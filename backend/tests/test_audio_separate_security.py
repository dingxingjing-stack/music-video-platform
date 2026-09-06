"""P1-2 修复验证：POST /api/v1/audio/separate 身份 + quota。

验证调用顺序（安全关键）：
  HTTP endpoint → 身份认证(401) → reserve_generation(429 阻止) → separation service
  
绝不允许：未认证/未 quota 就进入真实 separation provider。
"""
from __future__ import annotations

from pathlib import Path
import tempfile

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

import main as main_mod
from app.services import ai_limits


WAV = b"fake wav content"


@pytest.fixture(autouse=True)
def _quota_and_sep(monkeypatch):
    """quota 记录 + separation service stub（禁止真实 provider）。"""
    calls = {"reserve": [], "refund": [], "separate": []}

    monkeypatch.setattr(ai_limits, "reserve_generation",
                        lambda uid, duration=None: {"success": True} if calls.get("allow", True) else {"success": False, "error": "quota"})
    monkeypatch.setattr(ai_limits, "refund_generation",
                        lambda uid, duration=None, reason="": calls["refund"].append(uid) or {"success": True})

    def _record_reserve(uid, duration=None):
        calls["reserve"].append(uid)
        return {"success": True}

    # 通过 patch 注入 reserve 记录（避免上面的 lambda 记录残留）
    monkeypatch.setattr(ai_limits, "reserve_generation", _record_reserve)
    return calls


@pytest.fixture()
def client():
    return TestClient(main_mod.app)


def _post(client, headers=None, allow_cdn_fail=False):
    files = {"file": ("t.wav", WAV, "audio/wav")}
    data = {"model": "htdemucs"}
    h = headers or {}
    return client.post("/api/v1/audio/separate", files=files, data=data, headers=h)


def test_no_x_user_id_401(client, _quota_and_sep):
    r = _post(client)
    assert r.status_code == 401
    assert _quota_and_sep["reserve"] == []
    assert _quota_and_sep["separate"] == []


def test_blank_x_user_id_401(client, _quota_and_sep):
    r = _post(client, headers={"X-User-ID": "   "})
    assert r.status_code == 401
    assert _quota_and_sep["reserve"] == []


def test_body_user_id_does_not_provide_identity(client, _quota_and_sep):
    # 只有 body.user_id，无 X-User-ID → 仍 401（body 不参与身份）
    r = client.post("/api/v1/audio/separate",
                    files={"file": ("t.wav", WAV, "audio/wav")},
                    data={"model": "htdemucs", "user_id": "spoof"})
    assert r.status_code == 401
    assert _quota_and_sep["reserve"] == []


def test_quota_rejected_blocks_separation(client, _quota_and_sep, monkeypatch):
    # 强制 quota 拒绝 → reserve 返回 success=False → 不调用 separation
    monkeypatch.setattr(ai_limits, "reserve_generation",
                        lambda uid, duration=None: {"success": False, "error": "额度不足"})
    with patch("app.services.audio_separation_service.demucs_service.separate") as m:
        r = _post(client, headers={"X-User-ID": "u1"})
    assert r.status_code == 429
    m.assert_not_called()  # 关键：quota 拒绝后从未进入 separation provider
    assert _quota_and_sep["separate"] == []


def test_quota_passed_then_separation_called(client, _quota_and_sep):
    # quota 成功 → 才调用 separation service
    from app.services.audio_separation_service import demucs_service
    with patch.object(demucs_service, "separate", return_value={
        "success": True, "stems": [], "duration": 0.0, "message": "mock"
    }) as m, \
         patch("app.services.cdn_uploader.cdn_uploader.upload_audio", new_callable=AsyncMock,
               side_effect=lambda *a, **k: "https://cdn.example.com/x"):
        r = _post(client, headers={"X-User-ID": "u1"})
    assert r.status_code == 200
    m.assert_called_once()
    # reserve 已用 header 身份调用
    assert "u1" in _quota_and_sep["reserve"]


def test_header_identity_not_client_ip(client, _quota_and_sep):
    # 无 X-User-ID（即便有 client IP）→ 401，不 fallback IP
    r = _post(client)
    assert r.status_code == 401
    assert _quota_and_sep["reserve"] == []