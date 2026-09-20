"""积分补充包（Credit Packs / Paddle one-time）回归测试。

覆盖本轮的四条硬要求：
  §三 只有 webhook 确认支付成功才发 Credits（建单/打开 Checkout 不发）
  §四 同一笔 Paddle 交易重复回调只发一次
  §五 客户端不能声明积分数量，必须由后端 Price ID 决定
  §七 与会员订阅完全独立（不碰 beta_users 权益、不建订阅）
外加：未配置 Paddle 时全线 fail-closed；金额/币种不符不发；非 completed 事件不发。

全部走临时 SQLite + 假 Paddle（不打真实网络、不产生任何真实扣款）。
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
from app.services import credit_pack_service, credits_service, paddle_service
from app.services.auth_identity import get_verified_user_id

USER = "pack-buyer-1"
OTHER = "pack-buyer-2"
SECRET = "pdl_ntfset_test_secret"

PACK_ENVS = {
    "PADDLE_PRICE_ID_CREDITS_200": "pri_200credits",
    "PADDLE_PRICE_ID_CREDITS_500": "pri_500credits",
    "PADDLE_PRICE_ID_CREDITS_1200": "pri_1200credits",
    "PADDLE_PRICE_ID_CREDITS_2800": "pri_2800credits",
}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = str(tmp_path / "packs.db")
    eng = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    from app.db.database import Base
    Base.metadata.create_all(bind=eng)
    monkeypatch.setattr(credits_service, "SessionLocal", sessionmaker(bind=eng))
    monkeypatch.setattr(credit_pack_service, "SessionLocal", sessionmaker(bind=eng))
    # ai_limits（会员每日额度权益）也必须指向同一临时库，否则测试会读写开发库
    from app.services import ai_limits
    monkeypatch.setattr(ai_limits, "_DB_PATH", db)
    monkeypatch.setenv("PADDLE_WEBHOOK_SECRET", SECRET)
    for k, v in PACK_ENVS.items():
        monkeypatch.setenv(k, v)
    credits_service.add_credits(USER, 20, "admin_adjustment", description="seed")
    return eng


def _balance(user_id: str = USER) -> int:
    return int(credits_service.get_balance(user_id))


def _client(authenticated: bool = True, user: str = USER) -> TestClient:
    app = FastAPI()
    app.include_router(credits_router.router)
    if authenticated:
        app.dependency_overrides[get_verified_user_id] = lambda: user
    return TestClient(app)


def _sign(body: bytes, ts: int, secret: str = SECRET) -> str:
    sig = hmac.new(secret.encode("utf-8"), f"{ts}:{body.decode('utf-8')}".encode("utf-8"),
                   hashlib.sha256).hexdigest()
    return f"ts={ts};h1={sig}"


def _txn_event(*, price_id="pri_200credits", txn_id="txn_abc", user_id=USER, status="completed",
               event_type="transaction.completed", grand_total=499, currency="USD",
               custom_data=None) -> bytes:
    custom = {"user_id": user_id, "pack_id": "credits_200", "credits": "200", "kind": "credit_pack"} \
        if custom_data is None else custom_data
    payload = {
        "event_id": "evt_" + txn_id,
        "event_type": event_type,
        "occurred_at": "2026-09-20T00:00:00Z",
        "data": {
            "id": txn_id,
            "status": status,
            "currency_code": currency,
            "grand_total": str(grand_total),
            "custom_data": custom,
            "items": [{"price_id": price_id, "quantity": 1}],
        },
    }
    return json.dumps(payload).encode("utf-8")


def _post_webhook(body: bytes, signature: str | None) -> TestClient.response_model:  # type: ignore[valid-type]
    return _client(authenticated=False).post(
        "/api/v1/credits/paddle/webhook",
        content=body,
        headers={"Content-Type": "application/json",
                 **({"Paddle-Signature": signature} if signature else {})},
    )


# ── §五 配置是唯一事实来源 ───────────────────────────────────────────
def test_packs_empty_without_price_ids(monkeypatch):
    for k in PACK_ENVS:
        monkeypatch.delenv(k, raising=False)
    body = _client().get("/api/v1/credits/packs").json()
    assert body["packs"] == []
    assert body["recurring"] is False


def test_packs_lists_all_four_with_backend_credits(env):
    body = _client().get("/api/v1/credits/packs").json()
    got = {p["id"]: p for p in body["packs"]}
    assert set(got) == {"credits_200", "credits_500", "credits_1200", "credits_2800"}
    assert [(got[i]["credits"], got[i]["price_usd"]) for i in
            ("credits_200", "credits_500", "credits_1200", "credits_2800")] == \
        [(200, 4.99), (500, 9.99), (1200, 19.99), (2800, 39.99)]
    assert all(p["recurring"] is False for p in body["packs"]), "补充包绝不能是 Recurring"


# ── §三 建单/打开 Checkout 绝不发 Credits ─────────────────────────────
def test_checkout_requires_login():
    assert _client(authenticated=False).post("/api/v1/credits/checkout",
                                             json={"pack_id": "credits_200"}).status_code == 401


def test_checkout_fails_closed_without_api_key(env, monkeypatch):
    monkeypatch.delenv("PADDLE_API_KEY", raising=False)
    r = _client().post("/api/v1/credits/checkout", json={"pack_id": "credits_200"})
    assert r.status_code == 503
    assert _balance() == 20, "未配置支付商不得发生任何变化"


def test_checkout_unknown_pack(env, monkeypatch):
    monkeypatch.setenv("PADDLE_API_KEY", "pdl_sdbx_apikey_test")
    assert _client().post("/api/v1/credits/checkout", json={"pack_id": "credits_999999"}).status_code == 404


def test_checkout_creates_txn_but_grants_nothing(env, monkeypatch):
    monkeypatch.setenv("PADDLE_API_KEY", "pdl_sdbx_apikey_test")

    async def _fake_create(**kwargs):
        return {"transaction_id": "txn_pending_1", "checkout_url": None}

    async def _no_email(user_id):
        return None

    monkeypatch.setattr(paddle_service, "create_checkout_transaction", _fake_create)
    monkeypatch.setattr(paddle_service, "lookup_user_email", _no_email)
    r = _client().post("/api/v1/credits/checkout", json={"pack_id": "credits_200"})
    assert r.status_code == 200
    body = r.json()
    assert body["transaction_id"] == "txn_pending_1"
    assert body["recurring"] is False
    assert _balance() == 20, "仅仅建单/打开 Checkout 绝不能加 Credits"
    assert credit_pack_service.list_purchases(USER) == []


# ── §四 + §五 webhook 才是发放依据，且幂等 ────────────────────────────
def test_webhook_fails_closed_without_secret(monkeypatch):
    monkeypatch.delenv("PADDLE_WEBHOOK_SECRET", raising=False)
    body = _txn_event()
    assert _post_webhook(body, _sign(body, int(time.time()))).status_code == 503


def test_webhook_rejects_missing_and_forged_signature(env):
    body = _txn_event()
    assert _post_webhook(body, None).status_code == 401
    assert _post_webhook(body, "ts=123;h1=deadbeef").status_code == 401
    wrong = _sign(body, int(time.time()), secret="wrong-secret")
    assert _post_webhook(body, wrong).status_code == 401
    assert _balance() == 20, "未通过验签的回调绝不能改余额"
    assert credit_pack_service.list_purchases(USER) == []


def test_webhook_rejects_stale_timestamp(env):
    body = _txn_event()
    old = int(time.time()) - 10_000
    assert _post_webhook(body, _sign(body, old)).status_code == 401


def test_webhook_grants_credits_only_from_price_id(env):
    """客户端在 custom_data 里谎报 999999 Credits，也必须只按 Price ID 配置发 200。"""
    body = _txn_event(custom_data={"user_id": USER, "pack_id": "credits_200",
                                   "credits": "999999", "kind": "credit_pack"})
    r = _post_webhook(body, _sign(body, int(time.time())))
    assert r.status_code == 200, r.text
    assert r.json()["granted_credits"] == 200
    assert _balance() == 220, "20 + 200 = 220（谎报数字无效）"


def test_webhook_repeat_delivery_grants_once(env):
    body = _txn_event(txn_id="txn_dup")
    ts = int(time.time())
    first = _post_webhook(body, _sign(body, ts))
    assert first.status_code == 200 and first.json()["status"] == "granted"
    assert _balance() == 220
    for _ in range(3):
        again = _post_webhook(body, _sign(body, int(time.time())))
        assert again.status_code == 200
        assert again.json()["status"] == "already_processed"
    assert _balance() == 220, "重复回调不得重复发放"
    purchase_rows = int(_scalar(env, "SELECT COUNT(*) FROM credit_pack_purchases"))
    assert purchase_rows == 1


def test_webhook_same_account_can_buy_twice_and_accumulates(env):
    """同一账号连续购买两次 200 包：20 → 220 → 420（累加，不覆盖）。"""
    for txn in ("txn_a", "txn_b"):
        body = _txn_event(txn_id=txn)
        assert _post_webhook(body, _sign(body, int(time.time()))).status_code == 200
        # 不同 transaction_id 必须各自生效
    assert _balance() == 420
    assert len(credit_pack_service.list_purchases(USER)) == 2


def test_webhook_unknown_price_is_ignored(env):
    body = _txn_event(price_id="pri_not_ours", txn_id="txn_unknown")
    r = _post_webhook(body, _sign(body, int(time.time())))
    assert r.status_code == 200 and r.json().get("ignored") == "unconfigured_price"
    assert _balance() == 20


@pytest.mark.parametrize("event_type", ["transaction.billed", "transaction.canceled",
                                        "subscription.updated", "refund.updated"])
def test_webhook_ignores_non_completed_events(env, event_type):
    body = _txn_event(txn_id="txn_ev", event_type=event_type)
    r = _post_webhook(body, _sign(body, int(time.time())))
    assert r.status_code == 200
    assert _balance() == 20, f"{event_type} 不得发放 Credits"


def test_webhook_ignores_transaction_not_completed(env):
    body = _txn_event(txn_id="txn_draft", status="draft")
    assert _post_webhook(body, _sign(body, int(time.time()))).status_code == 200
    assert _balance() == 20


def test_webhook_rejects_amount_mismatch(env):
    """付 4.99 却想拿 2800 包：Price ID 与实收金额不符 → 400 且不发。"""
    body = _txn_event(txn_id="txn_mismatch", price_id="pri_2800credits", grand_total=499)
    r = _post_webhook(body, _sign(body, int(time.time())))
    assert r.status_code == 400
    assert _balance() == 20
    assert _scalar(env, "SELECT COUNT(*) FROM credit_pack_purchases") == 0


def test_webhook_rejects_wrong_currency(env):
    body = _txn_event(txn_id="txn_cur", currency="EUR")
    assert _post_webhook(body, _sign(body, int(time.time()))).status_code == 400
    assert _balance() == 20


def test_webhook_rejects_missing_user_in_custom_data(env):
    body = _txn_event(txn_id="txn_nousr", custom_data={"pack_id": "credits_200", "kind": "credit_pack"})
    assert _post_webhook(body, _sign(body, int(time.time()))).status_code == 400
    assert _balance() == 20


def test_webhook_rejects_missing_custom_kind(env):
    body = _txn_event(txn_id="txn_kind", custom_data={"user_id": USER, "credits": "200"})
    assert _post_webhook(body, _sign(body, int(time.time()))).status_code == 400
    assert _balance() == 20


# ── §七 与会员订阅完全独立 ───────────────────────────────────────────
def test_pack_purchase_does_not_touch_membership_or_quota(env):
    from app.services import ai_limits
    reserved = ai_limits.reserve_generation(USER, 180)
    assert reserved["success"] is True
    before_beta = _scalar(env, "SELECT daily_credits_used || '/' || daily_credits_limit || '/' || is_gray "
                               "FROM beta_users WHERE user_id=:u", u=USER)
    body = _txn_event(txn_id="txn_iso")
    assert _post_webhook(body, _sign(body, int(time.time()))).status_code == 200
    after_beta = _scalar(env, "SELECT daily_credits_used || '/' || daily_credits_limit || '/' || is_gray "
                              "FROM beta_users WHERE user_id=:u", u=USER)
    assert after_beta == before_beta, "买积分包不得改变会员权益/每日生成额度/灰度标记"
    # 也没人偷偷建订阅
    import app.routers.subscription as sub
    assert USER not in sub.subscriptions_db


def test_pack_credit_transaction_type_is_purchase(env):
    body = _txn_event(txn_id="txn_type")
    assert _post_webhook(body, _sign(body, int(time.time()))).status_code == 200
    rows = _scalar(env, "SELECT transaction_type FROM credits_transactions "
                        "WHERE reference_id=:r", r="txn_type")
    assert rows == "purchase"


# ── §六 一次性：多个包混合购买仍累加；不同账号互不影响 ───────────────
def test_different_packs_accumulate_and_other_user_unaffected(env):
    credits_service.add_credits(OTHER, 10, "admin_adjustment", description="seed other")
    b1 = _txn_event(txn_id="txn_p200", price_id="pri_200credits", grand_total=499)
    assert _post_webhook(b1, _sign(b1, int(time.time()))).status_code == 200
    payload = json.loads(b1)
    payload["data"]["items"][0]["price_id"] = "pri_2800credits"
    payload["data"]["grand_total"] = "3999"
    payload["data"]["id"] = "txn_p2800"
    payload["event_id"] = "evt_txn_p2800"
    b2 = json.dumps(payload).encode("utf-8")
    assert _post_webhook(b2, _sign(b2, int(time.time()))).status_code == 200
    assert _balance(USER) == 20 + 200 + 2800
    assert _balance(OTHER) == 10, "别人买包不得影响本账号余额"


# ── 音乐生成失败不扣 Credits：规则来源仍只有 standard_song=30 ─────────
def test_pack_feature_does_not_change_generation_cost_rule():
    from app.services.credits_config import CREDIT_COSTS, get_credit_cost
    assert get_credit_cost("standard_song", 180) == 30
    assert CREDIT_COSTS["standard_song"]["credit_cost"] == 30


def _scalar(eng, sql, **params):
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
