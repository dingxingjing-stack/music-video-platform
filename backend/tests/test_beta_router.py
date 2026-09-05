"""测试：Beta 路由参数校验（consume-credit 负数/0/超上限拒绝、缺 X-User-ID 拒绝）。

使用隔离 SQLite，不连接生产数据库。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import beta
from app.services import beta_service


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """构建一个只挂 beta 路由的测试 app，并指向隔离 SQLite。"""
    db_path = str(tmp_path / "test_beta_router.db")
    monkeypatch.setattr(beta_service, "DB_DIR", str(tmp_path))
    monkeypatch.setattr(beta_service, "DB_PATH", db_path)
    beta_service._init_db()

    app = FastAPI()
    app.include_router(beta.router)
    return TestClient(app)


def test_consume_credit_negative_amount_rejected(client):
    """负数 amount 应返回 422（pydantic gt=0 校验失败）。"""
    r = client.post("/api/v1/beta/consume-credit", json={"amount": -5}, headers={"X-User-ID": "u1"})
    assert r.status_code == 422


def test_consume_credit_zero_amount_rejected(client):
    """0 amount 应返回 422。"""
    r = client.post("/api/v1/beta/consume-credit", json={"amount": 0}, headers={"X-User-ID": "u1"})
    assert r.status_code == 422


def test_consume_credit_over_upper_limit_rejected(client):
    """超过上限（>10）应返回 422。"""
    r = client.post("/api/v1/beta/consume-credit", json={"amount": 11}, headers={"X-User-ID": "u1"})
    assert r.status_code == 422


def test_consume_credit_amount_one_accepted(client):
    """amount=1（默认）应被接受。"""
    r = client.post("/api/v1/beta/consume-credit", json={"amount": 1}, headers={"X-User-ID": "u1"})
    assert r.status_code == 200


def test_consume_credit_missing_user_rejected(client):
    """缺少 X-User-ID 应返回 400（拒绝误扣共享额度，不默认 beta_user）。"""
    r = client.post("/api/v1/beta/consume-credit", json={"amount": 1})
    assert r.status_code == 400


def test_consume_credit_does_not_default_to_beta_user(client):
    """未带 X-User-ID 时不应扣 'beta_user' 的额度。"""
    r = client.post("/api/v1/beta/consume-credit", json={"amount": 1})
    assert r.status_code == 400
    # 确认 'beta_user' 没有被误扣
    status = client.get("/api/v1/beta/status", headers={"X-User-ID": "beta_user"})
    assert status.status_code == 200
    assert status.json()["daily_credits_used"] == 0


def test_status_with_user(client):
    """GET /api/v1/beta/status 返回 200 与安全默认（fail-closed）。"""
    r = client.get("/api/v1/beta/status", headers={"X-User-ID": "u_status"})
    assert r.status_code == 200
    body = r.json()
    assert body["is_gray"] is False
    assert body["can_apply"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])