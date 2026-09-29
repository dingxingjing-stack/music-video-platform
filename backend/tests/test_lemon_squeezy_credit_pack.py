"""P2-4：Lemon Squeezy 一次性 Credit Pack 履约测试。

覆盖三件事，缺一不可：

  一 只有该发的才发：order_created + custom.kind=credit_pack + variant 已配置 +
    档位自洽 + 状态 paid + quantity 1 + 币种与金额与服务端配置一致 + 身份可用。
    任何一项不满足 ⇒ 0 Credits、0 purchase。
  二 发放只可能有一次：claim 由 lemonsqueezy_purchases.ls_order_id 的数据库 UNIQUE
    承担；grant 失败必须释放 claim，让重投还能补发；重投成功单只能得到
    already_processed。
  三 本阶段绝不该动的东西：subscription / invoice / refund / membership / grant
    相关表在全部场景后都必须仍是 0 行。

夹具形状沿用 tests/ls_payload.py（2026-09-25 真实 Test Mode 投递）。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db import database as db
from app.db.database import (
    Base,
    LemonSqueezyMembership,
    LemonSqueezyMembershipGrant,
    LemonSqueezyPurchase,
    LemonSqueezyWebhookDelivery,
)
from app.routers import lemon_squeezy as ls_router
from app.services import credits_service
from app.services import lemon_squeezy_service as ls
from tests import ls_payload

SECRET = "ls_test_webhook_secret_0123456789abcdefghij"
WEBHOOK_URL = "/api/v1/credits/lemonsqueezy/webhook"
USER = "11111111-2222-3333-4444-555555555555"
OTHER_USER = "66666666-7777-8888-9999-000000000000"

# 实测的 test-mode variant / product id（credits_500/1200/2800 的 price_id 未逐个
# 抓取，但 price_id 只被记录、不参与判定，故此处用合成值不影响结论）。
PACKS = {
    "credits_200": {"variant": "2167238", "product": "1387476", "price": "3637193",
                    "credits": 200, "cents": 499},
    "credits_500": {"variant": "2167243", "product": "1387479", "price": "3637500",
                    "credits": 500, "cents": 999},
    "credits_1200": {"variant": "2167246", "product": "1387482", "price": "3637600",
                     "credits": 1200, "cents": 1999},
    "credits_2800": {"variant": "2167248", "product": "1387484", "price": "3637700",
                     "credits": 2800, "cents": 3999},
}


@pytest.fixture()
def env(monkeypatch, tmp_path):
    """临时库 + 已配置的 4 个 pack variant；返回 TestClient 与查询助手。"""
    eng = create_engine(f"sqlite:///{tmp_path / 'ls.p24.db'}",
                        connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    maker = sessionmaker(bind=eng)
    monkeypatch.setattr(db, "engine", eng)
    monkeypatch.setattr(db, "SessionLocal", maker)
    monkeypatch.setattr(credits_service, "SessionLocal", maker)
    monkeypatch.setenv("LEMONSQUEEZY_WEBHOOK_SECRET", SECRET)
    for item, cfg in PACKS.items():
        monkeypatch.setenv(f"LEMONSQUEEZY_VARIANT_ID_{item.upper()}", cfg["variant"])
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    app = FastAPI()
    app.include_router(ls_router.router)
    return TestClient(app)


def _pack_payload(item: str, *, order_id: int = 9569465, webhook_id: str = ls_payload.DELIVERY_ID,
                  user_id: str | None = USER, price_cents: int | None = None,
                  quantity: int = 1, currency: str = "USD", tax: int = 0, discount: int = 0,
                  status: str = "paid", refunded: bool = False, test_mode: bool = True,
                  declared_pack: str | None = None, variant: str | None = None,
                  event_name: str = "order_created"):
    cfg = PACKS[item]
    custom = {"user_id": user_id if user_id is not None else "", "kind": "credit_pack",
              "pack_id": declared_pack or item, "credits": str(cfg["credits"])}
    if user_id is None:
        custom.pop("user_id")
    return ls_payload.order_payload(
        event_name=event_name, webhook_id=webhook_id, order_id=order_id,
        order_number=4823880 + order_id % 10, custom=custom,
        variant_id=int(variant or cfg["variant"]), product_id=int(cfg["product"]),
        price_id=int(cfg["price"]),
        price_cents=cfg["cents"] if price_cents is None else price_cents,
        quantity=quantity, currency=currency, tax=tax, discount=discount,
        status=status, refunded=refunded, test_mode=test_mode)


def _send(env, payload):
    body = ls_payload.encode(payload)
    return env.post(WEBHOOK_URL, content=body,
                    headers={"Content-Type": "application/json",
                             "X-Signature": ls_payload.sign(body, SECRET)})


def _balance(user_id: str) -> int | None:
    sess = db.SessionLocal()
    try:
        return sess.scalar(select(db.UserCredit.balance).where(db.UserCredit.user_id == user_id))
    finally:
        sess.close()


def _count(model) -> int:
    sess = db.SessionLocal()
    try:
        return sess.scalar(select(func.count()).select_from(model.__table__)) or 0
    finally:
        sess.close()


def _txn_count(user_id: str) -> int:
    sess = db.SessionLocal()
    try:
        return sess.scalar(select(func.count()).select_from(db.CreditTransaction)
                           .where(db.CreditTransaction.user_id == user_id)) or 0
    finally:
        sess.close()


# ── A–D. 四个档位各发一次 ───────────────────────────────────────────────
@pytest.mark.parametrize("item", ["credits_200", "credits_500", "credits_1200", "credits_2800"])
def test_each_pack_grants_its_own_credit_amount(env, item):
    res = _send(env, _pack_payload(item))
    assert res.status_code == 200, res.text
    assert _balance(USER) == PACKS[item]["credits"]
    assert _count(LemonSqueezyPurchase) == 1


def test_purchase_ledger_records_the_measured_fields(env):
    assert _send(env, _pack_payload("credits_200")).status_code == 200
    sess = db.SessionLocal()
    try:
        row = sess.scalars(select(LemonSqueezyPurchase)).one()
    finally:
        sess.close()
    assert row.ls_order_id == "9569465"
    assert row.ls_event_id == ls_payload.DELIVERY_ID
    assert row.user_id == USER
    assert row.test_mode is True
    assert (row.product_id, row.variant_id, row.price_id) == ("1387476", "2167238", "3637193")
    assert row.quantity == 1 and row.currency == "USD"
    assert (row.subtotal_cents, row.tax_cents, row.discount_cents, row.total_cents) == (499, 0, 0, 499)
    assert row.refunded_amount_cents == 0
    assert row.created_at is not None and row.updated_at is not None


def test_credit_transaction_is_namespaced_per_ls_order(env):
    assert _send(env, _pack_payload("credits_200")).status_code == 200
    sess = db.SessionLocal()
    try:
        row = sess.scalars(select(db.CreditTransaction)).one()
    finally:
        sess.close()
    assert row.reference_id == "ls:order:9569465"
    assert row.transaction_type == "purchase"
    assert row.amount == 200


# ── E/W. 重复投递只发一次 ───────────────────────────────────────────────
def test_duplicate_delivery_grants_only_once(env):
    payload = _pack_payload("credits_200")
    assert _send(env, payload).status_code == 200
    second = _send(env, payload)
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert _balance(USER) == 200
    assert _count(LemonSqueezyPurchase) == 1
    assert _txn_count(USER) == 1


def test_replay_with_new_delivery_id_still_grants_once(env):
    """LS 重投会保留 meta.webhook_id；但即便换了 id（人工重放），
    业务侧也必须靠 ls_order_id 兜住 —— 两层幂等互相独立。"""
    assert _send(env, _pack_payload("credits_200")).status_code == 200
    again = _pack_payload("credits_200", webhook_id="a2d4ffff-0000-0000-0000-000000000001")
    res = _send(env, again)
    assert res.status_code == 200
    assert _balance(USER) == 200
    assert _count(LemonSqueezyPurchase) == 1
    assert _count(LemonSqueezyWebhookDelivery) == 2      # 投递层记两条，业务层只一条


# ── F. 不同订单分别履约 ─────────────────────────────────────────────────
def test_different_orders_are_fulfilled_separately(env):
    a = _pack_payload("credits_200", order_id=9569465, webhook_id="a2d40000-0000-0000-0000-000000000001")
    b = _pack_payload("credits_200", order_id=9569466, webhook_id="a2d40000-0000-0000-0000-000000000002")
    assert _send(env, a).status_code == 200
    assert _send(env, b).status_code == 200
    assert _balance(USER) == 400
    assert _count(LemonSqueezyPurchase) == 2


def test_same_pack_two_users_are_isolated(env):
    assert _send(env, _pack_payload("credits_200", order_id=9569470,
                                    webhook_id="a2d40000-0000-0000-0000-00000000000a")).status_code == 200
    assert _send(env, _pack_payload("credits_200", order_id=9569471, user_id=OTHER_USER,
                                    webhook_id="a2d40000-0000-0000-0000-00000000000b")).status_code == 200
    assert _balance(USER) == 200
    assert _balance(OTHER_USER) == 200


# ── G. 未知 / 未配置 variant ────────────────────────────────────────────
def test_unknown_variant_is_not_fulfilled(env):
    res = _send(env, _pack_payload("credits_200", variant="9999999"))
    assert res.status_code == 200
    assert _balance(USER) is None
    assert _count(LemonSqueezyPurchase) == 0


def test_unconfigured_variant_env_is_not_fulfilled(env, monkeypatch):
    monkeypatch.delenv("LEMONSQUEEZY_VARIANT_ID_CREDITS_200", raising=False)
    res = _send(env, _pack_payload("credits_200"))
    assert _count(LemonSqueezyPurchase) == 0


def test_variant_mapped_to_unknown_pack_is_not_fulfilled(env, monkeypatch):
    """variant 配好了、custom 也自洽，但条目在 credits_config 里不存在 ⇒ 不履约。"""
    monkeypatch.setenv("LEMONSQUEEZY_VARIANT_ID_GHOST", "8888888")
    monkeypatch.setattr(ls, "VARIANT_ENV", {**ls.VARIANT_ENV, "ghost_pack": "LEMONSQUEEZY_VARIANT_ID_GHOST"})
    res = _send(env, _pack_payload("credits_200", variant="8888888", declared_pack="ghost_pack"))
    assert res.status_code == 200
    assert _balance(USER) is None
    assert _count(LemonSqueezyPurchase) == 0


# ── H. 档位串档 ─────────────────────────────────────────────────────────
def test_declared_pack_mismatching_variant_is_rejected(env):
    """variant 是 200 档，custom 却声明 2800 档：两个真值不一致 ⇒ 拒发。"""
    res = _send(env, _pack_payload("credits_200", declared_pack="credits_2800"))
    assert res.status_code == 400
    assert res.json()["detail"] == "pack_id_mismatch"
    assert _balance(USER) is None
    assert _count(LemonSqueezyPurchase) == 0


def test_missing_declared_pack_is_rejected(env):
    payload = _pack_payload("credits_200")
    payload["meta"]["custom_data"].pop("pack_id")
    assert _send(env, payload).status_code == 400


# ── I/V. 金额口径 ───────────────────────────────────────────────────────
@pytest.mark.parametrize("cents,reason", [(599, "over-paid"), (399, "under-paid"), (0, "zero")])
def test_amount_mismatch_is_rejected(env, cents, reason):
    res = _send(env, _pack_payload("credits_200", price_cents=cents))
    assert res.status_code == 400, reason
    assert res.json()["detail"] == "amount_mismatch"
    assert _balance(USER) is None
    assert _count(LemonSqueezyPurchase) == 0


def test_discount_making_total_below_list_price_is_rejected(env):
    """实测 discount_total 存在；打折后 total < 标价 ⇒ 按金额口径拒发，不自行反推。"""
    res = _send(env, _pack_payload("credits_200", discount=100))
    assert res.status_code == 400
    assert _count(LemonSqueezyPurchase) == 0


def test_tax_added_on_top_of_list_price_is_rejected_by_current_rule(env):
    """当前口径是"实收必须等于标价"。LS 若在标价之上另计销售税，total>标价 ⇒ 会被拒。

    这条测试是**故意把这个待决策口径钉在明面上**：一旦你决定允许含税差额，
    它会失败，提醒你同时改实现与注释。
    """
    res = _send(env, _pack_payload("credits_200", price_cents=549, tax=50))
    assert res.status_code == 400
    assert res.json()["detail"] == "amount_mismatch"


def test_amount_comparison_is_integer_cents_only():
    """真值换算：4.99 → 499，绝不用浮点比较金额。"""
    truth = ls.pack_truth_for_item("credits_200")
    assert truth["price_cents"] == 499 and isinstance(truth["price_cents"], int)
    assert ls.pack_truth_for_item("credits_2800")["price_cents"] == 3999


# ── J. 币种 ─────────────────────────────────────────────────────────────
def test_non_configured_currency_is_rejected_without_conversion(env):
    res = _send(env, _pack_payload("credits_200", currency="EUR"))
    assert res.status_code == 400
    assert res.json()["detail"] == "currency_not_supported"
    assert _balance(USER) is None
    assert _count(LemonSqueezyPurchase) == 0


def test_missing_currency_is_rejected(env):
    payload = _pack_payload("credits_200")
    payload["data"]["attributes"]["currency"] = ""
    assert _send(env, payload).status_code == 400


# ── K/L. 身份 ───────────────────────────────────────────────────────────
def test_missing_user_id_is_rejected(env):
    payload = _pack_payload("credits_200", user_id=None)
    res = _send(env, payload)
    assert res.status_code == 400
    assert res.json()["detail"] == "invalid_user_id"
    assert _count(LemonSqueezyPurchase) == 0


@pytest.mark.parametrize("bad_user", ["", "   ", "987654", "buyer@example.com",
                                      "ls-user-1", "11111111222233334444555555555555",
                                      "x" * 300])
def test_invalid_user_id_shapes_are_rejected(env, bad_user):
    payload = _pack_payload("credits_200")
    payload["meta"]["custom_data"]["user_id"] = bad_user
    res = _send(env, payload)
    assert res.status_code == 400, bad_user
    assert _balance(bad_user.strip()) is None
    assert _count(LemonSqueezyPurchase) == 0


def test_email_is_never_used_as_identity(env):
    """payload 里有 user_email，但它不参与归因：把 user_id 去掉就该拒。"""
    payload = _pack_payload("credits_200", user_id=None)
    assert payload["data"]["attributes"]["user_email"]
    assert _send(env, payload).status_code == 400


# ── M. quantity ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("qty", [0, 2, 3])
def test_quantity_other_than_one_is_rejected(env, qty):
    res = _send(env, _pack_payload("credits_200", quantity=qty))
    assert res.status_code == 400
    assert res.json()["detail"] == "unexpected_quantity"
    assert _balance(USER) is None
    assert _count(LemonSqueezyPurchase) == 0


# ── N/O/P. 本阶段禁止处理的对象 ─────────────────────────────────────────
def test_subscription_event_is_not_fulfilled(env):
    res = _send(env, ls_payload.subscription_payload())
    assert res.status_code == 200
    assert _count(LemonSqueezyPurchase) == 0
    assert _count(LemonSqueezyMembership) == 0
    assert _count(LemonSqueezyMembershipGrant) == 0
    assert _balance(USER) is None


def test_invoice_event_is_not_fulfilled(env):
    res = _send(env, ls_payload.invoice_payload())
    assert res.status_code == 200
    assert _count(LemonSqueezyMembershipGrant) == 0
    assert _count(LemonSqueezyPurchase) == 0
    assert _balance(USER) is None


def test_membership_order_is_not_fulfilled(env):
    """订阅首开的 order_created（kind=membership）不能发一次性积分。"""
    res = _send(env, ls_payload.order_payload(custom=dict(
        {"user_id": USER, "kind": "membership", "plan_id": "starter", "credits_per_month": "200"})))
    assert res.status_code == 200
    assert _count(LemonSqueezyPurchase) == 0
    assert _balance(USER) is None


def test_refund_event_causes_no_reversal(env):
    assert _send(env, _pack_payload("credits_200")).status_code == 200
    assert _balance(USER) == 200
    res = _send(env, _pack_payload("credits_200", event_name="order_refunded",
                                   refunded=True,
                                   webhook_id="a2d40000-0000-0000-0000-0000000000ff"))
    assert res.status_code == 200
    assert _balance(USER) == 200          # 不扣回
    assert _txn_count(USER) == 1          # 不产生退款流水


# ── U. 订单状态 ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("status", ["pending", "refunded", "failed", "expired", "sOMETHING", ""])
def test_only_paid_orders_are_fulfilled(env, status):
    res = _send(env, _pack_payload("credits_200", status=status))
    assert res.status_code == 200
    assert _balance(USER) is None
    assert _count(LemonSqueezyPurchase) == 0


# ── Q/R. Test / Live 隔离 ───────────────────────────────────────────────
def test_test_mode_pack_is_recorded_as_test(env):
    assert _send(env, _pack_payload("credits_200", test_mode=True)).status_code == 200
    sess = db.SessionLocal()
    try:
        assert sess.scalars(select(LemonSqueezyPurchase)).one().test_mode is True
    finally:
        sess.close()


def test_live_mode_pack_is_recorded_as_live(env):
    assert _send(env, _pack_payload("credits_200", test_mode=False)).status_code == 200
    sess = db.SessionLocal()
    try:
        assert sess.scalars(select(LemonSqueezyPurchase)).one().test_mode is False
    finally:
        sess.close()


def test_production_refuses_test_mode_orders(env, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    res = _send(env, _pack_payload("credits_200", test_mode=True))
    assert res.status_code == 200
    assert _balance(USER) is None
    assert _count(LemonSqueezyPurchase) == 0


def test_production_still_fulfills_live_orders(env, monkeypatch):
    """隔离不是"生产一律不发"：live 事件必须照常履约。"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert _send(env, _pack_payload("credits_200", test_mode=False)).status_code == 200
    assert _balance(USER) == 200


# ── S/T. 失败必须可恢复 ─────────────────────────────────────────────────
def test_grant_failure_releases_claim_so_retry_can_complete(env, monkeypatch):
    """§16 的反例：不能出现"purchase 记了、Credits 没发、重投又被 UNIQUE 挡住"。"""
    real = credits_service.add_credits
    attempts = {"n": 0}

    def flaky(*args, **kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return {"success": False, "error": "boom"}
        return real(*args, **kwargs)

    monkeypatch.setattr(credits_service, "add_credits", flaky)
    payload = _pack_payload("credits_200")
    res = _send(env, payload)
    assert res.status_code == 500
    assert _count(LemonSqueezyPurchase) == 0        # claim 已释放
    assert _balance(USER) is None

    ok = _send(env, payload)                        # 重投：claim 空着，能补发
    assert ok.status_code == 200
    assert _balance(USER) == 200
    assert _count(LemonSqueezyPurchase) == 1
    assert attempts["n"] == 2


def test_ledger_write_failure_grants_nothing(env, monkeypatch):
    """写路径整体故障（含投递台账）⇒ 500，绝不发放、绝不留下记录。"""
    real_maker = db.SessionLocal

    class _WriteDenied:
        def __init__(self, inner):
            self._inner = inner

        def add(self, obj):                      # 任何 ORM 写入都失败
            raise RuntimeError("write denied")

        def __getattr__(self, name):             # 读路径照常，便于本用例自己断言
            return getattr(self._inner, name)

    monkeypatch.setattr(db, "SessionLocal", lambda: _WriteDenied(real_maker()))
    assert _send(env, _pack_payload("credits_200")).status_code == 500
    assert _balance(USER) is None
    assert _count(LemonSqueezyPurchase) == 0


def test_no_partial_state_when_credit_row_insert_fails(env, monkeypatch):
    """claim 成功但发放内部报错 ⇒ 不留半完成状态、不重复发放。"""
    def _raise(*args, **kwargs):
        raise ValueError("no such user")
    monkeypatch.setattr(credits_service, "add_credits", _raise)
    assert _send(env, _pack_payload("credits_200")).status_code == 500
    assert _count(LemonSqueezyPurchase) == 0


# ── 结构性防线 ──────────────────────────────────────────────────────────
def test_delivery_ledger_still_written_even_when_rejected(env):
    """被拒的投递也要留下台账记录 —— 否则无法回答"LS 到底推过什么"。"""
    assert _send(env, _pack_payload("credits_200", currency="EUR")).status_code == 400
    assert _count(LemonSqueezyWebhookDelivery) == 1


def test_response_body_carries_no_pii_or_payload(env):
    res = _send(env, _pack_payload("credits_200"))
    assert res.status_code == 200
    assert set(res.json()) == {"received", "duplicate"}
    assert ls_payload.ORDER_UUID not in res.text
    assert "ls.wh.probe@example.com" not in res.text


def test_no_business_rows_outside_purchases_after_all_paths(env):
    """把三类不该处理的对象各推一遍，subscription 侧两张表必须恒为 0。"""
    _send(env, ls_payload.subscription_payload())
    _send(env, ls_payload.invoice_payload())
    _send(env, _pack_payload("credits_200", event_name="order_refunded", refunded=True,
                             webhook_id="a2d40000-0000-0000-0000-0000000000ee"))
    assert _count(LemonSqueezyMembership) == 0
    assert _count(LemonSqueezyMembershipGrant) == 0


def test_paddle_tables_are_untouched_by_ls_fulfilment(env):
    assert _send(env, _pack_payload("credits_200")).status_code == 200
    sess = db.SessionLocal()
    try:
        assert (sess.scalar(select(func.count()).select_from(db.CreditPackPurchase.__table__)) or 0) == 0
        assert (sess.scalar(select(func.count()).select_from(db.UserMembership.__table__)) or 0) == 0
    finally:
        sess.close()


# ── service 层：outcome 与机器码 ────────────────────────────────────────
# HTTP 响应体刻意不回传内部结论（P2-3 契约），所以"到底是 ignored 还是 rejected"
# 必须在 service 这一层钉住 —— 否则只有日志能看见，回归就抓不到语义漂移。
@pytest.mark.parametrize("kwargs,expected", [
    (dict(),                                  (ls.GRANTED, "granted")),
    (dict(status="pending"),                  (ls.IGNORED, "status:pending")),
    (dict(status=""),                         (ls.IGNORED, "status:unknown")),
    (dict(variant="9999999"),                 (ls.IGNORED, "unconfigured_variant")),
    (dict(declared_pack="credits_2800"),      (ls.REJECTED, "pack_id_mismatch")),
    (dict(currency="EUR"),                    (ls.REJECTED, "currency_not_supported")),
    (dict(price_cents=599),                   (ls.REJECTED, "amount_mismatch")),
    (dict(price_cents=399),                   (ls.REJECTED, "amount_mismatch")),
    (dict(quantity=2),                        (ls.REJECTED, "unexpected_quantity")),
    (dict(user_id=None),                      (ls.REJECTED, "invalid_user_id")),
])
def test_service_returns_the_expected_outcome(env, kwargs, expected):
    event = ls.parse_webhook_event(_pack_payload("credits_200", **kwargs))
    result = ls.fulfill_credit_pack_order(event)
    assert (result.status, result.code) == expected


def test_service_granted_result_carries_the_configured_amount(env):
    event = ls.parse_webhook_event(_pack_payload("credits_2800"))
    result = ls.fulfill_credit_pack_order(event)
    assert result.status == ls.GRANTED
    assert result.credits == 2800                 # 来自 credits_config，不是 payload
    assert _balance(USER) == 2800


@pytest.mark.parametrize("factory", [
    ls_payload.subscription_payload, ls_payload.invoice_payload,
])
def test_service_ignores_non_order_objects(env, factory):
    result = ls.fulfill_credit_pack_order(ls.parse_webhook_event(factory()))
    assert (result.status, result.code) == (ls.IGNORED, "not_a_pack_order")
    assert _count(LemonSqueezyPurchase) == 0


def test_service_ignores_second_delivery_of_the_same_order(env):
    event = ls.parse_webhook_event(_pack_payload("credits_200"))
    assert ls.fulfill_credit_pack_order(event).status == ls.GRANTED
    again = ls.fulfill_credit_pack_order(event)
    assert (again.status, again.code) == (ls.ALREADY_PROCESSED, "already_processed")
    assert again.credits == 0
    assert _balance(USER) == 200

