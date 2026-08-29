"""RunPod Provider 测试：验证 RunPod 作为生产主力、Fal 回退、Modal 禁止。"""

import pytest
import asyncio
import os

from app.services.provider_registry import get_provider_registry
from app.services import runpod_client, fal_client


@pytest.fixture()
def isolated_env(monkeypatch):
    """隔离环境变量，避免测试间污染。"""
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)
    monkeypatch.delenv("RUNPOD_ENDPOINT_ID", raising=False)
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.delenv("FAL_API_KEY", raising=False)
    monkeypatch.delenv("AI_GENERATION_PROVIDER", raising=False)


def test_runpod_is_default_production_provider(isolated_env):
    """生产环境默认 provider 为 runpod。"""
    os.environ["ENVIRONMENT"] = "production"
    os.environ["RUNPOD_API_KEY"] = "test_key"
    os.environ["RUNPOD_ENDPOINT_ID"] = "test_endpoint"

    # 重置注册表单例
    import app.services.provider_registry as pr
    pr._registry = None
    reg = pr.get_provider_registry()

    assert reg.select().name == "runpod"
    assert reg.select().production is True


def test_runpod_blocks_fal_and_modal_in_production(isolated_env):
    """生产环境禁止显式选择 Fal 和 Modal。"""
    os.environ["ENVIRONMENT"] = "production"
    os.environ["RUNPOD_API_KEY"] = "test_key"
    os.environ["RUNPOD_ENDPOINT_ID"] = "test_endpoint"

    import app.services.provider_registry as pr
    pr._registry = None
    reg = pr.get_provider_registry()

    with pytest.raises(RuntimeError, match="禁止选择.*fal_stable_audio"):
        reg.select("fal_stable_audio")

    with pytest.raises(RuntimeError, match="禁止选择.*modal_ace_step"):
        reg.select("modal_ace_step")


def test_development_allows_fallback(isolated_env):
    """开发环境允许显式选择 Fal 和 Modal（用于回归测试）。"""
    os.environ["ENVIRONMENT"] = "development"
    os.environ["RUNPOD_API_KEY"] = "test_key"
    os.environ["RUNPOD_ENDPOINT_ID"] = "test_endpoint"

    import app.services.provider_registry as pr
    pr._registry = None
    reg = pr.get_provider_registry()

    # 开发环境显式指定 Fal 应该成功（虽然生产不推荐）
    fal_provider = reg.select("fal_stable_audio")
    assert fal_provider.name == "fal_stable_audio"

    # 开发环境显式指定 Modal 应该成功
    modal_provider = reg.select("modal_ace_step")
    assert modal_provider.name == "modal_ace_step"


async def test_runpod_fallback_to_fal_in_production(isolated_env, monkeypatch):
    """生产环境：RunPod 失败时自动回退到 Fal（通过 provider 内部逻辑）。"""
    os.environ["ENVIRONMENT"] = "production"
    os.environ["RUNPOD_API_KEY"] = "test_key"
    os.environ["RUNPOD_ENDPOINT_ID"] = "test_endpoint"
    os.environ["FAL_KEY"] = "test_fal_key"

    # Mock RunPod 失败
    async def mock_runpod_fail(*args, **kwargs):
        return None

    # Mock Fal 成功
    async def mock_fal_success(*args, **kwargs):
        return {"full_wav": "fallback.wav", "full_mp3": "fallback.mp3"}

    import app.services.runpod_client as rc
    import app.services.fal_client as fc
    import app.services.provider_registry as pr

    monkeypatch.setattr(rc, "generate_via_runpod", mock_runpod_fail)
    monkeypatch.setattr(fc, "generate_via_fal", mock_fal_success)

    pr._registry = None
    reg = pr.get_provider_registry()
    provider = reg.select()

    assert provider.name == "runpod"

    # RunPod Provider 内部应该回退到 Fal
    result = await provider.generate({"prompt": "test", "duration": 10})
    assert result["success"] is True
    # provider name 会标记为 fallback 来源
    assert result["provider"] in ("runpod", "runpod->fal_fallback")
    assert result["volume_files"].get("full_wav") == "fallback.wav"


async def test_runpod_fails_without_fallback_when_fal_unavailable(isolated_env, monkeypatch):
    """生产环境：RunPod 失败且 Fal 也不可用时返回失败。"""
    os.environ["ENVIRONMENT"] = "production"
    os.environ["RUNPOD_API_KEY"] = "test_key"
    os.environ["RUNPOD_ENDPOINT_ID"] = "test_endpoint"
    os.environ.pop("FAL_KEY", None)

    async def mock_runpod_fail(*args, **kwargs):
        return None

    async def mock_fal_fail(*args, **kwargs):
        return None

    import app.services.runpod_client as rc
    import app.services.fal_client as fc
    import app.services.provider_registry as pr

    monkeypatch.setattr(rc, "generate_via_runpod", mock_runpod_fail)
    monkeypatch.setattr(fc, "generate_via_fal", mock_fal_fail)

    pr._registry = None
    reg = pr.get_provider_registry()
    provider = reg.select()

    result = await provider.generate({"prompt": "test", "duration": 10})
    assert result["success"] is False
    assert "RunPod generation failed" in result["error"]


async def test_runpod_provider_direct_call(isolated_env, monkeypatch):
    """直接测试 RunPodProvider.generate 方法。"""
    os.environ["ENVIRONMENT"] = "production"
    os.environ["RUNPOD_API_KEY"] = "test_key"
    os.environ["RUNPOD_ENDPOINT_ID"] = "test_endpoint"

    async def mock_runpod_success(*args, **kwargs):
        return {"full_wav": "test.wav", "full_mp3": "test.mp3"}

    import app.services.runpod_client as rc
    monkeypatch.setattr("app.services.runpod_client.generate_via_runpod", mock_runpod_success)

    import app.services.provider_registry as pr
    pr._registry = None
    reg = pr.get_provider_registry()
    provider = reg.select()

    result = await provider.generate({"prompt": "test song", "duration": 30})
    assert result["success"] is True
    assert result["provider"] == "runpod"
    assert result["volume_files"]["full_wav"] == "test.wav"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])