"""
Phase 3B-4C 验收测试：cdn_upload 身份收尾（不触真实 CDN/R2）。

注：`app/routers/user_age.py` 为未挂载的死代码；live `/api/v1/user/age` 由
`app/services/user_router.py` 提供（仍 X-User-ID），属范围外，单独待决。

覆盖：
  - 无 JWT → 401（上传/预签名）
  - 有 JWT(A) → 200
  - JWT(A) + X-User-ID(B) → 仍 A（忽略 X-User-ID）
  - /cdn/info 保持公开匿名
"""
import pytest
from fastapi.testclient import TestClient

import main as main_mod
from app.services import auth_identity
from app.services import cdn_uploader as _cdn

client = TestClient(main_mod.app)

A = "00000000-0000-4000-8000-0000000000aa"
B = "00000000-0000-4000-8000-0000000000bb"


@pytest.fixture(autouse=True)
def _jwt_stub(monkeypatch):
    def _resolve(auth):
        if isinstance(auth, str) and auth.startswith("Bearer "):
            return auth[len("Bearer "):] or None
        return None
    monkeypatch.setattr(auth_identity, "resolve_auth_user_id", _resolve)


@pytest.fixture(autouse=True)
def _cdn_stub(monkeypatch):
    """stub cdn 上传，避免真实 R2/S3/本地写入。"""
    async def _upload(path, file_type):
        return "https://cdn.example.com/stub/file.wav"
    monkeypatch.setattr(_cdn, "upload_to_cdn", _upload)
    monkeypatch.setattr(_cdn.cdn_uploader, "get_upload_url",
                        lambda ft, fe: {"upload_url": "https://cdn.example.com/put", "file_key": "k", "cdn_url": "https://cdn.example.com/k", "provider": "r2"})


def test_cdn_upload_no_jwt_401():
    r = client.post("/api/v1/cdn/upload", files={"file": ("t.wav", b"x", "audio/wav")}, data={"file_type": "audio"})
    assert r.status_code == 401


def test_cdn_presigned_no_jwt_401():
    r = client.post("/api/v1/cdn/presigned-url", data={"file_type": "audio", "file_ext": ".wav"})
    assert r.status_code == 401


def test_cdn_upload_jwt_ok():
    r = client.post("/api/v1/cdn/upload", files={"file": ("t.wav", b"x", "audio/wav")},
                    data={"file_type": "audio"}, headers={"Authorization": f"Bearer {A}", "X-User-ID": B})
    assert r.status_code == 200, r.text


def test_cdn_presigned_jwt_ok():
    r = client.post("/api/v1/cdn/presigned-url", data={"file_type": "audio", "file_ext": ".wav"},
                    headers={"Authorization": f"Bearer {A}", "X-User-ID": B})
    assert r.status_code == 200, r.text


def test_cdn_info_public():
    r = client.get("/api/v1/cdn/info")
    assert r.status_code == 200


# ── user_router /api/v1/user/age（live 端点）JWT 身份 ──────────────────
import app.services.user_router as _ur  # noqa: E402


@pytest.fixture()
def _age_lookup(monkeypatch):
    """stub 按 supabase_user_id 查 profile，返回 age=20，并记录被查 id。"""
    seen = {}

    def _get(uid):
        seen["uid"] = uid
        return {"age": 20}

    monkeypatch.setattr(_ur, "_get_user_by_supabase_id", lambda: _get)
    return seen


def test_user_age_live_no_jwt_401():
    r = client.get("/api/v1/user/age")
    assert r.status_code == 401


def test_user_age_live_x_user_id_alone_401():
    r = client.get("/api/v1/user/age", headers={"X-User-ID": B})
    assert r.status_code == 401


def test_user_age_live_jwt_a_uses_supabase_id(_age_lookup):
    r = client.get("/api/v1/user/age", headers={"Authorization": f"Bearer {A}", "X-User-ID": B})
    assert r.status_code == 200
    assert r.json()["age"] == 20
    assert _age_lookup["uid"] == A  # 身份用 JWT A，忽略 X-User-ID B