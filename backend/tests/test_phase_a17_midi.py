"""P4-B2 Phase A-17 测试：MIDI 正式接入（TemPolor midi v1，registry-only → 端点就绪）。

覆盖 A-17 授权 §五/§六/§八：
- 契约（2026-10-03 官方文档复核）：POST /open-apis/v1/midi body={url, callback_url} →
  item_ids；POST /open-apis/v1/midi/query body={"item_ids": [...]}；data.midis[] 含
  status/midi_url；业务码字段 status（非 code）；鉴权裸 Key；
- 产物：midi_url → midi.zip（非音频 → 不适用 240s 门）；zip 完整性校验 + 危险成员名拒绝；
- Credits：midi 未定价（credit_cost=0）→ /midi/convert fail-closed 503 midi_not_priced，
  绝不免费放行；退款复用既有幂等体系（端点结构镜像 /stems/separate）；
- 回调 URL 派生：…/tempolor/midi/callback（不匹配 /callback 结尾 → fail-closed）。

全部 mock，零真实 API、零费用。
"""
from __future__ import annotations

import asyncio
import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import ai_music
from app.services import (
    tempolor_midi_service as midi_service,
    task_store,
)
from app.services.credits_config import get_credit_cost

SENTINEL_KEY = "SENTINEL-tempolor-key-never-log"


def _mock_client_factory(service, monkeypatch, handler):
    real_client = httpx.AsyncClient

    def factory(**kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(**kwargs)

    monkeypatch.setattr(service.httpx, "AsyncClient", factory)


def _stub_r2_uploader(monkeypatch, uploaded):
    import app.services.cdn_uploader as cdn_mod

    async def fake_upload_private(local_path, key):
        uploaded[key] = local_path

    def fake_presign(key, expires_in=600):
        return f"https://r2.example/{key}?sig=test"

    monkeypatch.setattr(cdn_mod.cdn_uploader, "upload_private", fake_upload_private)
    monkeypatch.setattr(cdn_mod.cdn_uploader, "get_presigned_download_url", fake_presign)


@pytest.fixture()
def midi_env(monkeypatch):
    monkeypatch.setenv("TEMPOLOR_API_KEY", SENTINEL_KEY)
    monkeypatch.setenv("TEMPOLOR_CALLBACK_SECRET", "cb-secret")
    monkeypatch.setenv("TEMPOLOR_CALLBACK_URL", "https://melovar.example/api/v1/ai/tempolor/callback")
    monkeypatch.setattr(midi_service, "MIDI_FIRST_POLL_DELAY_SECONDS", 0.01)
    monkeypatch.setattr(midi_service, "MIDI_POLL_INTERVAL_SECONDS", 0.01)


# ── 1) 回调 URL 派生 ─────────────────────────────────────────────────────

def test_midi_callback_url_derivation(midi_env, monkeypatch):
    url = midi_service.effective_midi_callback_url()
    assert "/tempolor/midi/callback" in url
    assert "token=cb-secret" in url


def test_midi_callback_derivation_fail_closed(monkeypatch):
    monkeypatch.setenv("TEMPOLOR_CALLBACK_URL", "https://melovar.example/no-trailing-callback")
    with pytest.raises(midi_service.MidiError):
        midi_service.effective_midi_callback_url()


# ── 2) 提交契约 ──────────────────────────────────────────────────────────

def test_submit_midi_contract(midi_env, monkeypatch, tmp_path):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["payload"] = json.loads(request.content)
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"status": 200000, "data": {"item_ids": ["mid_1"]}})

    _mock_client_factory(midi_service, monkeypatch, handler)
    _stub_r2_uploader(monkeypatch, {})

    input_file = tmp_path / "in.mp3"
    input_file.write_bytes(b"\x00" * 4096)
    item = asyncio.run(midi_service.submit_midi(str(input_file), "midi-t1"))
    assert item == "mid_1"
    assert captured["path"] == "/open-apis/v1/midi"
    assert captured["auth"] == SENTINEL_KEY  # 裸 Key，无 Bearer
    assert set(captured["payload"].keys()) == {"url", "callback_url"}
    assert captured["payload"]["callback_url"]  # 官方强制非空


def test_submit_midi_business_error(midi_env, monkeypatch, tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": 400003, "message": "callback_url not blank"})

    _mock_client_factory(midi_service, monkeypatch, handler)
    _stub_r2_uploader(monkeypatch, {})
    input_file = tmp_path / "in.mp3"
    input_file.write_bytes(b"\x00" * 4096)
    with pytest.raises(midi_service.MidiError):
        asyncio.run(midi_service.submit_midi(str(input_file), "midi-t2"))


# ── 3) 轮询契约 ──────────────────────────────────────────────────────────

def test_poll_midi_success(midi_env, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/open-apis/v1/midi/query"
        assert json.loads(request.content) == {"item_ids": ["mid_1"]}
        return httpx.Response(200, json={
            "status": 200000,
            "data": {"midis": [{"item_id": "mid_1", "status": "succeeded",
                                 "midi_url": "https://cdn.example/m.zip"}]},
        })

    _mock_client_factory(midi_service, monkeypatch, handler)
    url = asyncio.run(midi_service.poll_midi("mid_1", "midi-t3"))
    assert url == "https://cdn.example/m.zip"


def test_poll_midi_failure_status(midi_env, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "status": 200000,
            "data": {"midis": [{"item_id": "mid_1", "status": "failed"}]},
        })

    _mock_client_factory(midi_service, monkeypatch, handler)
    with pytest.raises(midi_service.MidiError):
        asyncio.run(midi_service.poll_midi("mid_1", "midi-t4"))


def test_poll_midi_timeout(midi_env, monkeypatch):
    monkeypatch.setattr(midi_service, "MIDI_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(midi_service, "MIDI_FIRST_POLL_DELAY_SECONDS", 0.02)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "status": 200000,
            "data": {"midis": [{"item_id": "mid_1", "status": "running"}]},
        })

    _mock_client_factory(midi_service, monkeypatch, handler)
    with pytest.raises(midi_service.MidiError, match="timeout"):
        asyncio.run(midi_service.poll_midi("mid_1", "midi-t5"))


# ── 4) zip 下载与校验 ────────────────────────────────────────────────────

def _make_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("melody.mid", b"MThd\x00\x00\x00\x06" + __import__("os").urandom(4096))
        zf.writestr("README.txt", b"ok")
    return buf.getvalue()


def test_download_midi_zip_valid(midi_env, monkeypatch, tmp_path):
    payload = _make_zip_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)

    monkeypatch.setattr(midi_service.httpx, "AsyncClient",
                        lambda **kw: _wrap(kw, handler))
    out = asyncio.run(midi_service.download_midi_zip("https://cdn.example/m.zip", str(tmp_path)))
    assert Path(out).exists()


def test_download_midi_zip_rejects_unsafe_members(midi_env, monkeypatch, tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("../evil.mid", b"x")
    payload = buf.getvalue()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)

    monkeypatch.setattr(midi_service.httpx, "AsyncClient",
                        lambda **kw: _wrap(kw, handler))
    with pytest.raises(midi_service.MidiError):
        asyncio.run(midi_service.download_midi_zip("https://cdn.example/m.zip", str(tmp_path)))


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _wrap(kwargs, handler):
    kwargs["transport"] = httpx.MockTransport(handler)
    return _REAL_ASYNC_CLIENT(**kwargs)


# ── 5) 端到端编排 ────────────────────────────────────────────────────────

def test_run_midi_task_end_to_end(midi_env, monkeypatch, tmp_path):
    uploaded = {}
    _stub_r2_uploader(monkeypatch, uploaded)
    zip_payload = _make_zip_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/midi"):
            return httpx.Response(200, json={"status": 200000, "data": {"item_ids": ["mid_9"]}})
        if request.url.path.endswith("/midi/query"):
            return httpx.Response(200, json={
                "status": 200000,
                "data": {"midis": [{"item_id": "mid_9", "status": "succeeded",
                                     "midi_url": "https://cdn.example/m.zip"}]},
            })
        return httpx.Response(200, content=zip_payload)

    _mock_client_factory(midi_service, monkeypatch, handler)
    input_file = tmp_path / "in.mp3"
    input_file.write_bytes(b"\x00" * 4096)

    manifest = asyncio.run(midi_service.run_midi_task("midi-e2e-1", str(input_file)))
    assert manifest["midi_zip"] == "music/midi-e2e-1/midi.zip"


# ── 6) 端点层：fail-closed 定价门 ────────────────────────────────────────

@pytest.fixture()
def client(monkeypatch, tmp_path):
    from app.services import ai_limits, credits_service
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.services.auth_identity import get_verified_user_id

    db = str(tmp_path / "a17_midi.db")
    monkeypatch.setattr(task_store, "_DB_PATH", db)
    monkeypatch.setattr(ai_limits, "_DB_PATH", db)
    eng = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    from app.db.database import Base
    Base.metadata.create_all(bind=eng)
    monkeypatch.setattr(credits_service, "SessionLocal", sessionmaker(bind=eng))

    app = FastAPI()
    app.include_router(ai_music.router)
    app.dependency_overrides[get_verified_user_id] = lambda: "a17-midi-user"
    return TestClient(app)


def test_midi_convert_unpriced_fail_closed(client):
    assert get_credit_cost("midi") is None
    files = {"file": ("in.mp3", b"\x00" * 4096, "audio/mpeg")}
    resp = client.post("/api/v1/ai/midi/convert", files=files)
    assert resp.status_code == 503
    assert resp.json()["detail"] == "midi_not_priced"


def test_midi_task_endpoint_rejects_foreign_prefix(client):
    resp = client.get("/api/v1/ai/midi/task/song-not-midi")
    assert resp.status_code == 404
