"""Phase 2A + 阶段 B：Instrumental / Normal 路由锁定测试。

契约事实（docs/PROVIDER_STRATEGY.md + yinchao_provider 官方合同 + _OPERATION_CHAINS）：
- instrumental=true → operation "instrumental" → Yinchao V4.0 Instrumental 单家
  （Mureka 已删除，2026-10-01；绝不进入 TemPolor，官方合同 yinchao /api/v1/song/instrumental）。
- 普通人声歌 → operation "normal" → Yinchao V4.0 → TemPolor（fallback）不变。
- duration 单点归一化为「不低于 MIN(240)」的单次生成目标；不再分 150+122 continuation 段
  （continuation 仅保留独立续写入口）。

全部 provider/IO 均为 mock：不触真实 API / 真实计费 / 主数据库。
ENVIRONMENT=production 下走真实的 ProviderRegistry.chain_for_operation() 路由代码，
仅把注册表内的 provider 实例替换为记录型 fake。
"""

import asyncio
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.routers import ai_music
from app.services import task_store
from app.services import provider_registry as pr
from app.services.ai_limits import MAX_AUTO_RETRIES
from app.services.provider_registry import BaseProvider

from tests.test_ai_music_flow import isolated_db  # noqa: F401  复用独立 SQLite + HF 关闭 fixture


class RecordingProvider(BaseProvider):
    """记录每次收到的 request；ok=False 时恒失败（retryable）。"""

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
        seg = tempfile.NamedTemporaryFile(prefix=f"c2_{self.name}_", suffix=".wav", delete=False)
        seg.write(b"fake-audio")
        seg.close()
        return {
            "success": True,
            "volume_files": {
                "full_wav": "fake.wav",
                "_local_path": seg.name,
                "_measured_duration_sec": 245.0,  # 预实测值：质量门直接采信，不触 librosa
            },
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
    # 屏蔽真实外部依赖：Agnes 优化 / R2 上传 / 首歌奖励 / HF 兜底
    async def _agnes(_req):
        return SimpleNamespace(optimized_prompt="optimized", generated_lyrics=None)
    monkeypatch.setattr(ai_music.agnes_service, "generate_song", _agnes)
    async def _upload(task_id, volume_result):
        task_store.update(task_id, state="completed", progress=100)
    monkeypatch.setattr(ai_music, "_upload_and_finalize", _upload)
    monkeypatch.setattr(ai_music.credits_service, "claim_first_song_bonus", lambda u: None)
    monkeypatch.setattr(ai_music, "_try_hf_ace_step_fallback", AsyncMock(return_value=None))
    monkeypatch.setattr(ai_music, "_log_generation_cost", lambda *a, **k: None)
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


def test_1_instrumental_60s_single_shot_yinchao(isolated_db, prod_env, monkeypatch):
    """instrumental=true + 60s：Yinchao V4.0 Instrumental 单次成功，tempolor/mureka 不碰。"""
    y, t, m = RecordingProvider("yinchao"), RecordingProvider("tempolor"), RecordingProvider("mureka")
    tid = _run(monkeypatch, [y, t, m], duration=60, instrumental=True)
    assert len(y.requests) == 1
    assert y.requests[0]["operation"] == "instrumental"
    assert y.requests[0]["is_instrumental"] is True
    assert y.requests[0]["duration"] == 240        # 单点归一化：抬到 MIN，单次生成
    assert t.requests == []                        # instrumental 绝不进入 TemPolor
    assert m.requests == []                        # 链首成功 → 不切第二跳
    assert (task_store.get(tid) or {}).get("state") == "completed"


def test_2_instrumental_180s_boundary_still_yinchao(isolated_db, prod_env, monkeypatch):
    """instrumental=true + 180s（旧边界值）：仍单跳 Yinchao Instrumental。"""
    y, t, m = RecordingProvider("yinchao"), RecordingProvider("tempolor"), RecordingProvider("mureka")
    _run(monkeypatch, [y, t, m], duration=180, instrumental=True)
    assert len(y.requests) == 1
    assert y.requests[0]["duration"] == 240
    assert y.requests[0]["operation"] == "instrumental"
    assert t.requests == [] and m.requests == []


def test_3_instrumental_240s_single_shot_yinchao(isolated_db, prod_env, monkeypatch):
    """instrumental=true + 240s（阶段 B 下限）：单次生成，参数透传。"""
    y, t, m = RecordingProvider("yinchao"), RecordingProvider("tempolor"), RecordingProvider("mureka")
    tid = _run(monkeypatch, [y, t, m], duration=240, instrumental=True)
    assert len(y.requests) == 1
    assert y.requests[0]["duration"] == 240
    assert t.requests == [] and m.requests == []
    assert (task_store.get(tid) or {}).get("state") == "completed"


def test_4_instrumental_yinchao_fail_no_fallback_target(isolated_db, prod_env, monkeypatch):
    """Yinchao Instrumental 用尽 1+MAX_AUTO_RETRIES 仍失败 → 链无下一家（Mureka 已删除）
    → 任务 failed，绝不进 TemPolor，也绝无第二跳。"""
    y, t, m = RecordingProvider("yinchao", ok=False), RecordingProvider("tempolor"), RecordingProvider("mureka")
    tid = _run(monkeypatch, [y, t, m], duration=60, instrumental=True)
    assert len(y.requests) == 1 + MAX_AUTO_RETRIES  # 按既有重试策略打满
    assert m.requests == [], "Mureka 已删除：instrumental 链不存在第二跳"
    assert t.requests == [], "instrumental fallback 绝不允许进入 TemPolor"
    assert (task_store.get(tid) or {}).get("state") == "failed"


def test_5_normal_song_uses_yinchao_first(isolated_db, prod_env, monkeypatch):
    """instrumental=false + 60s：链 Yinchao → TemPolor，链首成功则单次生成、不碰下一家。"""
    y, t, m = RecordingProvider("yinchao"), RecordingProvider("tempolor"), RecordingProvider("mureka")
    tid = _run(monkeypatch, [y, t, m], duration=60)
    assert len(y.requests) == 1
    assert y.requests[0]["operation"] == "normal"
    assert y.requests[0]["duration"] == 240        # 60s 抬到 MIN；单次生成（无 150+122 段）
    assert t.requests == [] and m.requests == []
    assert (task_store.get(tid) or {}).get("state") == "completed"


def test_6_normal_song_falls_back_to_tempolor(isolated_db, prod_env, monkeypatch):
    """Yinchao 用尽 1+MAX_AUTO_RETRIES 仍失败 → 自动切 TemPolor 单次完成，不回头。"""
    y, t, m = RecordingProvider("yinchao", ok=False), RecordingProvider("tempolor"), RecordingProvider("mureka")
    tid = _run(monkeypatch, [y, t, m], duration=60)
    assert len(y.requests) == 1 + MAX_AUTO_RETRIES
    assert len(t.requests) == 1
    assert t.requests[0]["operation"] == "normal"
    assert t.requests[0]["duration"] == 240
    assert m.requests == [], "normal 链不含 mureka"
    assert (task_store.get(tid) or {}).get("state") == "completed"


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


def test_8_explicit_env_keeps_single_provider_hop(isolated_db, monkeypatch):
    """显式 AI_GENERATION_PROVIDER=yinchao：保持单跳 select() 语义（不分链、不 fallback）；
    阶段 B 后 instrumental 官方入口即 Yinchao V4.0 Instrumental，payload 原样到达。"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AI_GENERATION_PROVIDER", "yinchao")
    y, t, m = RecordingProvider("yinchao"), RecordingProvider("tempolor"), RecordingProvider("mureka")
    tid = _run(monkeypatch, [y, t, m], duration=60, instrumental=True)
    assert len(y.requests) == 1
    assert y.requests[0]["operation"] == "instrumental"
    assert t.requests == [] and m.requests == []
    assert (task_store.get(tid) or {}).get("state") == "completed"
    monkeypatch.delenv("AI_GENERATION_PROVIDER", raising=False)
