"""P2-2 修复验证：voice_clone HTTP 路由身份边界（X-User-ID）。

用户资源接口（voices / clone-quota / upload / clone）：
  - 无 X-User-ID → 401
  - 空白 X-User-ID → 401
  - query/body 伪造 user_id → 不能绕过
  - client.host/IP → 不能作为身份
  - 合法 X-User-ID → 进入原业务逻辑
/ presets 为静态公开接口，仍无需认证。

全部用 stub service，不触真实 GPU/provider。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import main as main_mod
from app.services import voice_clone_service as _vcs
from app.services import auth_identity

# 完整路径（voice_clone.router 以 /api/v1 前缀挂载）
BASE = "/api/v1/voice"


@pytest.fixture(autouse=True)
def _jwt_stub(monkeypatch):
    """Phase 3B-4B：身份改为 Authorization Bearer JWT。打桩 resolve_auth_user_id。"""
    def _resolve(auth):
        if isinstance(auth, str) and auth.startswith("Bearer "):
            return auth[len("Bearer "):] or None
        return None
    monkeypatch.setattr(auth_identity, "resolve_auth_user_id", _resolve)


@pytest.fixture(autouse=True)
def _stub_service(monkeypatch):
    """stub 业务方法，禁止真实逻辑/GPU；并记录调用到的 user_key。"""
    rec = {"list": [], "quota": [], "upload": [], "clone": []}

    # VoiceSample 结构：id, name, audio_url, duration, created_at, is_private, owner_id, prompt_text, prompt_language
    monkeypatch.setattr(_vcs.voice_clone_service, "list_voices",
                        lambda uid: rec["list"].append(uid) or [])
    
    # QuotaInfo: used, limit, can_clone
    monkeypatch.setattr(_vcs.voice_clone_service, "get_quota",
                        lambda uid: rec["quota"].append(uid) or {"used": 0, "limit": 1, "can_clone": True})
    
    # VoiceSample for upload
    monkeypatch.setattr(_vcs.voice_clone_service, "upload_voice",
                        lambda url, name, uid: rec["upload"].append(uid) or {
                            "id": "v1", "name": name or "test", "audio_url": url,
                            "duration": 30.0, "created_at": "2024-01-01T00:00:00",
                            "is_private": True, "owner_id": uid, "prompt_text": "", "prompt_language": ""
                        })
    
    # VoiceCloneResponse for clone
    async def _mock_clone(req):
        rec["clone"].append(None)
        return {"success": True, "audio_url": "https://mock/clone.wav", "duration": 5.0,
                "voice_id": req.voice_id, "error": None, "message": "ok"}
    
    monkeypatch.setattr(_vcs.voice_clone_service, "clone_voice", _mock_clone)
    
    # presets - static list of VoiceSample
    monkeypatch.setattr(_vcs.voice_clone_service, "presets", [], raising=False)
    return rec


@pytest.fixture()
def client():
    return TestClient(main_mod.app)


def _req(client, path, method="get", headers=None):
    if path == "/upload":
        # /upload 必须带必需的 audio_url query 参数，才能到达身份检查
        return client.post(f"{BASE}{path}?audio_url=https://x/a.wav", headers=headers)
    if method == "get":
        return client.get(BASE + path, headers=headers)
    return client.post(BASE + path, headers=headers, json={"text": "hi"})


# ── 无 Authorization → 401（用户资源接口） ─────────────────────────────
@pytest.mark.parametrize("path", ["/voices", "/clone-quota", "/upload", "/clone"])
def test_no_x_user_id_401(client, path):
    method = "post" if path in ("/upload", "/clone") else "get"
    r = _req(client, path, method)
    assert r.status_code == 401, f"{path} 应 401, got {r.status_code}"


# ── 空 Bearer token → 401 ──────────────────────────────────────────────
@pytest.mark.parametrize("path", ["/voices", "/clone-quota", "/upload", "/clone"])
def test_blank_x_user_id_401(client, path):
    method = "post" if path in ("/upload", "/clone") else "get"
    r = _req(client, path, method, headers={"Authorization": "Bearer "})
    assert r.status_code == 401


# ── query 伪造 user_id 不能绕过（仍看 JWT） ────────────────────────────
def test_query_user_id_cannot_bypass(client):
    # upload 带 query user_id=attacker，无 Authorization → 401
    r = client.post(f"{BASE}/upload?user_id=attacker&audio_url=https://x/y.wav")
    assert r.status_code == 401
    # voices 带 query user_id → 401
    r = client.get(f"{BASE}/voices?user_id=attacker")
    assert r.status_code == 401


# ── body 伪造 user_id 不能绕过（clone 有 body） ────────────────────────
def test_body_user_id_cannot_bypass(client):
    r = client.post(f"{BASE}/clone", json={"text": "hi", "user_id": "attacker"})
    assert r.status_code == 401


# ── 合法 JWT → 进入业务逻辑，且身份即 verified id ─────────────────────
def test_valid_x_user_id_reaches_business(client, _stub_service):
    h = {"Authorization": "Bearer legit-user"}
    r = client.get(f"{BASE}/voices", headers=h)
    assert r.status_code == 200
    assert _stub_service["list"] == ["legit-user"]

    r = client.get(f"{BASE}/clone-quota", headers=h)
    assert r.status_code == 200
    assert _stub_service["quota"] == ["legit-user"]

    r = client.post(f"{BASE}/upload?audio_url=https://x/a.wav", headers=h)
    assert r.status_code == 200
    assert _stub_service["upload"] == ["legit-user"]


# ── 有 JWT 时 X-User-ID 不参与身份（JWT 优先） ─────────────────────────
def test_header_beats_query_user_id(client, _stub_service):
    r = client.get(f"{BASE}/voices?user_id=attacker",
                   headers={"Authorization": "Bearer real", "X-User-ID": "forged"})
    assert r.status_code == 200
    assert _stub_service["list"] == ["real"]


# ── presets 公开，无需认证 ────────────────────────────────────────────
def test_presets_public(client, _stub_service):
    r = client.get(f"{BASE}/presets")
    assert r.status_code == 200