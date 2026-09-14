"""Commit 8 测试：长音乐（>180s）首段 Yinchao → TemPolor fallback，第二段绝不跨家。

全部 provider/IO 均为 mock，不触碰真实 API、真实文件（除 tmp_path）与真实计费。
"""

import pathlib

import pytest
from unittest.mock import AsyncMock, patch

from app.services.continuation_service import continuation_service
from app.services import task_store


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    """continuation 只用 task_store.update 做进度标记；桩掉以避免真实 DB。"""
    monkeypatch.setattr(task_store, "update", lambda *args, **kwargs: None)


@pytest.fixture()
def prod_auto(monkeypatch):
    """production 自动模式：无显式 provider，链 = [yinchao, tempolor]。"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("AI_GENERATION_PROVIDER", raising=False)
    import app.services.provider_registry as pr
    pr._registry = None
    yield
    pr._registry = None


def _touch(path):
    pathlib.Path(path).touch(exist_ok=True)
    return str(path)


def _ok_volume(local_path):
    return {"success": True, "volume_files": {"full_wav": local_path, "_local_path": local_path}}


def _fail(error):
    return {"success": False, "error": error}


def _stub_heavy_io(monkeypatch, tmp_path):
    """桩掉续写上下文/拼接/上传等重 IO，只保留 provider 选择逻辑真实。"""
    combined = _touch(str(tmp_path / "combined.wav"))
    monkeypatch.setattr(
        "app.services.audio_trim.trim_audio",
        AsyncMock(return_value=(b"fake_wav_bytes" * 1000, "audio/wav")),
    )
    monkeypatch.setattr(
        "app.services.continuation_analysis.analyze_audio_context",
        AsyncMock(return_value={"bpm": 120, "key": "C major"}),
    )
    monkeypatch.setattr(
        continuation_service, "_continue_lyrics", AsyncMock(return_value="continued lyrics")
    )
    monkeypatch.setattr(
        continuation_service, "_stitch_with_crossfade", AsyncMock(return_value=combined)
    )
    monkeypatch.setattr(continuation_service, "_upload_parts", AsyncMock(return_value={}))
    monkeypatch.setattr(
        continuation_service,
        "_upload_final",
        AsyncMock(return_value={"full_wav": "music/task/final.wav", "full_mp3": "music/task/final.mp3"}),
    )
    return combined


def _install_segment_router(monkeypatch, behaviors):
    """按 (provider 名, 是否第二段) 路由 _generate_single_segment 返回值，并记录调用。

    behaviors: {(name, is_second): result | [result, ...]}，缺省为成功（需调用方先建好文件）。
    """
    calls: list = []

    async def _stub(provider, prompt, lyrics, duration, reference_b64, enable_a2a):
        key = (provider.name, bool(enable_a2a))
        calls.append(key)
        seq = behaviors.get(key)
        if seq is None:
            raise AssertionError(f"unexpected segment call: {key}")
        if isinstance(seq, list):
            assert seq, f"behavior exhausted for {key}"
            return seq.pop(0)
        return seq

    monkeypatch.setattr(continuation_service, "_generate_single_segment", _stub)
    return calls


def _run_long(**kwargs):
    params = dict(prompt="test", style="pop", duration=300, lyrics="test lyrics",
                  task_id="test-c8", user_key="test-c8")
    params.update(kwargs)
    return continuation_service.generate_long_music(**params)


async def test_1_yinchao_first_segment_success_stays_yinchao(prod_auto, monkeypatch, tmp_path):
    """Yinchao 首段成功 → 第二段仍用 Yinchao，metadata 为 yinchao+continuation。"""
    p1 = _touch(str(tmp_path / "p1.wav"))
    p2 = _touch(str(tmp_path / "p2.wav"))
    _stub_heavy_io(monkeypatch, tmp_path)
    calls = _install_segment_router(monkeypatch, {
        ("yinchao", False): _ok_volume(p1),
        ("yinchao", True): _ok_volume(p2),
    })
    result = await _run_long()
    assert result["success"] is True
    assert calls == [("yinchao", False), ("yinchao", True)]
    assert result["provider"] == "yinchao+continuation"


async def test_2_first_segment_fallback_to_tempolor(prod_auto, monkeypatch, tmp_path):
    """Yinchao 首段失败 → TemPolor 首段成功 → 第二段用 TemPolor，不切回 Yinchao。"""
    p1 = _touch(str(tmp_path / "t1.wav"))
    p2 = _touch(str(tmp_path / "t2.wav"))
    _stub_heavy_io(monkeypatch, tmp_path)
    calls = _install_segment_router(monkeypatch, {
        ("yinchao", False): _fail("yinchao down"),
        ("tempolor", False): _ok_volume(p1),
        ("tempolor", True): _ok_volume(p2),
    })
    result = await _run_long()
    assert result["success"] is True
    assert calls == [("yinchao", False), ("tempolor", False), ("tempolor", True)]
    assert result["provider"] == "tempolor+continuation"


async def test_3_both_first_segments_fail(prod_auto, monkeypatch, tmp_path):
    """双败 → 抛最终异常（交外层统一 refund 一次）；只尝试两家，不碰 HF/Mureka/RunPod。"""
    _stub_heavy_io(monkeypatch, tmp_path)
    calls = _install_segment_router(monkeypatch, {
        ("yinchao", False): _fail("yinchao down"),
        ("tempolor", False): _fail("tempolor down"),
    })
    with pytest.raises(RuntimeError, match="首段 150s 生成失败"):
        await _run_long()
    assert calls == [("yinchao", False), ("tempolor", False)]
    assert {name for name, _ in calls} == {"yinchao", "tempolor"}


def test_3b_continuation_never_refunds_directly():
    """continuation 内禁止直接退款调用：源码级断言（退款只允许在外层 ai_music 统一处理）。"""
    import pathlib
    import app.services.continuation_service as cont_mod
    src = pathlib.Path(cont_mod.__file__).read_text(encoding="utf-8")
    for call in ("refund_generation", "refund_generation_credits", "consume_credits"):
        assert call not in src


async def test_4_explicit_yinchao_never_falls_back(monkeypatch, tmp_path):
    """AI_GENERATION_PROVIDER=yinchao → 失败不切 TemPolor。"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AI_GENERATION_PROVIDER", "yinchao")
    import app.services.provider_registry as pr
    pr._registry = None
    try:
        _stub_heavy_io(monkeypatch, tmp_path)
        calls = _install_segment_router(monkeypatch, {("yinchao", False): _fail("boom")})
        with pytest.raises(RuntimeError, match="首段 150s 生成失败"):
            await _run_long()
        assert calls == [("yinchao", False)]
    finally:
        pr._registry = None


async def test_5_explicit_tempolor_never_falls_back(monkeypatch, tmp_path):
    """AI_GENERATION_PROVIDER=tempolor → 失败不切 Yinchao。"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AI_GENERATION_PROVIDER", "tempolor")
    import app.services.provider_registry as pr
    pr._registry = None
    try:
        _stub_heavy_io(monkeypatch, tmp_path)
        calls = _install_segment_router(monkeypatch, {("tempolor", False): _fail("boom")})
        with pytest.raises(RuntimeError, match="首段 150s 生成失败"):
            await _run_long()
        assert calls == [("tempolor", False)]
    finally:
        pr._registry = None


async def test_6a_second_segment_yinchao_failure_never_switches(prod_auto, monkeypatch, tmp_path):
    """Yinchao 首段成功、第二段失败 → 不切 TemPolor 第二段，最终失败。"""
    p1 = _touch(str(tmp_path / "p1.wav"))
    _stub_heavy_io(monkeypatch, tmp_path)
    calls = _install_segment_router(monkeypatch, {
        ("yinchao", False): _ok_volume(p1),
        ("yinchao", True): [_fail("seg2 down")] * 10,
    })
    with pytest.raises(RuntimeError, match="续写段生成失败"):
        await _run_long()
    assert ("tempolor", True) not in calls
    assert {name for name, second in calls if second} == {"yinchao"}


async def test_6b_second_segment_tempolor_failure_never_switches(monkeypatch, tmp_path):
    """TemPolor 首段成功、第二段失败 → 不切 Yinchao 第二段，最终失败。"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AI_GENERATION_PROVIDER", "tempolor")
    import app.services.provider_registry as pr
    pr._registry = None
    try:
        p1 = _touch(str(tmp_path / "t1.wav"))
        _stub_heavy_io(monkeypatch, tmp_path)
        calls = _install_segment_router(monkeypatch, {
            ("tempolor", False): _ok_volume(p1),
            ("tempolor", True): [_fail("seg2 down")] * 10,
        })
        with pytest.raises(RuntimeError, match="续写段生成失败"):
            await _run_long()
        assert ("yinchao", True) not in calls
        assert {name for name, second in calls if second} == {"tempolor"}
    finally:
        pr._registry = None
