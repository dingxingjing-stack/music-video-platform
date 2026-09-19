"""Phase 2A：Instrumental 路由锁定测试。

契约事实（见 docs/PROVIDER_STRATEGY.md + yinchao_provider 注释）：
Yinchao 无 instrumental 参数（payload 固定 task_type="normal"，进入即产出带人声），
因此 instrumental=true 时任意时长都必须只走 TemPolor；普通人声歌链路保持
生产链 Yinchao → TemPolor（fallback）不变。

全部 provider/IO 均为 mock：不触真实 API / 真实计费 / 主数据库。
ENVIRONMENT=production 下走真实的 ProviderRegistry.select()/fallback_chain() 路由代码，
仅把注册表内的 provider 实例替换为记录型 fake。
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.routers import ai_music
from app.services import task_store
from app.services import provider_registry as pr
from app.services.provider_registry import BaseProvider

from tests.test_ai_music_flow import isolated_db  # noqa: F401  复用独立 SQLite + HF 关闭 fixture


class RecordingProvider(BaseProvider):
    """记录每次收到的 request；ok=False 时恒失败。"""

    provider_type = "api"
    capabilities = ["text_to_music"]
    production = True

    def __init__(self, name: str, ok: bool = True):
        self.name = name
        self.ok = ok
        self.requests: list[dict] = []

    async def generate(self, request: dict) -> dict:
        self.requests.append(dict(request))
        if not self.ok:
            return {"success": False, "error": f"{self.name} down", "provider": self.name}
        return {
            "success": True,
            "volume_files": {"full_wav": "fake.wav", "_local_path": "nonexistent-local-path"},
            "provider": self.name,
        }


@pytest.fixture()
def prod_env(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("AI_GENERATION_PROVIDER", raising=False)
    yield
    monkeypatch.delenv("AI_GENERATION_PROVIDER", raising=False)


def _install(monkeypatch, providers):
    """真实 ProviderRegistry 实例 + fake provider，桩掉重 IO 后仅保留路由逻辑真实。"""
    reg = pr.ProviderRegistry()
    for p in providers:
        reg.register(p)
    monkeypatch.setattr(ai_music, "get_provider_registry", lambda: reg)
    # 屏蔽真实外部依赖：Agnes 优化 / R2 上传 / 首歌奖励
    async def _agnes(_req):
        return SimpleNamespace(optimized_prompt="optimized", generated_lyrics=None)
    monkeypatch.setattr(ai_music.agnes_service, "generate_song", _agnes)
    async def _upload(task_id, volume_result):
        task_store.update(task_id, state="completed", progress=100)
    monkeypatch.setattr(ai_music, "_upload_and_finalize", _upload)
    monkeypatch.setattr(ai_music.credits_service, "claim_first_song_bonus", lambda u: None)
    # 失败路径的 credits 退款走全局 SessionLocal（非 isolated_db 覆盖范围），桩掉避免污染真实库
    monkeypatch.setattr(
        ai_music.credits_service, "refund_generation_credits",
        lambda u, t: {"success": True, "mocked": True},
    )
    return reg


def _run(monkeypatch, providers, **req_kw):
    _install(monkeypatch, providers)
    tid = task_store.new_task("uA")
    params = {"prompt": "a piano piece"}
    params.update(req_kw)
    req = ai_music.GenerateRequest(**params)
    asyncio.run(ai_music._run_generation(tid, req, "uA"))
    return tid


def test_1_short_instrumental_60s_only_tempolor(isolated_db, prod_env, monkeypatch):
    """instrumental=true + 60s：必须 TemPolor，绝不 Yinchao。"""
    y = RecordingProvider("yinchao")
    t = RecordingProvider("tempolor")
    _run(monkeypatch, [y, t], duration=60, instrumental=True)
    assert y.requests == []
    assert len(t.requests) == 1
    assert t.requests[0]["is_instrumental"] is True


def test_2_instrumental_180s_only_tempolor(isolated_db, prod_env, monkeypatch):
    """instrumental=true + 180s（边界值）：仍必须 TemPolor。"""
    y = RecordingProvider("yinchao")
    t = RecordingProvider("tempolor")
    _run(monkeypatch, [y, t], duration=180, instrumental=True)
    assert y.requests == []
    assert t.requests[0]["is_instrumental"] is True


def test_3_long_instrumental_240s_only_tempolor(isolated_db, prod_env, monkeypatch):
    """instrumental=true + 240s（长歌分支已有）：保持 TemPolor 且透传参数。"""
    y = RecordingProvider("yinchao")
    t = RecordingProvider("tempolor")
    _run(monkeypatch, [y, t], duration=240, instrumental=True)
    assert y.requests == []
    assert t.requests[0]["is_instrumental"] is True


def test_4_normal_short_song_uses_yinchao_first(isolated_db, prod_env, monkeypatch):
    """instrumental=false + 60s：生产链 Yinchao 优先（成功则不碰 TemPolor），原行为不变。"""
    y = RecordingProvider("yinchao")
    t = RecordingProvider("tempolor")
    _run(monkeypatch, [y, t], duration=60)
    assert len(y.requests) == 1
    assert y.requests[0]["is_instrumental"] is False
    assert t.requests == []


def test_5_normal_song_fallback_unchanged(isolated_db, prod_env, monkeypatch):
    """Yinchao 两次尝试（1+MAX_AUTO_RETRIES=1）均失败 → 自动切 TemPolor 成功。"""
    y = RecordingProvider("yinchao", ok=False)
    t = RecordingProvider("tempolor")
    _run(monkeypatch, [y, t], duration=60)
    assert len(y.requests) == 2
    assert len(t.requests) == 1
    assert t.requests[0]["is_instrumental"] is False


def test_6_instrumental_overrides_explicit_yinchao_env(isolated_db, monkeypatch):
    """即使 AI_GENERATION_PROVIDER=yinchao，instrumental 也不得进入 Yinchao。"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AI_GENERATION_PROVIDER", "yinchao")
    y = RecordingProvider("yinchao")
    t = RecordingProvider("tempolor")
    _run(monkeypatch, [y, t], duration=60, instrumental=True)
    assert y.requests == []
    assert len(t.requests) == 1
    monkeypatch.delenv("AI_GENERATION_PROVIDER", raising=False)


def test_7_validation_error_never_falls_back(isolated_db, prod_env, monkeypatch):
    """§16/§19-Test14：Yinchao 返回参数类错误（non_retryable）→ 禁止切换 TemPolor、不耗其额度。"""
    class NonRetryableYinchao(RecordingProvider):
        async def generate(self, request: dict) -> dict:
            self.requests.append(dict(request))
            return {"success": False, "error": "Yinchao 请求参数错误（400）",
                    "non_retryable": True, "provider": self.name}

    y = NonRetryableYinchao("yinchao")
    t = RecordingProvider("tempolor")
    tid = _run(monkeypatch, [y, t], duration=60)
    assert len(y.requests) == 1          # 不可重试：只打一次
    assert t.requests == []              # 绝不进入 TemPolor
    assert (task_store.get(tid) or {}).get("state") == "failed"
