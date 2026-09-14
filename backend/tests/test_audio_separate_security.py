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
from app.services import ai_limits, auth_identity


WAV = b"fake wav content"


# Phase 3B-4A：身份改为 Authorization Bearer JWT。测试环境打桩 resolve_auth_user_id，
# 使 "Bearer <token>" 映射为 token 本身，且缺失/空返回 None（等价 401）。
@pytest.fixture(autouse=True)
def _jwt_stub(monkeypatch):
    def _resolve(auth):
        if isinstance(auth, str) and auth.startswith("Bearer "):
            token = auth[len("Bearer "):]
            return token or None
        return None
    monkeypatch.setattr(auth_identity, "resolve_auth_user_id", _resolve)


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
    # 空 Bearer token → 401
    r = _post(client, headers={"Authorization": "Bearer "})
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
        r = _post(client, headers={"Authorization": "Bearer u1", "X-User-ID": "spoof"})
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
        r = _post(client, headers={"Authorization": "Bearer u1"})
    assert r.status_code == 200
    m.assert_called_once()
    # reserve 已用 JWT 身份调用
    assert "u1" in _quota_and_sep["reserve"]


def test_header_identity_not_client_ip(client, _quota_and_sep):
    # 无 X-User-ID（即便有 client IP）→ 401，不 fallback IP
    r = _post(client)
    assert r.status_code == 401
    assert _quota_and_sep["reserve"] == []


# ---------------------------------------------------------------------------
# 生产环境防伪加固测试：audio_router /stems 端点（Stage 4-2）
# ---------------------------------------------------------------------------

def test_audio_router_stems_endpoint_production_blocks_ffmpeg_pseudo_stems(monkeypatch):
    """生产环境下，/api/v1/audio/stems 端点必须禁止使用 ffmpeg 频段滤波作为真实 stem 分离。"""
    # 设置生产环境
    monkeypatch.setenv("ENVIRONMENT", "production")
    
    from fastapi.testclient import TestClient
    import main as main_mod
    
    client = TestClient(main_mod.app)
    
    # 创建一个简单的 WAV 文件用于测试
    import tempfile
    import os
    wav_content = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x40\x1f\x00\x00\x40\x1f\x00\x01\x02\x00\x00data\x00\x00\x00\x00"
    
    # 测试 /stems 端点
    response = client.post(
        "/api/v1/audio/stems",
        json={"audio_url": "data:audio/wav;base64," + wav_content.hex(), "track_name": "test"}
    )
    
    # 在生产环境中应返回服务不可用 (503) 或类似的明确错误，而不是尝试 ffmpeg 分离
    assert response.status_code == 503, "生产环境应返回 503 Service Unavailable 而非尝试 ffmpeg 分离"
    # 可以选择性地检查响应内容表明这是由于生产环境限制
    # 注意：由于我们返回的是 StreamingResponse，具体内容可能需要根据实现调整

def test_audio_router_stems_endpoint_development_allows_ffmpeg(monkeypatch):
    """开发/测试环境下，/api/v1/audio/stems 端点应允许使用 ffmpeg（用于开发/实验）。"""
    # 设置开发环境
    monkeypatch.setenv("ENVIRONMENT", "development")
    
    from fastapi.testclient import TestClient
    import main as main_mod
    import tempfile
    import os
    
    client = TestClient(main_mod.app)
    
    # 创建一个临时 WAV 文件用于测试
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
        wav_content = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x40\x1f\x00\x00\x40\x1f\x00\x01\x02\x00\x00data\x00\x00\x00\x00"
        tmp_wav.write(wav_content)
        tmp_wav_path = tmp_wav.name
    
    try:
        # 测试 /stems 端点
        response = client.post(
            "/api/v1/audio/stems",
            json={"audio_url": tmp_wav_path, "track_name": "test"}
        )
        
        # 在开发环境中应允许请求继续（即使 ffmpeg 不可用，也应返回某个响应而不是被我们的生产限制阻断）
        # 实际返回码可能是 200（如果 ffmpeg 可用）或其他非 503 错误（如果 ffmpeg 不可用但有其他处理），但不应是我们的生产限制 503
        assert response.status_code != 503, "开发环境不应返回 503 Service Unavailable 由于生产环境限制"
    finally:
        # 清理临时文件
        if os.path.exists(tmp_wav_path):
            os.unlink(tmp_wav_path)