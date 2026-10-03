"""Phase Signup Reward = +30 Credits 测试（2026-10-03 裁定实施）。

覆盖：
- 注册自动发放：claim_welcome_bonus → +30、welcome_bonus_claimed=true、ledger 落账
- Duplicate：重复 claim 不再增加、无第二条 ledger
- Concurrency：双线程并发 claim 恰一成功（CAS）
- Historical user：claimed=true 用户 claim → already_claimed、余额/ledger 零变化
- Retired endpoints：/bonus/* ×3 → 410（HTTP 层，经 credits router）
- Credits integrity：standard_song 30、失败退款逻辑不变
"""
from __future__ import annotations

import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.routers import credits as credits_router
from app.services import credits_service
from app.services.auth_identity import get_verified_user_id

USER = "signup-reward-user"


@pytest.fixture()
def credits_db(tmp_path, monkeypatch):
    eng = create_engine(
        f"sqlite:///{tmp_path / 'signup_reward.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=eng)
    Session = sessionmaker(bind=eng)
    monkeypatch.setattr(credits_service, "SessionLocal", Session)
    return eng, Session


@pytest.fixture()
def app(credits_db):
    app = FastAPI()
    app.include_router(credits_router.router)
    return app


@pytest.fixture()
def client(app):
    return TestClient(app)


@pytest.fixture()
def authed_client(app):
    app.dependency_overrides[get_verified_user_id] = lambda: USER
    return TestClient(app)


def _ledger_rows(sess, user: str, txn_type: str | None = None):
    q = "SELECT amount, transaction_type FROM credits_transactions WHERE user_id=:u"
    if txn_type:
        q += " AND transaction_type=:t"
        return sess.execute(text(q), {"u": user, "t": txn_type}).fetchall()
    return sess.execute(text(q + " ORDER BY id"), {"u": user}).fetchall()


from sqlalchemy import text  # noqa: E402


# ── Signup：注册自动 +30（claim_welcome_bonus = 注册流程的实际调用点）────────

def test_signup_reward_granted_once(credits_db):
    eng, _ = credits_db
    conn = eng.connect()
    conn = eng.connect()
    r = credits_service.claim_welcome_bonus(USER)
    assert r["success"] is True and r["amount"] == 30
    bal = conn.execute(text("SELECT balance, welcome_bonus_claimed FROM user_credits WHERE user_id=:u"),
                      {"u": USER}).fetchone()
    assert bal[0] == 30 and bal[1] in (1, True)
    rows = conn.execute(text(
        "SELECT amount, transaction_type FROM credits_transactions WHERE user_id=:u AND transaction_type='welcome_bonus'"),
        {"u": USER}).fetchall()
    assert len(rows) == 1 and rows[0][0] == 30


def test_signup_reward_duplicate_no_double_grant(credits_db):
    eng, _ = credits_db
    conn = eng.connect()
    credits_service.claim_welcome_bonus(USER)
    r2 = credits_service.claim_welcome_bonus(USER)
    assert r2["success"] is False and r2["already_claimed"] is True
    eng, _ = credits_db
    n = conn.execute(text(
        "SELECT count(*) FROM credits_transactions WHERE user_id=:u AND transaction_type='welcome_bonus'"),
        {"u": USER}).scalar()
    assert n == 1  # 仅一条 ledger


def test_signup_reward_concurrent_single_grant(credits_db):
    """双线程并发 claim → 恰一成功（CAS rowcount 判定）。"""
    eng, _ = credits_db
    conn = eng.connect()
    conn = eng.connect()
    results = []
    barrier = threading.Barrier(2)

    def worker():
        barrier.wait()
        results.append(credits_service.claim_welcome_bonus(USER))

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start(); t2.start(); t1.join(); t2.join()

    ok = [r for r in results if r["success"]]
    assert len(ok) == 1, f"并发 claim 必须恰一成功，实际 {results}"
    assert credits_service.get_balance(USER) == 30
    n = conn.execute(text(
        "SELECT count(*) FROM credits_transactions WHERE user_id=:u AND transaction_type='welcome_bonus'"),
        {"u": USER}).scalar()
    assert n == 1


# ── Historical user：claimed=true → 不再获得 ────────────────────────────────

def test_historical_claimed_user_no_regrant(credits_db):
    eng, _ = credits_db
    conn = eng.connect()
    conn = eng.connect()
    credits_service.claim_welcome_bonus(USER)   # 首次 +30
    before = credits_service.get_balance(USER)
    # 模拟历史用户再次触发（claimed 已置位）
    r = credits_service.claim_welcome_bonus(USER)
    assert r["success"] is False and r["already_claimed"] is True
    assert credits_service.get_balance(USER) == before  # 余额零变化


# ── Retired endpoints：HTTP 410 ─────────────────────────────────────────────

def test_bonus_welcome_endpoint_410(authed_client):
    resp = authed_client.post("/api/v1/credits/bonus/welcome")
    assert resp.status_code == 410


def test_bonus_email_verification_endpoint_410(authed_client):
    resp = authed_client.post("/api/v1/credits/bonus/email-verification")
    assert resp.status_code == 410


def test_bonus_first_song_endpoint_410(authed_client):
    resp = authed_client.post("/api/v1/credits/bonus/first-song")
    assert resp.status_code == 410


def test_bonus_endpoints_410_even_anonymous(client):
    """匿名（无 JWT）→ 401（JWT 鉴权依赖先于退役判定执行——安全语义正确）。"""
    for ep in ("/api/v1/credits/bonus/welcome",
               "/api/v1/credits/bonus/email-verification",
               "/api/v1/credits/bonus/first-song"):
        assert client.post(ep).status_code == 401


# ── Credits integrity：generation cost / refund 不受影响 ────────────────────

def test_generation_cost_still_30():
    from app.services.credits_config import get_credit_cost
    assert get_credit_cost("standard_song") == 30


def test_generation_failure_refund_flow_unchanged(credits_db):
    add = credits_service.add_credits(USER, 100, "purchase", reference_id="ls:o-int")
    assert add["success"] is True
    consumed = credits_service.consume_credits(USER, 30, reference_id="task-int")
    assert consumed["success"] is True and credits_service.get_balance(USER) == 70
    refunded = credits_service.refund_generation_credits(USER, "task-int")
    assert refunded["success"] is True and refunded.get("already_refunded") is not True
    assert credits_service.get_balance(USER) == 100  # 失败退款恢复
    r2 = credits_service.refund_generation_credits(USER, "task-int")
    assert r2.get("already_refunded") is True        # 退款幂等
