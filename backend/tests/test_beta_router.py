"""测试：Beta 路由参数校验 + JWT 身份（consume-credit 负数/0/超上限拒绝、缺 Authorization 拒绝）。

使用隔离 SQLite，不连接生产数据库。
Phase 3B-4B：身份改为 Authorization Bearer JWT（无 JWT → 401）。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import beta
from app.services import beta_service, auth_identity


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """构建一个只挂 beta 路由的测试 app，并指向隔离 SQLite；打桩 JWT 解析。"""
    db_path = str(tmp_path / "test_beta_router.db")
    monkeypatch.setattr(beta_service, "DB_DIR", str(tmp_path))
    monkeypatch.setattr(beta_service, "DB_PATH", db_path)
    beta_service._init_db()

    def _resolve(auth):
        if isinstance(auth, str) and auth.startswith("Bearer "):
            return auth[len("Bearer "):] or None
        return None
    monkeypatch.setattr(auth_identity, "resolve_auth_user_id", _resolve)

    app = FastAPI()
    app.include_router(beta.router)
    return TestClient(app)


def _h(uid="u1"):
    return {"Authorization": f"Bearer {uid}"}


def test_consume_credit_negative_amount_rejected(client):
    r = client.post("/api/v1/beta/consume-credit", json={"amount": -5}, headers=_h())
    assert r.status_code == 422


def test_consume_credit_zero_amount_rejected(client):
    r = client.post("/api/v1/beta/consume-credit", json={"amount": 0}, headers=_h())
    assert r.status_code == 422


def test_consume_credit_over_upper_limit_rejected(client):
    r = client.post("/api/v1/beta/consume-credit", json={"amount": 11}, headers=_h())
    assert r.status_code == 422


def test_consume_credit_amount_one_accepted(client):
    r = client.post("/api/v1/beta/consume-credit", json={"amount": 1}, headers=_h())
    assert r.status_code == 200


def test_consume_credit_missing_jwt_rejected(client):
    """缺少 Authorization → 401（fail-closed）。"""
    r = client.post("/api/v1/beta/consume-credit", json={"amount": 1})
    assert r.status_code == 401


def test_status_with_user(client):
    r = client.get("/api/v1/beta/status", headers=_h("u_status"))
    assert r.status_code == 200
    body = r.json()
    assert body["is_gray"] is False
    assert body["can_apply"] is False


def test_identity_from_jwt_not_xheader(client):
    """Bearer(A) + X-User-ID(B) → 使用 A。"""
    r = client.post(
        "/api/v1/beta/consume-credit",
        json={"amount": 1},
        headers={"Authorization": "Bearer id_from_jwt", "X-User-ID": "forged"},
    )
    assert r.status_code == 200
    # 确认额度记在 JWT 身份上
    status = client.get("/api/v1/beta/status", headers={"Authorization": "Bearer id_from_jwt"})
    assert status.status_code == 200
    assert status.json()["total_generations"] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])