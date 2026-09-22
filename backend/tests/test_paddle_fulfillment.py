"""Paddle 履约层（客户/订阅镜像 + 访问判定 + 客户门户）回归测试。

覆盖三部分要求：
  §1 customer.* 事件被镜像且绝不发放；未知事件安全忽略
  §2 订阅状态镜像；active/trialing 才算付费，scheduled_change 不收回访问，
     canceled 才收回；至少一次投递 + 乱序下幂等；归属不可改写给别人
  §3 门户会话：未登录 401；无 customer 404；customer_id 只由服务端反查，
     客户端传来的 ctre_ 一律忽略
外加：镜像写失败不得影响积分发放（投影与发放解耦）。
零网络、零真实扣款：临时 SQLite + 自造签名 + 打桩 Paddle 调用。
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
from tests.paddle_payload import normalize_transaction_payload
from app.services import (
    credit_pack_service,
    credits_service,
    membership_service,
    paddle_mirror,
    paddle_service,
)
from app.services.auth_identity import get_verified_user_id

USER = "portal-user-1"
OTHER = "portal-user-2"
SECRET = "pdl_ntfset_fulfillment_test"
CUSTOMER = "ctre_01mx2k4v8n0tjgq7z3vb8k5m2e"

PLAN_ENVS = {"PADDLE_PRICE_ID_STARTER": "pri_plan_starter",
             "PADDLE_PRICE_ID_BASIC": "pri_plan_basic",
             "PADDLE_PRICE_ID_PRO": "pri_plan_pro",
             "PADDLE_PRICE_ID_CREATOR": "pri_plan_creator"}
PACK_ENVS = {"PADDLE_PRICE_ID_CREDITS_200": "pri_pack_200",
             "PADDLE_PRICE_ID_CREDITS_500": "pri_pack_500",
             "PADDLE_PRICE_ID_CREDITS_1200": "pri_pack_1200",
             "PADDLE_PRICE_ID_CREDITS_2800": "pri_pack_2800"}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = str(tmp_path / "fulfillment.db")
    eng = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    from app.db.database import Base
    Base.metadata.create_all(bind=eng)
    maker = sessionmaker(bind=eng)
    monkeypatch.setattr(credits_service, "SessionLocal", maker)
    monkeypatch.setattr(credit_pack_service, "SessionLocal", maker)
    monkeypatch.setattr(membership_service, "SessionLocal", maker)
    monkeypatch.setattr(paddle_mirror, "SessionLocal", maker)
    monkeypatch.setenv("PADDLE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("PADDLE_ENV", "sandbox")
    monkeypatch.setenv("PADDLE_API_KEY", "pdl_sdbx_apikey_test_value")
    monkeypatch.setenv("PADDLE_CLIENT_TOKEN", "test_client_token_value")
    for k, v in {**PLAN_ENVS, **PACK_ENVS}.items():
        monkeypatch.setenv(k, v)
    credits_service.add_credits(USER, 0, "admin_adjustment", description="open row")
    return eng


def _app(user=USER):
    app = FastAPI()
    app.include_router(credits_router.router)
    if user is not None:
        app.dependency_overrides[get_verified_user_id] = lambda: user
    return app


def _balance(user_id: str = USER) -> int:
    return int(credits_service.get_balance(user_id))


def _sign(body: bytes) -> str:
    ts = int(time.time())
    sig = hmac.new(SECRET.encode(), f"{ts}:{body.decode()}".encode(), hashlib.sha256).hexdigest()
    return f"ts={ts};h1={sig}"


def _post(body: bytes) -> tuple[int, dict]:
    client = TestClient(_app(user=None))
    r = client.post("/api/v1/credits/paddle/webhook", content=body,
                    headers={"Content-Type": "application/json",
                             "Paddle-Signature": _sign(body)})
    return r.status_code, r.json()


def _event(event_type: str, data: dict, event_id: str = "evt_1") -> bytes:
    # 交易类夹具统一转成 Paddle 真实载荷形状（金额在 details.totals、price 内嵌 items[]）
    data = normalize_transaction_payload(data)
    return json.dumps({"event_id": event_id, "event_type": event_type,
                       "occurred_at": "2026-09-20T00:00:00Z", "data": data}).encode()


def _subscription_event(event_type: str, *, status="active", subscription_id="sub_001",
                        price_id="pri_plan_pro", customer_id=CUSTOMER, user_id=USER,
                        scheduled_change=None, cancel_at_period_end=False,
                        start="2026-09-20T00:00:00Z", end="2026-10-20T00:00:00Z") -> bytes:
    data = {"id": subscription_id, "status": status, "customer_id": customer_id,
            "currency_code": "USD",
            "billing_cycle": {"interval": "month", "frequency": 1},
            "current_billing_period": {"started_at": start, "ends_at": end},
            "cancel_at_period_end": cancel_at_period_end,
            "items": [{"price_id": price_id, "quantity": 1}],
            "custom_data": {"user_id": user_id, "kind": "membership", "plan_id": "pro"}}
    if scheduled_change is not None:
        data["scheduled_change"] = scheduled_change
    return _event(event_type, data)


def _membership_transaction(txn_id="txn_sub_1", subscription_id="sub_001",
                            price_id="pri_plan_pro", customer_id=None) -> bytes:
    data = {"id": txn_id, "status": "completed", "subscription_id": subscription_id,
            "currency_code": "USD", "grand_total": "1999",
            "billing_period": {"started_at": "2026-09-20T00:00:00Z",
                               "ends_at": "2026-10-20T00:00:00Z"},
            "custom_data": {"user_id": USER, "kind": "membership", "plan_id": "pro"},
            "items": [{"price_id": price_id, "quantity": 1}]}
    if customer_id:
        data["customer_id"] = customer_id
    return _event("transaction.completed", data)


def _sub_row(subscription_id="sub_001"):
    return paddle_mirror.get_subscription(subscription_id)


def _rows(eng, table):
    with eng.connect() as c:
        return [dict(r._mapping) for r in c.execute(text(f"SELECT * FROM {table}")).fetchall()]


# ── §1 客户镜像 ────────────────────────────────────────────────────────
def test_customer_created_then_updated_mirrors_single_row(env):
    code, body = _post(_event("customer.created", {
        "id": CUSTOMER, "email": "a@example.com", "name": "A", "status": "active",
        "locale": "en"}))
    assert code == 200 and body["mirrored"] is True
    code, _ = _post(_event("customer.updated", {
        "id": CUSTOMER, "email": "b@example.com", "status": "active"}, event_id="evt_2"))
    assert code == 200
    rows = _rows(env, "paddle_customers")
    assert len(rows) == 1, "同一客户的多条事件必须 upsert 成一行，不是盲插"
    assert rows[0]["email"] == "b@example.com"


def test_customer_events_never_grant_credits(env):
    before = _balance()
    code, _ = _post(_event("customer.created", {
        "id": CUSTOMER, "email": "a@example.com", "status": "active",
        "custom_data": {"user_id": USER}}))
    assert code == 200
    assert _balance() == before, "客户资料事件绝不能发积分"


def test_unknown_event_is_ignored_and_not_mirrored(env):
    code, body = _post(_event("payout.created", {"id": "pay_001", "status": "approved"}))
    assert code == 200 and body["ignored"] == "payout.created"
    assert _rows(env, "paddle_customers") == []
    assert _rows(env, "paddle_subscriptions") == []


# ── §2 订阅镜像与访问判定 ──────────────────────────────────────────────
def test_subscription_created_mirrors_active_and_grants(env):
    code, body = _post(_membership_transaction())
    assert code == 200 and body["granted_credits"] == 1200
    assert _sub_row()["status"] == "active"
    assert paddle_mirror.has_paid_access(USER) is True


def test_scheduled_change_cancel_keeps_access_until_period_end(env):
    _post(_membership_transaction())
    code, _ = _post(_subscription_event(
        "subscription.updated",
        scheduled_change={"action": "cancel", "resume_at": None,
                          "effective_from": "2026-10-20T00:00:00Z"},
        cancel_at_period_end=True))
    assert code == 200
    row = _sub_row()
    assert row["status"] == "active", "scheduled_change 不改变当前状态"
    assert row["scheduled_change_action"] == "cancel"
    assert paddle_mirror.has_paid_access(USER) is True, "计划取消期间绝不能收回访问"


def test_subscription_canceled_revokes_access_and_syncs_ledger(env):
    _post(_membership_transaction())
    code, _ = _post(_subscription_event("subscription.canceled", status="canceled",
                                        scheduled_change=None))
    assert code == 200
    assert _sub_row()["status"] == "canceled"
    assert paddle_mirror.has_paid_access(USER) is False
    assert membership_service.get_active_membership(USER) is None, \
        "取消后台账必须跟着降级，否则 /membership 继续报生效中"


@pytest.mark.parametrize("status,expected", [
    ("active", True), ("trialing", True),
    ("canceled", False), ("paused", False), ("past_due", False)])
def test_access_matrix_by_status(env, status, expected):
    paddle_mirror.upsert_subscription_state(subscription_id="sub_matrix",
                                           status=status, user_id=USER)
    assert paddle_mirror.has_paid_access(USER) is expected


def test_duplicate_delivery_is_idempotent(env):
    body = _subscription_event("subscription.updated", status="active")
    assert _post(body)[0] == 200
    assert _post(body)[0] == 200
    assert len(_rows(env, "paddle_subscriptions")) == 1


def test_subscription_owner_cannot_be_reassigned(env):
    _post(_membership_transaction())
    code, resp = _post(_subscription_event("subscription.updated", status="active",
                                           user_id=OTHER))
    assert code == 200, "归属冲突不应让 Paddle 无限重投"
    assert resp.get("ignored") or resp.get("status") == "active"
    assert _sub_row()["user_id"] == USER, "会员绝不能被搬到别的用户名下"
    assert paddle_mirror.has_paid_access(OTHER) is False


def test_transaction_only_event_links_customer_without_status_damage(env):
    code, _ = _post(_membership_transaction(customer_id=CUSTOMER))
    assert code == 200
    assert _sub_row()["status"] == "active", "交易事件不得把订阅状态写成交易状态"
    assert paddle_mirror.get_customer_id_for_user(USER) == CUSTOMER


def test_mirror_failure_does_not_block_grant(env, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("mirror db is down")

    monkeypatch.setattr(paddle_mirror, "mirror_from_event", boom)
    code, body = _post(_membership_transaction())
    assert code == 200 and body["granted_credits"] == 1200, "投影故障绝不能吞掉履约"
    assert _balance() == 1200


# ── §3 客户门户 ────────────────────────────────────────────────────────
def test_portal_session_requires_authentication(env):
    app = _app(user=None)                      # 不覆盖依赖 → 真实 JWT 校验路径
    r = TestClient(app).post("/api/v1/credits/portal-session")
    assert r.status_code == 401


def test_portal_session_missing_customer_returns_404(env):
    r = TestClient(_app()).post("/api/v1/credits/portal-session")
    assert r.status_code == 404 and r.json()["detail"] == "no_paddle_customer"


def test_portal_session_resolves_customer_server_side(env, monkeypatch):
    seen: dict[str, object] = {}

    async def fake(customer_id, subscription_ids=None):
        seen["customer_id"] = customer_id
        seen["subscription_ids"] = subscription_ids
        return {"url": "https://paddle.test/portal/session-token",
                "subscription_urls": [], "customer_id": customer_id}

    monkeypatch.setattr(paddle_service, "create_portal_session", fake)
    _post(_membership_transaction(customer_id=CUSTOMER))
    r = TestClient(_app()).post("/api/v1/credits/portal-session",
                                json={"customer_id": "ctre_someone_elses_account"})
    assert r.status_code == 200
    assert r.json()["url"] == "https://paddle.test/portal/session-token"
    assert seen["customer_id"] == CUSTOMER, "必须用服务端镜像反查的 customer id"
    assert seen["subscription_ids"] == ["sub_001"]


def test_portal_session_is_503_without_api_key(env, monkeypatch):
    monkeypatch.delenv("PADDLE_API_KEY")
    r = TestClient(_app()).post("/api/v1/credits/portal-session")
    assert r.status_code == 503
