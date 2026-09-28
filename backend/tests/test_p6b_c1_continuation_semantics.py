"""P6-B-C1：continuation 首段 provider 调用语义锁定。

契约来源（只读对齐，不改 HTTP 路由）：
- ai_music._run_generation 的 non_retryable 契约：参数/内容/能力类错误
  不重试、不换 Provider、不烧第二家额度（test_instrumental_routing.test_7 锁的就是这条）。
- 本轮把同一 non_retryable 语义补进 continuation_service.generate_long_music 首段循环，
  并允许调用方注入 provider chain，使 continuation 不再强制自行解析全局 registry。

全部 provider 均为注入的 fake：不触真实 Yinchao / TemPolor / R2 / 主数据库。
即使环境变量里配了真 key，本文件的链路也不会走到真实 registry 的 provider 实例。
"""

import pathlib

import pytest
from unittest.mock import AsyncMock

from app.services.continuation_service import continuation_service
from app.services import task_store


class FakeProvider:
    """按脚本返回结果的 provider 替身，记录每次收到的 request。"""

    provider_type = "api"
    capabilities = ["text_to_music"]
    production = True
    max_duration = 300
    gpu = "none"

    def __init__(self, name, results):
        self.name = name
        self._results = list(results)
        self.requests = []

    async def generate(self, request: dict) -> dict:
        self.requests.append(dict(request))
        if self._results:
            return self._results.pop(0)
        return {"success": False, "error": f"{self.name} 调用次数超出脚本预期"}

    def segment_flags(self):
        """(是否首段, 次数) 里首段的调用次数 —— enable_audio2audio 区分两段。"""
        return sum(1 for r in self.requests if not r.get("enable_audio2audio"))


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    """continuation 只用 task_store.update 写进度；桩掉以避免真实 DB（含 sqlite ai_tasks 缺列）。"""
    monkeypatch.setattr(task_store, "update", lambda *a, **k: None)


@pytest.fixture()
def offline_env(monkeypatch):
    """显式声明：即使走到未注入的路径，也不会连真实 provider 端点。"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("YINCHAO_API_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("TEMPOLOR_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.delenv("AI_GENERATION_PROVIDER", raising=False)


def _ok(tmp_path, tag):
    p = pathlib.Path(tmp_path / f"{tag}.wav")
    p.touch()
    return {"success": True, "volume_files": {"full_wav": tag, "_local_path": str(p)}}


def _fail(error, non_retryable=False):
    out = {"success": False, "error": error}
    if non_retryable:
        out["non_retryable"] = True
    return out


@pytest.fixture()
def stub_heavy_io(monkeypatch, tmp_path):
    """桩掉参考段截取/分析/歌词续写/拼接/R2 上传，只保留 provider 选择与失败语义真实。"""
    combined = pathlib.Path(tmp_path / "combined.wav")
    combined.touch()
    monkeypatch.setattr(
        "app.services.audio_trim.trim_audio",
        AsyncMock(return_value=(b"fake_wav_bytes" * 1000, "audio/wav")),
    )
    monkeypatch.setattr(
        "app.services.continuation_analysis.analyze_audio_context",
        AsyncMock(return_value={"bpm": 120, "key": "C major"}),
    )
    monkeypatch.setattr(continuation_service, "_continue_lyrics", AsyncMock(return_value="cont"))
    monkeypatch.setattr(
        continuation_service, "_stitch_with_crossfade", AsyncMock(return_value=str(combined))
    )
    # P6-B-C2：成品时长硬闸的实测出口在此桩掉（这些用例测的是 provider 语义，不是测量）。
    monkeypatch.setattr(
        continuation_service, "_measure_final_duration", AsyncMock(return_value=271.0)
    )
    monkeypatch.setattr(continuation_service, "_upload_parts", AsyncMock(return_value={}))
    monkeypatch.setattr(
        continuation_service,
        "_upload_final",
        AsyncMock(return_value={"full_wav": "music/final.wav", "full_mp3": "music/final.mp3"}),
    )
    return combined


async def _long(chain, **kw):
    params = dict(prompt="p", style="pop", duration=300, lyrics="ly",
                  task_id="t-c1", user_key="u-c1", provider_chain=chain)
    params.update(kw)
    return await continuation_service.generate_long_music(**params)


# ── Test A：注入链第一家直接成功 ────────────────────────────────────────────
async def test_a_injected_first_provider_success_no_fallback(offline_env, stub_heavy_io, tmp_path):
    a = FakeProvider("injected-a", [_ok(tmp_path, "a1"), _ok(tmp_path, "a2")])
    b = FakeProvider("injected-b", [])
    result = await _long([a, b])
    assert result["success"] is True
    assert result["provider"] == "injected-a+continuation"
    assert a.segment_flags() == 1          # 首段只打一次
    assert len(a.requests) == 2            # 首段 + 第二段仍用同一家
    assert b.requests == []                # 成功即不碰链中下一家


# ── Test C：可重试失败 → 换下一家（本轮保持"每家一次"，见 Test B 的待裁决断言）──
async def test_c_retryable_failure_falls_back_to_next_provider(offline_env, stub_heavy_io, tmp_path):
    from app.services.ai_limits import MAX_AUTO_RETRIES
    attempts = 1 + MAX_AUTO_RETRIES

    a = FakeProvider("injected-a", [_fail("transient gpu error")] * attempts)
    b = FakeProvider("injected-b", [_ok(tmp_path, "b1"), _ok(tmp_path, "b2")])
    result = await _long([a, b])
    assert result["success"] is True
    assert result["provider"] == "injected-b+continuation"
    assert a.segment_flags() == attempts   # C1-R：换家前先用尽同一家的重试预算
    assert b.segment_flags() == 1
    assert len(b.requests) == 2            # 第二段沿用换家后的 provider，不跨家


# ── Test D：non_retryable → 不换家（对齐 HTTP 路由契约）──────────────────────
async def test_d_non_retryable_error_never_falls_back(offline_env, stub_heavy_io, tmp_path):
    a = FakeProvider("injected-a", [_fail("内容审核不通过（400）", non_retryable=True)])
    b = FakeProvider("injected-b", [_ok(tmp_path, "b1"), _ok(tmp_path, "b2")])
    with pytest.raises(RuntimeError, match="首段 150s 生成失败"):
        await _long([a, b])
    assert a.requests and len(a.requests) == 1   # 不重试
    assert b.requests == []                      # 绝不换下一家烧额度


async def test_d2_non_retryable_error_message_is_persisted(offline_env, stub_heavy_io, tmp_path, monkeypatch):
    """失败原因必须写进 task error，供外层统一 refund 时归因（不改 refund 本身）。"""
    seen = []
    monkeypatch.setattr(task_store, "update", lambda tid, **kw: seen.append(kw))
    a = FakeProvider("injected-a", [_fail("参数非法", non_retryable=True)])
    b = FakeProvider("injected-b", [])
    with pytest.raises(RuntimeError):
        await _long([a, b])
    assert any("不可重试" in str(v.get("error", "")) for v in seen)
    assert b.requests == []


# ── Test E：provider chain 注入确实生效，不再强制解析全局 registry ────────────
async def test_e_injected_chain_overrides_global_registry(offline_env, stub_heavy_io, tmp_path, monkeypatch):
    """全局路径若被使用会解析成真实 yinchao/tempolor；注入链生效时只见到 fake 名字。"""
    import app.services.provider_registry as pr

    def _boom(*a, **k):
        raise AssertionError("generate_long_music 不应在已注入 chain 时解析全局 registry")

    monkeypatch.setattr(pr, "get_provider_registry", _boom)
    a = FakeProvider("injected-only", [_ok(tmp_path, "e1"), _ok(tmp_path, "e2")])
    result = await _long([a])
    assert result["provider"] == "injected-only+continuation"
    assert a.segment_flags() == 1


async def test_e2_empty_injected_chain_is_rejected(offline_env, stub_heavy_io, tmp_path):
    with pytest.raises(ValueError, match="provider_chain"):
        await _long([])


async def test_e3_uninjected_path_still_resolves_fallback_chain(offline_env, stub_heavy_io, tmp_path, monkeypatch):
    """未注入时既有语义不变：仍由 registry.fallback_chain() 得到 Yinchao → TemPolor 顺序。"""
    a = FakeProvider("yinchao", [_ok(tmp_path, "f1"), _ok(tmp_path, "f2")])
    b = FakeProvider("tempolor", [])
    seen = {}

    class FakeRegistry:
        def fallback_chain(self):
            seen["fallback_chain"] = True
            return [a, b]

        def select(self, name=None):
            raise AssertionError("未设置 AI_GENERATION_PROVIDER 时不应调用 select()")

    monkeypatch.setattr("app.services.provider_registry.get_provider_registry", lambda: FakeRegistry())
    result = await continuation_service.generate_long_music(
        prompt="p", style="pop", duration=300, lyrics="ly", task_id="t-c1", user_key="u-c1",
    )
    assert seen.get("fallback_chain") is True
    assert result["provider"] == "yinchao+continuation"
    assert b.requests == []


# ── Test B（C1-R）：首段重试语义已与 HTTP 路由对齐 ──────────────────────────
# 原 C1 钉桩用例按其注释规定在本轮改写：每家共 1+MAX_AUTO_RETRIES 次，
# 预算内可被同一家救回（不外溢），耗尽后才换家，且不会多打一次。
async def test_b_retryable_failure_is_retried_within_same_provider(
    offline_env, stub_heavy_io, tmp_path
):
    from app.services.ai_limits import MAX_AUTO_RETRIES

    attempts = 1 + MAX_AUTO_RETRIES
    assert attempts >= 2, "重试预算必须至少 2 次，否则本用例失去意义"
    a = FakeProvider("injected-a", [_fail("transient")] + [_ok(tmp_path, "b1"), _ok(tmp_path, "b2")])
    b = FakeProvider("injected-b", [])
    result = await _long([a, b])
    assert result["provider"] == "injected-a+continuation"   # 同一家救回，不换家
    assert a.segment_flags() == 2                            # 第 2 次尝试即成功
    assert b.requests == []


async def test_b2_retry_ceiling_is_exactly_1_plus_max_auto_retries(
    offline_env, stub_heavy_io, tmp_path
):
    from app.services.ai_limits import MAX_AUTO_RETRIES

    attempts = 1 + MAX_AUTO_RETRIES
    a = FakeProvider("injected-a", [_fail("down")] * (attempts + 5))
    with pytest.raises(RuntimeError, match="首段 150s 生成失败"):
        await _long([a])
    assert len(a.requests) == attempts   # 精确上限：不少打，也不多打
