"""P4-B2 Phase A-17 测试：歌词继续写主链切换（Agnes/Gemini/NVIDIA → 音潮）。

覆盖 A-17 授权 §一/§十三：
- 语义：/api/v1/audio/lyrics = 已有歌词片段的文本续写（非 song/extend、非 AI 写词）；
- 主链：llm_factory（Agnes）调用点已从 /lyrics 与 /lyrics/stream 移除；
- 编排：复用 lyrics_engine（音潮主 → 天谱乐备，45s hard deadline）；
- 契约：HTTP 200 + {"lyrics": ...}；失败返回兜底文案 + error；空/超长片段 → 400；
- 隔离：AI 写词（/api/v1/lyrics/generate → lyric_service）不受影响。

全部 mock，零真实 API、零费用。
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import audio_router as audio_router_mod
from app.services import lyrics_engine as lyrics_engine_mod
from app.services.lyrics_engine import UnifiedLyricResult


USER = "a17-lyrics-user"


@pytest.fixture()
def client(monkeypatch):
    app = FastAPI()
    app.include_router(audio_router_mod.router)
    return TestClient(app)


def _ok(provider="yinchao_lyric", lyric="风把梦吹向远方\n心跳与节奏同响"):
    return UnifiedLyricResult(
        provider=provider, title=None, lyric=lyric, item_id=None,
        status="succeeded", error=None, fallback_used=(provider != "yinchao_lyric"),
        elapsed_sec=0.5,
    )


def _fail(error="down"):
    return UnifiedLyricResult(
        provider="", title=None, lyric="", item_id=None,
        status="failed", error=error, fallback_used=True, elapsed_sec=1.0,
    )


@pytest.fixture()
def llm_touched(monkeypatch):
    """哨兵：若歌词继续写链路再触碰 llm_factory 即测试失败（A-17 禁令）。"""
    state = {"touched": False}

    class _Sentinel:
        async def call(self, *a, **kw):
            state["touched"] = True
            raise AssertionError("llm_factory 不得出现在歌词继续写调用链（A-17）")

    import app.services.inference.llm_factory as lf
    monkeypatch.setattr(lf, "llm_factory", _Sentinel(), raising=False)
    return state


# ── 1) 成功路径 ──────────────────────────────────────────────────────────

def test_lyrics_completion_success_primary(client, monkeypatch, llm_touched):
    captured = {}

    async def fake_generate(prompt):
        captured["prompt"] = prompt
        return _ok()

    monkeypatch.setattr(lyrics_engine_mod.lyrics_engine, "generate", fake_generate)
    resp = client.post("/lyrics", json={"prompt": "夜色温柔", "style": "流行", "language": "中文"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["lyrics"].startswith("风把梦")
    assert data["provider"] == "yinchao_lyric"
    # 续写语义：已有片段 + 续写指令进入 prompt（而非仅主题）
    assert "夜色温柔" in captured["prompt"]
    assert "续写" in captured["prompt"]
    assert llm_touched["touched"] is False


def test_lyrics_completion_fallback_provider(client, monkeypatch, llm_touched):
    async def fake_generate(prompt):
        return _ok(provider="tempolor_lyric_v1")

    monkeypatch.setattr(lyrics_engine_mod.lyrics_engine, "generate", fake_generate)
    resp = client.post("/lyrics", json={"prompt": "第一段歌词"})
    assert resp.status_code == 200
    assert resp.json()["provider"] == "tempolor_lyric_v1"
    assert llm_touched["touched"] is False


# ── 2) 失败路径（契约与既有前端一致：200 + 兜底文案）────────────────────

def test_lyrics_completion_engine_failure(client, monkeypatch):
    async def fake_generate(prompt):
        return _fail("primary: x；backup: y")

    monkeypatch.setattr(lyrics_engine_mod.lyrics_engine, "generate", fake_generate)
    resp = client.post("/lyrics", json={"prompt": "片段"})
    assert resp.status_code == 200
    data = resp.json()
    assert "暂不可用" in data["lyrics"]
    assert data["error"]


def test_lyrics_completion_engine_exception(client, monkeypatch):
    async def boom(prompt):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(lyrics_engine_mod.lyrics_engine, "generate", boom)
    resp = client.post("/lyrics", json={"prompt": "片段"})
    assert resp.status_code == 200
    assert "暂不可用" in resp.json()["lyrics"]


# ── 3) 输入校验 ──────────────────────────────────────────────────────────

def test_lyrics_completion_empty_fragment(client):
    resp = client.post("/lyrics", json={"prompt": "   "})
    assert resp.status_code == 400


def test_lyrics_completion_too_long_fragment(client):
    resp = client.post("/lyrics", json={"prompt": "长" * 2001})
    assert resp.status_code == 400
    assert "过长" in resp.json()["error"]


# ── 4) SSE 端点 ──────────────────────────────────────────────────────────

def test_lyrics_stream_success(client, monkeypatch):
    async def fake_generate(prompt):
        return _ok()

    monkeypatch.setattr(lyrics_engine_mod.lyrics_engine, "generate", fake_generate)
    resp = client.post("/lyrics/stream", json={"prompt": "片段"})
    assert resp.status_code == 200
    events = [l for l in resp.text.splitlines() if l.startswith("data: ")]
    payload = json.loads(events[0][len("data: "):])
    assert payload["text"].startswith("风把梦")
    assert events[-1] == "data: [DONE]"


def test_lyrics_stream_engine_failure(client, monkeypatch):
    async def fake_generate(prompt):
        return _fail("deadline")

    monkeypatch.setattr(lyrics_engine_mod.lyrics_engine, "generate", fake_generate)
    resp = client.post("/lyrics/stream", json={"prompt": "片段"})
    assert resp.status_code == 200
    events = [l for l in resp.text.splitlines() if l.startswith("data: ")]
    assert "error" in json.loads(events[0][len("data: "):])


def test_lyrics_stream_empty_fragment(client):
    resp = client.post("/lyrics/stream", json={"prompt": ""})
    assert resp.status_code == 200
    events = [l for l in resp.text.splitlines() if l.startswith("data: ")]
    assert "error" in json.loads(events[0][len("data: "):])


# ── 5) 隔离：AI 写词路由不受 A-17 影响 ───────────────────────────────────

def test_ai_lyric_generation_route_still_lyrics_engine(client, monkeypatch):
    """AI 写词（/api/v1/lyrics/generate）语义独立：A-17 不改它，也不经 /audio/lyrics。"""
    from app.routers import ai_lyrics as ai_lyrics_router
    from app.services import lyric_service as lyric_service_mod

    app2 = FastAPI()
    app2.include_router(ai_lyrics_router.router)
    c2 = TestClient(app2)

    async def fake_generate(prompt):
        return _ok()

    monkeypatch.setattr(lyric_service_mod.lyrics_engine, "generate", fake_generate)
    resp = c2.post("/api/v1/lyrics/generate", json={"theme": "夏天的海边"})
    assert resp.status_code == 200
    assert resp.json()["lyrics"]
