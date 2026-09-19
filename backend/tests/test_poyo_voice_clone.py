"""PoYo Voice Clone Provider 单元测试（全程 mock，不调用真实 API、不含真实 Key）。"""

from __future__ import annotations

import asyncio

import pytest

from app.services import poyo_voice_clone_provider as pvc
from app.services.poyo_voice_clone_provider import (
    PoYoVoiceCloneError,
    PoYoVoiceCloneProvider,
)


@pytest.fixture(autouse=True)
def _clear_key(monkeypatch):
    monkeypatch.delenv("POYO_API_KEY", raising=False)
    monkeypatch.setenv("POYO_API_KEY", "test-key")


def _provider() -> PoYoVoiceCloneProvider:
    p = PoYoVoiceCloneProvider()
    p._api_key = "test-key"
    return p


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── 1. 缺 Key ──────────────────────────────────────
def test_missing_key(monkeypatch):
    monkeypatch.delenv("POYO_API_KEY", raising=False)
    p = PoYoVoiceCloneProvider()
    assert p.is_configured() is False
    with pytest.raises(PoYoVoiceCloneError):
        run(p.validate("https://x/a.mp3", 0, 10))


# ── 2/3. validate 成功 / 失败 ────────────────────────
def test_validate_success(monkeypatch):
    async def fake_submit(client, key, model, inp):
        assert model == "suno-voice-validate"
        assert inp["voice_url"] == "https://x/a.mp3"
        return "vt_1"

    async def fake_poll(client, key, task_id, deadline):
        return {"status": "finished", "files": [{"voice_status": "wait_validating", "validate_info": "Read phrase"}]}

    monkeypatch.setattr(pvc, "_submit", fake_submit)
    monkeypatch.setattr(pvc, "_poll", fake_poll)
    r = run(_provider().validate("https://x/a.mp3", 0, 10, "en"))
    assert r["task_id"] == "vt_1"
    assert r["validate_info"] == "Read phrase"


def test_validate_failure(monkeypatch):
    async def fake_submit(client, key, model, inp):
        raise PoYoVoiceCloneError("PoYo 请求参数错误（400）")

    monkeypatch.setattr(pvc, "_submit", fake_submit)
    with pytest.raises(PoYoVoiceCloneError):
        run(_provider().validate("https://x/a.mp3", 0, 10))


# ── 4/5. generate 成功 / 失败 ────────────────────────
def test_generate_success(monkeypatch):
    async def fake_submit(client, key, model, inp):
        assert model == "suno-voice-generate"
        assert inp["task_id"] == "vt_1"
        assert inp["verify_url"] == "https://x/verify.wav"
        return "gt_1"

    async def fake_poll(client, key, task_id, deadline):
        return {"status": "finished", "files": [{"voice_status": "success", "voice_id": "voice_abc123"}]}

    monkeypatch.setattr(pvc, "_submit", fake_submit)
    monkeypatch.setattr(pvc, "_poll", fake_poll)
    r = run(_provider().generate("vt_1", "https://x/verify.wav"))
    assert r["voice_id"] == "voice_abc123"


def test_generate_failure(monkeypatch):
    # 测真正的 _poll：task 返回 failed → 抛 PoYoVoiceCloneError
    import time as _time

    class FakeResp:
        status_code = 200
        content = b"{}"

        def json(self):
            return {"data": {"status": "failed", "error_message": "invalid", "files": []}}

    class FakeClient:
        async def get(self, url, headers=None, params=None):
            return FakeResp()

    async def _no_sleep(seconds):
        return None

    monkeypatch.setattr(pvc.asyncio, "sleep", _no_sleep)
    with pytest.raises(PoYoVoiceCloneError):
        run(pvc._poll(FakeClient(), "k", "t", _time.monotonic() + 60))


# ── 6. task polling（真正的 _poll 循环直到 finished）──
def test_poll_loops_until_finished(monkeypatch):
    import time as _time

    responses = [
        {"status": "running", "files": []},
        {"status": "running", "files": []},
        {"status": "finished", "files": [{"voice_id": "v1", "voice_status": "success"}]},
    ]
    calls = {"n": 0}

    class FakeResp:
        status_code = 200
        content = b"{}"

        def json(self):
            calls["n"] += 1
            return {"data": responses[min(calls["n"] - 1, len(responses) - 1)]}

    class FakeClient:
        async def get(self, url, headers=None, params=None):
            return FakeResp()

    async def _no_sleep(seconds):
        return None

    monkeypatch.setattr(pvc.asyncio, "sleep", _no_sleep)
    r = run(pvc._poll(FakeClient(), "k", "t", _time.monotonic() + 60))
    assert r["status"] == "finished"
    assert calls["n"] >= 3


# ── 7. voice_id 正确解析（含在 files[0]）────────────
def test_voice_id_parsed(monkeypatch):
    async def fake_submit(client, key, model, inp):
        return "gt_1"

    async def fake_poll(client, key, task_id, deadline):
        return {"status": "finished", "files": [{"voice_status": "success", "voice_id": "voice_x"}]}

    monkeypatch.setattr(pvc, "_submit", fake_submit)
    monkeypatch.setattr(pvc, "_poll", fake_poll)
    assert run(_provider().generate("vt_1", "u"))["voice_id"] == "voice_x"


# ── 8. is_available 正确解析 ────────────────────────
def test_check_is_available(monkeypatch):
    async def fake_submit(client, key, model, inp):
        assert model == "suno-voice-check"
        return "ct_1"

    async def fake_poll(client, key, task_id, deadline):
        return {"status": "finished", "files": [{"is_available": True}]}

    monkeypatch.setattr(pvc, "_submit", fake_submit)
    monkeypatch.setattr(pvc, "_poll", fake_poll)
    assert run(_provider().check("gt_1"))["is_available"] is True


# ── 9. timeout ─────────────────────────────────────
def test_timeout(monkeypatch):
    async def fake_submit(client, key, model, inp):
        return "gt_1"

    async def fake_poll(client, key, task_id, deadline):
        raise PoYoVoiceCloneError("PoYo voice polling timeout")

    monkeypatch.setattr(pvc, "_submit", fake_submit)
    monkeypatch.setattr(pvc, "_poll", fake_poll)
    with pytest.raises(PoYoVoiceCloneError):
        run(_provider().generate("vt_1", "u"))


# ── 10. 非 2xx ─────────────────────────────────────
def test_non_2xx(monkeypatch):
    class FakeResp:
        status_code = 401
        text = ""

    async def fake_submit(client, key, model, inp):
        raise PoYoVoiceCloneError(pvc._map_submit_error(FakeResp()))

    monkeypatch.setattr(pvc, "_submit", fake_submit)
    with pytest.raises(PoYoVoiceCloneError) as ei:
        run(_provider().validate("https://x/a.mp3", 0, 10))
    assert "401" in str(ei.value)


# ── 11. 无效参数（语言/时间/缺 task_id）────────────
def test_invalid_param_language(monkeypatch):
    with pytest.raises(PoYoVoiceCloneError):
        run(_provider().validate("https://x/a.mp3", 0, 10, "xx"))


def test_invalid_param_time(monkeypatch):
    with pytest.raises(PoYoVoiceCloneError):
        run(_provider().validate("https://x/a.mp3", 10, 5, "en"))


def test_invalid_generate_missing_task(monkeypatch):
    with pytest.raises(PoYoVoiceCloneError):
        run(_provider().generate("", "https://x/verify.wav"))


# ── 12. 不发生重复创建（每个方法仅提交一次）────────
def test_no_duplicate_create(monkeypatch):
    submits = {"n": 0}

    async def fake_submit(client, key, model, inp):
        submits["n"] += 1
        return "gt_1"

    async def fake_poll(client, key, task_id, deadline):
        return {"status": "finished", "files": [{"voice_id": "v1", "voice_status": "success"}]}

    monkeypatch.setattr(pvc, "_submit", fake_submit)
    monkeypatch.setattr(pvc, "_poll", fake_poll)
    run(_provider().generate("vt_1", "u"))
    assert submits["n"] == 1  # 一次请求只提交一次，无内部重试重复 create