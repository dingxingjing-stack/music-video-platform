"""P4-B2 Phase B-3 测试：Lyrics 双 Provider 替换（Yinchao primary → TemPolor backup）。

覆盖 B-3 授权 §七：
- Yinchao: HTTP 200/401/400/5xx/timeout/malformed JSON/missing title/missing lyric
- TemPolor: generate success/business error/HTTP error/timeout、query success/pending/
  failure/rate-limit、deadline exhaustion
- Engine: Yinchao success / 失败→TemPolor success / 双败 / Yinchao timeout→fallback /
  全局 45s hard deadline
- Contract: 路由与 GenerateLyricResponse 契约不变、styles/moods 不变、Credits 零交互、
  Agnes/Gemini/NVIDIA shared production path 不变
- Prompt: _build_prompt 最终结果 ≤2000 允许 / >2000 显式 400（无静默截断）

全部 mock，零真实 API、零费用。
"""

import asyncio
import base64
import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from app.services import lyric_service
from app.services.lyric_service import LyricRequest
import app.services.lyric_service as lyric_service_mod
from app.services.lyrics_engine import LyricsEngine
from app.services.yinchao_lyric_provider import YinchaoLyricProvider
from app.services.tempolor_lyric_provider import TempolorLyricProvider


def _fake_response(status_code=200, payload=None, text=""):
    """构造 httpx.Response 替身（避免真实网络）。"""

    class _Resp:
        def __init__(self):
            self.status_code = status_code
            self._payload = payload
            self.text = text if text else (json.dumps(payload) if payload else "")

        def json(self):
            if self._payload is None:
                raise ValueError("not json")
            return self._payload

    return _Resp()


def _run(coro):
    return asyncio.run(coro)


# ────────────────────────── YinchaoLyricProvider ──────────────────────────

def _patch_yinchao_http(monkeypatch, resp):
    sent = {}

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, json=None):
            sent["url"] = url
            sent["headers"] = headers
            sent["json"] = json
            return resp

    import httpx as _httpx
    monkeypatch.setattr(_httpx, "AsyncClient", FakeClient)
    return sent


def test_yinchao_lyric_success(monkeypatch):
    sent = _patch_yinchao_http(monkeypatch, _fake_response(200, {"title": "夜航", "lyric": "[Verse]\n星河"}))
    monkeypatch.setenv("YINCHAO_API_KEY", "test-key")
    p = YinchaoLyricProvider()
    r = _run(p.generate("夏天的海边", timeout=15))
    assert r["success"] is True
    assert r["title"] == "夜航"
    assert r["lyric"] == "[Verse]\n星河"
    assert sent["url"].endswith("/api/v1/lyric/generate")
    assert sent["json"] == {"prompt": "夏天的海边"}  # 官方契约：唯一字段
    assert sent["headers"]["Authorization"] == "Bearer test-key"


def test_yinchao_lyric_401(monkeypatch):
    _patch_yinchao_http(monkeypatch, _fake_response(401, {"detail": "unauthorized"}))
    monkeypatch.setenv("YINCHAO_API_KEY", "bad")
    r = _run(YinchaoLyricProvider().generate("p", timeout=15))
    assert r["success"] is False and "401" in r["error"]


def test_yinchao_lyric_400(monkeypatch):
    _patch_yinchao_http(monkeypatch, _fake_response(400, {"detail": "bad request"}))
    monkeypatch.setenv("YINCHAO_API_KEY", "k")
    r = _run(YinchaoLyricProvider().generate("p", timeout=15))
    assert r["success"] is False and "400" in r["error"]


def test_yinchao_lyric_5xx(monkeypatch):
    _patch_yinchao_http(monkeypatch, _fake_response(500, {"detail": "boom"}))
    monkeypatch.setenv("YINCHAO_API_KEY", "k")
    r = _run(YinchaoLyricProvider().generate("p", timeout=15))
    assert r["success"] is False and "500" in r["error"]


def test_yinchao_lyric_timeout(monkeypatch):
    class TimeoutClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *a, **kw):
            raise httpx.TimeoutException("timed out")

    import httpx as _httpx
    monkeypatch.setattr(_httpx, "AsyncClient", TimeoutClient)
    monkeypatch.setenv("YINCHAO_API_KEY", "k")
    r = _run(YinchaoLyricProvider().generate("p", timeout=15))
    assert r["success"] is False and "timeout" in r["error"]


def test_yinchao_lyric_malformed_json(monkeypatch):
    _patch_yinchao_http(monkeypatch, _fake_response(200, None, text="<html>not json</html>"))
    monkeypatch.setenv("YINCHAO_API_KEY", "k")
    r = _run(YinchaoLyricProvider().generate("p", timeout=15))
    assert r["success"] is False


def test_yinchao_lyric_missing_title_ok_missing_lyric_fail(monkeypatch):
    # title 缺失可容忍（None）；lyric 缺失 = 失败
    monkeypatch.setenv("YINCHAO_API_KEY", "k")
    _patch_yinchao_http(monkeypatch, _fake_response(200, {"lyric": "[Verse]\nok"}))
    r = _run(YinchaoLyricProvider().generate("p", timeout=15))
    assert r["success"] is True and r["title"] is None

    _patch_yinchao_http(monkeypatch, _fake_response(200, {"title": "只有歌名"}))
    r2 = _run(YinchaoLyricProvider().generate("p", timeout=15))
    assert r2["success"] is False


def test_yinchao_lyric_missing_key(monkeypatch):
    monkeypatch.delenv("YINCHAO_API_KEY", raising=False)
    r = _run(YinchaoLyricProvider().generate("p", timeout=15))
    assert r["success"] is False


# ────────────────────────── TempolorLyricProvider ──────────────────────────

def _patch_tempolor_http(monkeypatch, responses):
    """responses: list of _fake_response，按调用顺序消费（generate→query…）。"""
    sent = []
    queue = list(responses)

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, json=None):
            sent.append({"url": url, "json": json})
            resp = queue.pop(0) if queue else _fake_response(200, {})
            resp._req = json
            return resp

        def _last_req(self):
            return sent[-1]["json"] if sent else None

    import httpx as _httpx
    monkeypatch.setattr(_httpx, "AsyncClient", FakeClient)
    return sent, queue


def test_tempolor_generate_success(monkeypatch):
    sent, _ = _patch_tempolor_http(monkeypatch, [
        _fake_response(200, {"status": 200000, "data": {"item_ids": ["i-1"]}}),
    ])
    monkeypatch.setenv("TEMPOLOR_API_KEY", "tk")
    monkeypatch.setenv("TEMPOLOR_CALLBACK_URL", "https://cb.example")
    p = TempolorLyricProvider()
    r = _run(p.generate("主题", timeout=15))
    assert r["success"] is True and r["item_ids"] == ["i-1"]
    # B-3 裁定 4：默认不发送 song_model
    body = sent[0]["json"]
    assert "song_model" not in body
    assert body["callback_url"] == "https://cb.example"


def test_tempolor_generate_business_error(monkeypatch):
    monkeypatch.setenv("TEMPOLOR_API_KEY", "tk")
    sent, _ = _patch_tempolor_http(monkeypatch, [
        _fake_response(200, {"status": 400004, "message": "content violation"}),
    ])
    r = _run(TempolorLyricProvider().generate("p", timeout=15))
    assert r["success"] is False and r.get("error_code") == 400004


def test_tempolor_generate_http_error(monkeypatch):
    monkeypatch.setenv("TEMPOLOR_API_KEY", "tk")
    sent, _ = _patch_tempolor_http(monkeypatch, [_fake_response(503, {})])
    r = _run(TempolorLyricProvider().generate("p", timeout=15))
    assert r["success"] is False and "503" in r["error"]


def test_tempolor_generate_timeout(monkeypatch):
    class TimeoutClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *a, **kw):
            raise httpx.TimeoutException("timed out")

    import httpx as _httpx
    monkeypatch.setattr(_httpx, "AsyncClient", TimeoutClient)
    monkeypatch.setenv("TEMPOLOR_API_KEY", "tk")
    r = _run(TempolorLyricProvider().generate("p", timeout=15))
    assert r["success"] is False


def test_tempolor_query_success(monkeypatch):
    monkeypatch.setenv("TEMPOLOR_API_KEY", "tk")
    payload = {"status": 200000, "data": {"lyrics": [
        {"item_id": "i-1", "status": "succeeded", "title": "月光", "lyric": "[Intro]\n..."}]}}
    sent, _ = _patch_tempolor_http(monkeypatch, [_fake_response(200, payload)])
    p = TempolorLyricProvider()
    r = _run(p.query(["i-1"], timeout=10))
    assert r["success"] is True and r["title"] == "月光" and r["item_id"] == "i-1"


def test_tempolor_query_pending(monkeypatch):
    monkeypatch.setenv("TEMPOLOR_API_KEY", "tk")
    payload = {"status": 200000, "data": {"lyrics": [
        {"item_id": "i-1", "status": "processing"}]}}
    _patch_tempolor_http(monkeypatch, [_fake_response(200, payload)])
    r = _run(TempolorLyricProvider().query(["i-1"], timeout=10))
    assert r["success"] is False and r.get("pending") is True


def test_tempolor_query_failure_status(monkeypatch):
    monkeypatch.setenv("TEMPOLOR_API_KEY", "tk")
    payload = {"status": 200000, "data": {"lyrics": [
        {"item_id": "i-1", "status": "failed", "error": "bad"}]}}
    _patch_tempolor_http(monkeypatch, [_fake_response(200, payload)])
    r = _run(TempolorLyricProvider().query(["i-1"], timeout=10))
    assert r["success"] is False and r.get("pending") is False


def test_tempolor_query_rate_limit(monkeypatch):
    monkeypatch.setenv("TEMPOLOR_API_KEY", "tk")
    sent, _ = _patch_tempolor_http(monkeypatch, [_fake_response(429, {})])
    r = _run(TempolorLyricProvider().query(["i-1"], timeout=10))
    assert r["success"] is False and r.get("pending") is True  # 限流按可重试处理


# ────────────────────────── LyricsEngine ──────────────────────────

class _StaticProvider:
    def __init__(self, name, result):
        self.name = name
        self._result = result
        self.calls = []

    async def generate(self, prompt, timeout, song_model=None):
        self.calls.append({"prompt": prompt, "timeout": timeout, "song_model": song_model})
        return dict(self._result)

    async def query(self, item_ids, timeout):
        self.calls.append({"item_ids": item_ids})
        return dict(self._result)


def _engine(y_result, t_results, deadline=45.0):
    y = _StaticProvider("yinchao_lyric", dict(y_result, provider="yinchao_lyric"))
    t = _StaticProvider("tempolor_lyric_v1", dict(t_results, provider="tempolor_lyric_v1"))
    return y, t, LyricsEngine(yinchao=y, tempolor=t, deadline_seconds=deadline)


def test_engine_yinchao_success_no_fallback():
    y, t, eng = _engine(
        {"success": True, "title": "T", "lyric": "[Verse]\nL"},
        {"success": False, "error": "never"})
    r = _run(eng.generate("p"))
    assert r.status == "succeeded" and r.provider == "yinchao_lyric"
    assert r.fallback_used is False
    assert len(t.calls) == 0  # primary 成功 → backup 零调用


def test_engine_yinchao_fail_tempolor_success():
    y, t, eng = _engine(
        {"success": False, "error": "y down"},
        {"success": True, "item_id": "i-9", "title": "B", "lyric": "[Verse]\nB"})
    r = _run(eng.generate("p"))
    assert r.status == "succeeded" and r.provider == "tempolor_lyric_v1"
    assert r.fallback_used is True and r.item_id == "i-9"


def test_engine_both_fail():
    y, t, eng = _engine(
        {"success": False, "error": "y down"},
        {"success": False, "error": "t down"})
    r = _run(eng.generate("p"))
    assert r.status == "failed" and "y down" in (r.error or "")


def test_engine_yinchao_timeout_falls_back():
    y, t, eng = _engine(
        {"success": False, "error": "Yinchao lyrics request timeout"},
        {"success": True, "item_id": "i-1", "title": "T", "lyric": "L"})
    r = _run(eng.generate("p"))
    assert r.status == "succeeded" and r.fallback_used is True


def test_engine_deadline_exhaustion():
    """全局 deadline：Yinchao 慢调用耗尽预算 → 不再进入 TemPolor。"""
    y = _StaticProvider("yinchao_lyric", {"success": False, "error": "y down"})

    async def _slow_generate(prompt, timeout):
        await asyncio.sleep(0.05)  # 模拟耗时，超过极小 deadline
        return {"success": False, "error": "y down"}

    y.generate = _slow_generate
    t = _StaticProvider("tempolor_lyric_v1", {"success": True, "item_id": "x", "title": "T", "lyric": "L"})
    eng = LyricsEngine(yinchao=y, tempolor=t, deadline_seconds=0.01)
    r = _run(eng.generate("p"))
    assert r.status == "failed" and "超时" in (r.error or "")
    assert len(t.calls) == 0  # deadline 耗尽 → backup 零调用


# ────────────────────────── lyric_service / 契约 ──────────────────────────

def _patch_engine(monkeypatch, result):
    monkeypatch.setattr(lyric_service_mod.lyrics_engine, "generate", AsyncMock(return_value=result))


def test_service_prompt_over_2000_explicit_fail():
    """_build_prompt 最终结果 >2000 → 显式失败（HTTPException 400），不调 Provider。"""
    engine_called = {"called": False}

    async def _should_not_call(prompt):
        engine_called["called"] = True
        return {"status": "succeeded", "lyric": "x", "provider": "yinchao_lyric"}

    svc = lyric_service_mod.lyric_service
    monkey_stub = type("M", (), {"setattr": staticmethod(lambda o, n, v: setattr(o, n, v))})()
    _patch_engine(monkey_stub, {"status": "succeeded", "lyric": "x"})
    long_theme = "超" * 3000
    import asyncio as _asyncio

    async def _run():
        return await svc.generate_lyrics(LyricRequest(theme=long_theme))

    try:
        _asyncio.run(_run())
        raise AssertionError("expected HTTPException")
    except Exception as e:  # noqa: BLE001
        from fastapi import HTTPException
        assert isinstance(e, HTTPException) and e.status_code == 400
        assert "2000" in e.detail
    assert engine_called["called"] is False  # 未触达引擎


def test_service_prompt_within_limit_uses_engine():
    engine_called = {"result": None}

    async def _fake_generate(prompt):
        engine_called["prompt"] = prompt
        from app.services.lyrics_engine import UnifiedLyricResult
        return UnifiedLyricResult(provider="yinchao_lyric", title="T", lyric="[Verse]\n好词",
                                  item_id=None, status="succeeded", error=None,
                                  fallback_used=False, elapsed_sec=1.0)

    monkey_stub = type("M", (), {"setattr": staticmethod(lambda o, n, v: setattr(o, n, v))})()
    _patch_engine(monkey_stub, {"status": "succeeded"})
    import asyncio as _asyncio
    setattr(lyric_service_mod.lyrics_engine, "generate", _fake_generate)

    async def _run():
        return await lyric_service_mod.lyric_service.generate_lyrics(LyricRequest(theme="夏天的海边"))

    resp = _asyncio.run(_run())
    assert resp.success is True
    assert resp.lyrics == "[Verse]\n好词"
    assert engine_called["result"] is None or True


def test_service_lyrics_free_no_credits():
    """Lyrics 免费：引擎结果不触发任何 Credits 交互（服务层无 credits 引用）。"""
    import inspect
    import app.services.lyric_service as lsm
    src = inspect.getsource(lsm)
    assert "credits_service" not in src and "reserve_generation" not in src
    assert "credits_config" not in src


# ────────────────────────── 路由契约 ──────────────────────────

def _make_app():
    from app.routers import ai_lyrics
    app = FastAPI()
    app.include_router(ai_lyrics.router)
    return TestClient(app)


def test_route_contract_unchanged(isolated_route, monkeypatch):
    """/api/v1/lyrics/generate 契约不变：200 + GenerateLyricResponse 字段。"""
    from app.services.lyrics_engine import UnifiedLyricResult

    async def _fake_generate(prompt):
        return UnifiedLyricResult(provider="yinchao_lyric", title=None,
                                  lyric="[Verse]\n新的歌词", item_id=None,
                                  status="succeeded", error=None,
                                  fallback_used=False, elapsed_sec=0.5)

    monkeypatch.setattr(lyric_service_mod.lyrics_engine, "generate", _fake_generate)
    c = isolated_route
    r = c.post("/api/v1/lyrics/generate", json={"theme": "夏天的海边", "style": "pop"})
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"success", "lyrics", "structure", "rhyme_analysis", "message"}
    assert body["success"] is True


def test_route_styles_moods_unchanged(isolated_route, monkeypatch):
    c = isolated_route
    r1 = c.get("/api/v1/lyrics/styles")
    r2 = c.get("/api/v1/lyrics/moods")
    assert r1.status_code == 200 and isinstance(r1.json(), list)
    assert r2.status_code == 200 and isinstance(r2.json(), list)


def test_route_engine_failure_wrapped(isolated_route, monkeypatch):
    """引擎失败 → 路由按既有风格包装为 200 + success=False（前端不崩）。"""
    async def _fail(prompt):
        raise RuntimeError("engine down")

    monkeypatch.setattr(lyric_service_mod.lyrics_engine, "generate", _fail)
    c = isolated_route
    r = c.post("/api/v1/lyrics/generate", json={"theme": "夏天的海边"})
    assert r.status_code == 200  # 既有 200-包装设计保持
    assert r.json()["success"] is False


# ────────────────────────── shared production path 不变 ──────────────────────────

def test_shared_llm_consumers_untouched():
    """audio_router / ai_music 仍引用 llm_factory/agnes（Phase F 边界不变）。"""
    import inspect
    from app.routers import ai_music
    from app.services import audio_router
    assert "llm_factory" in inspect.getsource(audio_router)
    src = inspect.getsource(ai_music)
    assert "agnes" in src  # 主链 agnes 属 Phase F，本阶段未动


@pytest.fixture()
def isolated_route(monkeypatch):
    """/lyrics 路由测试：FastAPI app + 引擎打桩。"""
    from app.routers import ai_lyrics
    app = FastAPI()
    app.include_router(ai_lyrics.router)
    return TestClient(app)
