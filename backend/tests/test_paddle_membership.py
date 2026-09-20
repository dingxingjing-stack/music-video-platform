"""会员订阅（Paddle Recurring / Monthly）与积分包隔离性的回归测试。

覆盖本轮要求：
  §9  Starter 4.99/月、Basic 9.99/月、Pro 19.99/月、Creator 39.99/月（数字不得改动）
  §10 会员用 Recurring、积分包用 One-time
  §11 积分包不得创建订阅、不得改会员等级/到期时间（反之亦然）
  §12 同一账号可重复买包，积分累加
  §13 只有验签通过的 webhook 才发放
  §14/§15 客户端不能决定积分数量，Price ID → 数量只在后端
  §16 幂等（同一事件重投 / 同一周期重复通知）
  §17 会员与积分包共用同一套用户与积分系统
零网络、零真实扣款：临时 SQLite + 自造签名，不触任何 Paddle 接口。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.routers import credits as credits_router
from app.services import (
    credit_pack_service,
    credits_service,
    membership_service,
    paddle_service,
)
from app.services.auth_identity import get_verified_user_id

USER = "member-1"
SECRET = "pdl_ntfset_membership_test"

PLAN_ENVS = {
    "PADDLE_PRICE_ID_STARTER": "pri_plan_starter",
    "PADDLE_PRICE_ID_BASIC": "pri_plan_basic",
    "PADDLE_PRICE_ID_PRO": "pri_plan_pro",
    "PADDLE_PRICE_ID_CREATOR": "pri_plan_creator",
}
PACK_ENVS = {
    "PADDLE_PRICE_ID_CREDITS_200": "pri_pack_200",
    "PADDLE_PRICE_ID_CREDITS_500": "pri_pack_500",
    "PADDLE_PRICE_ID_CREDITS_1200": "pri_pack_1200",
    "PADDLE_PRICE_ID_CREDITS_2800": "pri_pack_2800",
}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = str(tmp_path / "billing.db")
    eng = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    from app.db.database import Base
    Base.metadata.create_all(bind=eng)
    monkeypatch.setattr(credits_service, "SessionLocal", sessionmaker(bind=eng))
    monkeypatch.setattr(credit_pack_service, "SessionLocal", sessionmaker(bind=eng))
    monkeypatch.setattr(membership_service, "SessionLocal", sessionmaker(bind=eng))
    monkeypatch.setenv("PADDLE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("PADDLE_ENV", "sandbox")
    monkeypatch.setenv("PADDLE_API_KEY", "pdl_sdbx_apikey_test_value")
    monkeypatch.setenv("PADDLE_CLIENT_TOKEN", "test_client_token_value")
    for k, v in {**PLAN_ENVS, **PACK_ENVS}.items():
        monkeypatch.setenv(k, v)
    credits_service.add_credits(USER, 0, "admin_adjustment", description="open row")
    return eng


def _client(authenticated: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(credits_router.router)
    if authenticated:
        app.dependency_overrides[get_verified_user_id] = lambda: USER
    return TestClient(app)


def _balance(user_id: str = USER) -> int:
    return int(credits_service.get_balance(user_id))


def _sign(body: bytes, ts: int) -> str:
    sig = hmac.new(SECRET.encode(), f"{ts}:{body.decode()}".encode(), hashlib.sha256).hexdigest()
    return f"ts={ts};h1={sig}"


def _post(body: bytes, signature: str | None = None) -> tuple[int, dict]:
    r = _client(authenticated=False).post(
        "/api/v1/credits/paddle/webhook", content=body,
        headers={"Content-Type": "application/json",
                 **({"Paddle-Signature": signature} if signature else {})})
    return r.status_code, r.json()


def _event(event_type: str, data: dict) -> bytes:
    return json.dumps({"event_id": "evt_" + str(len(data)) + event_type[-6:],
                       "event_type": event_type, "occurred_at": "2026-09-20T00:00:00Z",
                       "data": data}).encode()


def _membership_transaction(*, price_id="pri_plan_pro", txn_id="txn_sub_1",
                            subscription_id="sub_001", start="2026-09-20T00:00:00Z",
                            end="2026-10-20T00:00:00Z", grand_total="1999",
                            custom_data=None) -> bytes:
    custom = {"user_id": USER, "kind": "membership", "plan_id": "pro",
              "credits_per_month": "1200"} if custom_data is None else custom_data
    return _event("transaction.completed", {
        "id": txn_id, "status": "completed", "subscription_id": subscription_id,
        "currency_code": "USD", "grand_total": grand_total,
        "billing_period": {"started_at": start, "ends_at": end},
        "custom_data": custom,
        "items": [{"price_id": price_id, "quantity": 1}],
    })


def _membership_row(subscription_id: str = "sub_001"):
    return membership_service.get_membership(subscription_id)


# ── §9/§10 配置与 one-time vs recurring ───────────────────────────────
def test_plans_use_the_locked_price_table(env):
    body = _client().get("/api/v1/credits/plans").json()
    got = {p["id"]: p for p in body["plans"]}
    assert set(got) == {"starter", "basic", "pro", "creator"}
    assert [(got[i]["price_usd"], got[i]["credits_per_month"]) for i in
            ("starter", "basic", "pro", "creator")] == \
        [(4.99, 200), (9.99, 500), (19.99, 1200), (39.99, 2800)], "会员价格与每月积分不得被改动"
    assert body["recurring"] is True and body["interval"] == "month"
    assert all(p["recurring"] is True for p in body["plans"])
    # 同一响应里积分包必须是 one-time（两套商品语义不混）
    packs = _client().get("/api/v1/credits/packs").json()
    assert packs["recurring"] is False and all(p["recurring"] is False for p in packs["packs"])


def test_plans_empty_when_price_ids_missing(monkeypatch):
    for k in PLAN_ENVS:
        monkeypatch.delenv(k, raising=False)
    app = FastAPI()
    app.include_router(credits_router.router)
    assert TestClient(app).get("/api/v1/credits/plans").json()["plans"] == []


# ── §13 建单阶段绝不发放 ─────────────────────────────────────────────
def test_plan_checkout_grants_nothing(env, monkeypatch):
    async def _fake(**kwargs):
        return {"transaction_id": "txn_pending_sub", "checkout_url": None}

    async def _no_email(user_id):
        return None

    monkeypatch.setattr(paddle_service, "create_checkout_transaction", _fake)
    monkeypatch.setattr(paddle_service, "lookup_user_email", _no_email)
    r = _client().post("/api/v1/credits/checkout", json={"plan_id": "pro"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recurring"] is True and body["credits_per_month"] == 1200
    assert _balance() == 0, "仅建单不得发积分"
    assert membership_service.get_active_membership(USER) is None, "仅建单不得产生会员等级"


def test_plan_checkout_requires_login(env):
    assert _client(authenticated=False).post("/api/v1/credits/checkout",
                                             json={"plan_id": "pro"}).status_code == 401


def test_checkout_rejects_ambiguous_request(env):
    assert _client().post("/api/v1/credits/checkout",
                          json={"plan_id": "pro", "pack_id": "credits_200"}).status_code == 422


# ── 会员开通：等级 + 月度积分 ─────────────────────────────────────────
def test_membership_transaction_sets_tier_and_grants_monthly_credits(env):
    body = _membership_transaction()
    status, resp = _post(body, _sign(body, int(time.time())))
    assert status == 200, resp
    assert resp["granted_credits"] == 1200
    assert _balance() == 1200
    row = _membership_row()
    assert row["plan_id"] == "pro" and row["status"] == "active"
    assert row["current_period_end"] == "2026-10-20T00:00:00Z"
    assert row["credits_per_month"] == 1200
    active = membership_service.get_active_membership(USER)
    assert active["plan_id"] == "pro"
    assert _client().get("/api/v1/credits/membership").json()["membership"]["plan_id"] == "pro"
    assert _rows(env, "SELECT transaction_type FROM credits_transactions ORDER BY id") ==         ["admin_adjustment", "subscription_grant"]
    # 复用同一套积分/账本系统，不另建余额表
    assert _col(env, "SELECT COUNT(*) FROM credit_pack_purchases") == 0


def test_membership_grant_is_idempotent_per_period(env):
    body = _membership_transaction()
    assert _post(body, _sign(body, int(time.time())))[1]["granted_credits"] == 1200
    for _ in range(3):
        status, resp = _post(body, _sign(body, int(time.time())))
        assert status == 200 and resp["granted_credits"] == 0
    assert _balance() == 1200, "同一周期重投只发一次"


def test_membership_renewal_next_period_grants_again(env):
    first = _membership_transaction(txn_id="txn_c1",
                                    start="2026-09-20T00:00:00Z", end="2026-10-20T00:00:00Z")
    assert _post(first, _sign(first, int(time.time())))[1]["granted_credits"] == 1200
    renewal = _membership_transaction(txn_id="txn_c2",
                                      start="2026-10-20T00:00:00Z", end="2026-11-20T00:00:00Z")
    assert _post(renewal, _sign(renewal, int(time.time())))[1]["granted_credits"] == 1200
    assert _balance() == 2400
    renewal_again = _membership_transaction(txn_id="txn_c2",
                                            start="2026-10-20T00:00:00Z", end="2026-11-20T00:00:00Z")
    assert _post(renewal_again, _sign(renewal_again, int(time.time())))[1]["granted_credits"] == 0
    assert _balance() == 2400, "同一续费周期重投不得再发"


def test_renewal_transaction_paid_without_custom_data_uses_stored_owner(env):
    opening = _membership_transaction()
    assert _post(opening, _sign(opening, int(time.time())))[0] == 200
    # 续费交易可能不带 custom_data：身份必须回退到首开事件登记的归属
    renewal = _event("transaction.paid", {
        "id": "txn_renew_noCD", "status": "paid", "subscription_id": "sub_001",
        "currency_code": "USD", "grand_total": "1999",
        "billing_period": {"started_at": "2026-11-20T00:00:00Z",
                           "ends_at": "2026-12-20T00:00:00Z"},
        "custom_data": {},
        "items": [{"price_id": "pri_plan_pro", "quantity": 1}],
    })
    status, resp = _post(renewal, _sign(renewal, int(time.time())))
    assert status == 200, resp
    assert resp["granted_credits"] == 1200 and _balance() == 2400


def test_subscription_cancel_updates_status_without_revoking_credits(env):
    opening = _membership_transaction()
    _post(opening, _sign(opening, int(time.time())))
    cancel = _event("subscription.canceled", {
        "id": "sub_001", "status": "canceled", "price_id": "pri_plan_pro",
        "current_billing_period_end": "2026-10-20T00:00:00Z", "custom_data": {}})
    assert _post(cancel, _sign(cancel, int(time.time())))[0] == 200
    assert _membership_row()["status"] == "canceled"
    assert _balance() == 1200, "取消不回收已发放的积分"
    assert membership_service.get_active_membership(USER) is None
    assert _client().get("/api/v1/credits/membership").json()["membership"] is None


def test_sync_only_events_never_grant(env):
    opening = _membership_transaction()
    _post(opening, _sign(opening, int(time.time())))
    before = _balance()
    updated = _event("subscription.updated", {
        "id": "sub_001", "status": "active", "price_id": "pri_plan_pro",
        "current_billing_period_start": "2026-09-20T00:00:00Z",
        "current_billing_period_end": "2026-10-20T00:00:00Z", "custom_data": {}})
    assert _post(updated, _sign(updated, int(time.time())))[1]["granted_credits"] == 0
    assert _balance() == before


def test_unknown_membership_price_is_ignored(env):
    body = _membership_transaction(price_id="pri_not_configured", txn_id="txn_x",
                                   subscription_id="sub_x")
    status, resp = _post(body, _sign(body, int(time.time())))
    assert status == 200 and resp.get("ignored") == "unconfigured_price"
    assert _balance() == 0
    assert membership_service.get_active_membership(USER) is None


def test_membership_checkout_price_mismatch_is_refused(env):
    body = _membership_transaction(grand_total="499", txn_id="txn_cheap", subscription_id="sub_cheap")
    status, resp = _post(body, _sign(body, int(time.time())))
    assert status == 400, resp
    assert _balance() == 0 and membership_service.get_active_membership(USER) is None


# ── §11/§12/§17 两套商品互不干扰、共用同一套积分系统 ──────────────────
def test_credit_pack_never_creates_or_changes_membership(env):
    pack = _event("transaction.completed", {
        "id": "txn_pack_only", "status": "completed", "currency_code": "USD", "grand_total": "499",
        "custom_data": {"user_id": USER, "kind": "credit_pack", "pack_id": "credits_200",
                        "credits": "200"},
        "items": [{"price_id": "pri_pack_200", "quantity": 1}]})
    assert _post(pack, _sign(pack, int(time.time())))[1]["granted_credits"] == 200
    assert membership_service.get_active_membership(USER) is None, "买包不得产生会员订阅"
    assert _col(env, "SELECT COUNT(*) FROM user_memberships") == 0
    assert _balance() == 200

    opening = _membership_transaction()
    _post(opening, _sign(opening, int(time.time())))
    period_end_before = _membership_row()["current_period_end"]
    anchor_before = _membership_row()["last_granted_period_start"]
    second = _event("transaction.completed", {
        "id": "txn_pack_2", "status": "completed", "currency_code": "USD", "grand_total": "499",
        "custom_data": {"user_id": USER, "kind": "credit_pack", "pack_id": "credits_200",
                        "credits": "200"},
        "items": [{"price_id": "pri_pack_200", "quantity": 1}]})
    assert _post(second, _sign(second, int(time.time())))[1]["granted_credits"] == 200
    row = _membership_row()
    assert row["current_period_end"] == period_end_before, "买包不得改会员到期时间"
    assert row["plan_id"] == "pro" and row["last_granted_period_start"] == anchor_before, \
        "买包不得改会员等级或消耗本周期发放锚点"
    assert _balance() == 200 + 1200 + 200, "积分一律累加"


def test_repeated_pack_purchases_accumulate(env):
    for i in range(3):
        pack = _event("transaction.completed", {
            "id": f"txn_acc_{i}", "status": "completed", "currency_code": "USD",
            "grand_total": "999",
            "custom_data": {"user_id": USER, "kind": "credit_pack", "pack_id": "credits_500",
                            "credits": "500"},
            "items": [{"price_id": "pri_pack_500", "quantity": 1}]})
        assert _post(pack, _sign(pack, int(time.time())))[1]["granted_credits"] == 500
    assert _balance() == 1500
    assert _col(env, "SELECT COUNT(*) FROM credit_pack_purchases") == 3


def test_webhook_still_fails_closed_without_secret(monkeypatch):
    monkeypatch.delenv("PADDLE_WEBHOOK_SECRET", raising=False)
    body = _membership_transaction()
    app = FastAPI()
    app.include_router(credits_router.router)
    r = TestClient(app).post("/api/v1/credits/paddle/webhook", content=body,
                             headers={"Paddle-Signature": "ts=1;h1=x"})
    assert r.status_code == 503


# ── 自检端点绝不回显密钥值 ───────────────────────────────────────────
def test_billing_status_reports_presence_only(env):
    r = _client(authenticated=False).get("/api/v1/credits/billing-status")
    assert r.status_code == 200
    text_body = r.text
    assert SECRET not in text_body and "sgr_test_value" not in text_body
    assert "test_client_token_value" not in text_body and "pri_plan_pro" not in text_body
    body = r.json()
    assert body["missing_credentials"] == []
    assert body["credentials_present"] == {"PADDLE_API_KEY": True, "PADDLE_CLIENT_TOKEN": True,
                                           "PADDLE_WEBHOOK_SECRET": True}
    assert body["credit_pack_prices_configured"] == 4 and body["membership_prices_configured"] == 4
    assert body["packs_ready"] is True and body["plans_ready"] is True
    assert body["webhook_path"] == "/api/v1/credits/paddle/webhook"


def _rows(eng, sql, **params):
    sess = eng.connect()
    try:
        out = [r[0] for r in sess.execute(text(sql), params).fetchall()]
        sess.commit()
        return out
    finally:
        sess.close()


def _col(eng, sql, **params):
    sess = eng.connect()
    try:
        res = sess.execute(text(sql), params)
        try:
            value = res.scalar()
        except Exception:
            value = None
        sess.commit()
        return value
    finally:
        sess.close()


# ── Sandbox / Production 凭据错配必须拒绝下单 ────────────────────────
def test_checkout_refuses_test_token_in_production(env, monkeypatch):
    async def _fake(**kwargs):
        return {"transaction_id": "should_not_happen", "checkout_url": None}

    monkeypatch.setattr(paddle_service, "create_checkout_transaction", _fake)
    monkeypatch.setenv("PADDLE_ENV", "production")      # 但 token 仍是 test_ 前缀
    r = _client().post("/api/v1/credits/checkout", json={"plan_id": "pro"})
    assert r.status_code == 503
    assert r.json()["detail"] == "paddle_env_mismatch_test_token_in_production"
    assert _balance() == 0


def test_checkout_refuses_live_token_in_sandbox(env, monkeypatch):
    monkeypatch.setenv("PADDLE_CLIENT_TOKEN", "live_real_token_value")
    monkeypatch.setenv("PADDLE_ENV", "sandbox")
    r = _client().post("/api/v1/credits/checkout", json={"pack_id": "credits_200"})
    assert r.status_code == 503
    assert r.json()["detail"] == "paddle_env_mismatch_live_token_in_sandbox"


# ── 周期扣款的真实事件名：transaction.paid / subscription.activated ────
def test_transaction_paid_grants_and_completed_is_deduped(env):
    """同一订阅周期：先 transaction.paid 发放，随后 transaction.completed 重投不得再发。"""
    paid = _membership_transaction(txn_id="txn_paid_first", start="2026-09-20T00:00:00Z")
    paid = paid.replace(b'"transaction.completed"', b'"transaction.paid"')
    status, resp = _post(paid, _sign(paid, int(time.time())))
    assert status == 200, resp
    assert resp["granted_credits"] == 1200, "transaction.paid 是真实续费信号"
    completed = _membership_transaction(txn_id="txn_completed_second", start="2026-09-20T00:00:00Z")
    status, resp = _post(completed, _sign(completed, int(time.time())))
    assert status == 200, resp
    assert resp["granted_credits"] == 0, "同周期第二笔通知不得再发"
    assert _balance() == 1200


def test_credit_pack_ignores_transaction_paid(env):
    """一次性积分包只认 transaction.completed（§五）；paid 阶段不得提前发放。"""
    body = _event("transaction.completed", {
        "id": "txn_pack_paid_first", "status": "paid", "currency_code": "USD",
        "grand_total": "499",
        "custom_data": {"user_id": USER, "kind": "credit_pack", "pack_id": "credits_200",
                        "credits": "200"},
        "items": [{"price_id": "pri_pack_200", "quantity": 1}]}).replace(
        b'"transaction.completed"', b'"transaction.paid"')
    status, resp = _post(body, _sign(body, int(time.time())))
    assert status == 200 and resp.get("granted_credits") is None
    assert _balance() == 0, "transaction.paid 阶段绝不提前发放积分包 Credits"


def test_subscription_activated_grants_for_new_period(env):
    """试用转正（subscription.activated）算作成功周期。"""
    opening = _membership_transaction()
    _post(opening, _sign(opening, int(time.time())))
    activated = _event("subscription.activated", {
        "id": "sub_001", "status": "active", "price_id": "pri_plan_pro",
        "current_billing_period_start": "2026-10-20T00:00:00Z",
        "current_billing_period_end": "2026-11-20T00:00:00Z", "custom_data": {}})
    assert _post(activated, _sign(activated, int(time.time())))[1]["granted_credits"] == 1200


def test_trialing_event_grants_nothing(env):
    body = _event("subscription.trialing", {
        "id": "sub_trial", "status": "trialing", "price_id": "pri_plan_pro",
        "current_billing_period_start": "2026-09-20T00:00:00Z",
        "current_billing_period_end": "2026-10-20T00:00:00Z",
        "custom_data": {"user_id": USER, "kind": "membership", "plan_id": "pro"}})
    assert _post(body, _sign(body, int(time.time())))[1]["granted_credits"] == 0
    assert _balance() == 0


# ── 公开接口不下发 Price ID；旧 packages 标记 deprecated ──────────────
def test_public_endpoints_do_not_leak_price_ids(env):
    for path in ("/api/v1/credits/packs", "/api/v1/credits/plans"):
        text = _client(authenticated=False).get(path).text
        for secret_id in ("pri_plan_pro", "pri_pack_200", "pri_plan_starter"):
            assert secret_id not in text
    legacy = _client(authenticated=False).get("/api/v1/credits/packages").json()
    assert legacy["deprecated"] is True and legacy["use"]


def test_billing_status_lists_price_env_names_only(env):
    body = _client(authenticated=False).get("/api/v1/credits/billing-status").json()
    assert body["credential_warnings"] == [] and body["checkout_blocked_reason"] is None
    assert "PADDLE_PRICE_ID_STARTER" in body["price_env_keys"]["memberships"]
    assert "PADDLE_PRICE_ID_CREDITS_200" in body["price_env_keys"]["credit_packs"]
