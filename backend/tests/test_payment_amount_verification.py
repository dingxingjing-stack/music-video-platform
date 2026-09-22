"""Paddle 交易金额/币种校验（Critical-1 + Critical-2 的回归哨兵）。

存在理由：`_verify_paid_amount` 曾按顶层 grand_total/subtotal/amounts 取金额，而真实
Paddle Billing v2 载荷把这些放在 details.totals / details.payout_totals 里 —— 于是校验
在真实回调上静默变成空操作，而旧夹具因为自造顶层字段仍然全绿。本文件的所有夹具都用
**真实形状**（金额只出现在 details.totals，price 定义内嵌在 items[].price）。
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

USER = "fx-buyer"
SECRET = "pdl_ntfset_fx_test"
PACK_ENVS = {
    "PADDLE_PRICE_ID_CREDITS_200": "pri_200credits",
    "PADDLE_PRICE_ID_CREDITS_500": "pri_500credits",
    "PADDLE_PRICE_ID_CREDITS_1200": "pri_1200credits",
    "PADDLE_PRICE_ID_CREDITS_2800": "pri_2800credits",
}

# 2026-09-22 从 sandbox 真实 transactions.get 回读到的结构（金额只在 details.totals）。
# 注意 items[0] 只有 price / quantity / proration 三个键 —— 真实 Paddle 就是不给 price_id，
# 它是从内嵌 price.id 里读出来的（REST 与 webhook 都是这个形状，已实测）。
REAL_RECORDED_TRANSACTION = {
    "id": "txn_01m352dqwvcwjw53vya3mybwhf",
    "status": "canceled",
    "currency_code": "USD",
    "customer_id": None,
    "subscription_id": None,
    "billing_period": {"started_at": "2026-09-22T17:25:40Z", "ends_at": "2026-10-22T17:25:40Z"},
    "custom_data": None,
    "items": [{"quantity": 1, "proration": None,
               "price": {"id": "pri_200credits", "name": "Monthly", "type": "standard",
                         "status": "active", "product_id": "pro_01m3510p3nr4a2zss457azqba9",
                         "tax_mode": "location", "quantity": {"minimum": 1, "maximum": 1},
                         "billing_cycle": {"interval": "month", "frequency": 1},
                         "trial_period": None, "custom_data": None,
                         "description": "Melovar Starter monthly - 200 credits",
                         "unit_price": {"amount": "499", "currency_code": "USD"},
                         "unit_price_overrides": []}}],
    "details": {
        "tax_rates_used": [],
        "totals": {"subtotal": "499", "tax": "0", "discount": "0", "total": "499",
                   "grand_total": "499", "grand_total_tax": "0", "fee": None,
                   "credit": "0", "credit_to_balance": "0", "balance": "499",
                   "earnings": None, "currency_code": "USD", "exchange_rate": "1"},
        "payout_totals": None,
        "line_items": [],
    },
}

# 2026-09-22 从 Paddle 实际投递给我们端点的 transaction.completed 请求体里逐字摘出的
# 金额/条目结构（payments 里有 captured 记录、payout_totals 已填充）。这份是 Paddle 样例
# 账户的交易，价格不属于 Melovar 目录，所以只能做**解析层**断言，不能端到端发放。
REAL_COMPLETED_EVENT_DATA = {
    "id": "txn_01hv8wptq8987qeep44cyrewp9",
    "status": "completed",
    "currency_code": "USD",
    "subscription_id": "sub_01hv8x29kz0t586xy6zn1a62ny",
    "custom_data": None,
    "origin": "web",
    "items": [
        {"quantity": 10, "proration": None,
         "price": {"id": "pri_01gsz8x8sawmvhz1pv30nge1ke", "tax_mode": "account_setting",
                   "unit_price": {"amount": "3000", "currency_code": "USD"},
                   "unit_price_overrides": []}},
        {"quantity": 1, "proration": None,
         "price": {"id": "pri_01h1vjfevh5etwq3rb416a23h2", "tax_mode": "account_setting",
                   "unit_price": {"amount": "10000", "currency_code": "USD"},
                   "unit_price_overrides": []}},
        {"quantity": 1, "proration": None,
         "price": {"id": "pri_01gsz98e27ak2tyhexptwc58yk", "tax_mode": "account_setting",
                   "unit_price": {"amount": "19900", "currency_code": "USD"},
                   "unit_price_overrides": []}},
    ],
    "details": {
        "totals": {"fee": "3311", "tax": "5315", "total": "65215", "credit": "0",
                   "balance": "0", "discount": "0", "earnings": "56589",
                   "subtotal": "59900", "grand_total": "65215", "currency_code": "USD",
                   "grand_total_tax": "5315", "credit_to_balance": "0"},
        "payout_totals": {"fee": "3311", "tax": "5315", "total": "65215", "credit": "0",
                          "balance": "0", "discount": "0", "earnings": "56589",
                          "fee_rate": "0.05", "subtotal": "59900", "grand_total": "65215",
                          "currency_code": "USD", "exchange_rate": "1",
                          "grand_total_tax": "5315", "credit_to_balance": "0"},
        "adjusted_totals": None,
        "adjusted_payout_totals": None,
        "tax_rates_used": [{"tax_rate": "0.08875"}],
        "line_items": [{"price_id": "pri_01gsz8x8sawmvhz1pv30nge1ke", "quantity": 10,
                        "tax_rate": "0.08875",
                        "totals": {"tax": "2662", "total": "32662", "discount": "0",
                                   "subtotal": "30000"}}],
    },
}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = str(tmp_path / "fx.db")
    eng = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    from app.db.database import Base
    Base.metadata.create_all(bind=eng)
    monkeypatch.setattr(credits_service, "SessionLocal", sessionmaker(bind=eng))
    monkeypatch.setattr(credit_pack_service, "SessionLocal", sessionmaker(bind=eng))
    from app.services import ai_limits
    monkeypatch.setattr(ai_limits, "_DB_PATH", db)
    monkeypatch.setenv("PADDLE_WEBHOOK_SECRET", SECRET)
    for k, v in PACK_ENVS.items():
        monkeypatch.setenv(k, v)
    credits_service.add_credits(USER, 20, "admin_adjustment", description="seed")
    return eng


def _balance() -> int:
    return int(credits_service.get_balance(USER))


def _rows(eng) -> int:
    s = eng.connect()
    try:
        return int(s.execute(text("SELECT COUNT(*) FROM credit_pack_purchases")).scalar())
    finally:
        s.close()


def _post(body: bytes, signature: str | None = None):
    app = FastAPI()
    app.include_router(credits_router.router)
    app.dependency_overrides[get_verified_user_id] = lambda: USER
    ts = int(time.time())
    sig = signature if signature is not None else hmac.new(
        SECRET.encode(), f"{ts}:{body.decode()}".encode(), hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json",
               **({"Paddle-Signature": f"ts={ts};h1={sig}"} if sig else {})}
    r = TestClient(app).post("/api/v1/credits/paddle/webhook", content=body, headers=headers)
    return r.status_code, (r.json() if r.content else None)


def _real_txn(*, price_id="pri_200credits", txn_id="txn_fx", currency="USD",
              subtotal="499", tax="0", total=None, grand_total=None, quantity=1,
              unit_amount="499", unit_currency="USD", override=None, extra_items=None,
              status="completed", event_type="transaction.completed",
              custom_data=None) -> bytes:
    """构造**真实形状**的 transaction.completed。

    金额只出现在 details.totals，price 定义内嵌在 items[].price，且
    total = subtotal - discount + tax（本夹具 discount 恒为 0）。
    传 price_id=None 会刻意造出真实事件那种"items[] 只有 price/quantity/proration、
    没有 price_id"的形状，用来守 price.id 回退链。
    """
    unit_price = {"amount": unit_amount, "currency_code": unit_currency}
    overrides = [{"country_codes": [code[:2].upper()],
                  "unit_price": {"amount": str(value), "currency_code": code}}
                 for code, value in sorted((override or {}).items())]
    item: dict = {"price": {"id": price_id or "pri_real_only",
                            "unit_price": unit_price,
                            "unit_price_overrides": overrides},
                  "quantity": quantity, "proration": None}
    if price_id is not None:
        item = {"price_id": price_id, **item}
    items = [item] + (extra_items or [])
    resolved_total = str(int(subtotal) + int(tax)) if total is None else str(total)
    resolved_grand = resolved_total if grand_total is None else str(grand_total)
    data = {
        "id": txn_id,
        "status": status,
        "currency_code": currency,
        "custom_data": custom_data if custom_data is not None else {
            "user_id": USER, "kind": "credit_pack", "pack_id": "credits_200", "credits": "200"},
        "items": items,
        "details": {"tax_rates_used": [],
                    "totals": {"subtotal": str(subtotal), "tax": str(tax),
                               "discount": "0", "total": resolved_total,
                               "grand_total": resolved_grand,
                               "grand_total_tax": str(tax), "currency_code": currency,
                               "credit": "0", "credit_to_balance": "0", "balance": "0",
                               "fee": None, "earnings": None},
                    "payout_totals": None, "line_items": []},
    }
    return json.dumps({"event_id": "evt_" + txn_id, "event_type": event_type,
                       "occurred_at": "2026-09-23T00:00:00Z", "data": data}).encode()


# ── 1. 真实载荷形状能被解析 ─────────────────────────────────────────
def test_real_paddle_payload_is_parsed():
    a = paddle_service.extract_payment_amounts(REAL_RECORDED_TRANSACTION)
    assert (a.currency, a.subtotal, a.total, a.grand_total) == ("USD", 499, 499, 499)
    assert a.item_count == 1 and a.quantity == 1
    assert a.price_id == "pri_200credits"
    assert a.unit_amount == 499 and a.unit_currency == "USD"
    assert a.due_amount == 499, "真实载荷必须能推出同币种应收额"


# ── 1b. 真实 transaction.completed 载荷：details.totals.total 必须读得到 ──
def test_real_completed_payload_total_is_parsed():
    """取自 Paddle 实际投递的 completed 请求体。它有三个 item，所以只能验解析层。"""
    a = paddle_service.extract_payment_amounts(REAL_COMPLETED_EVENT_DATA)
    assert (a.currency, a.item_count) == ("USD", 3)
    assert a.subtotal == 59900 and a.total == 65215 and a.grand_total == 65215
    assert a.total is not None, "completed 载荷的 details.totals.total 必须被解析出来"
    # payout_totals 已解析但不参与拒绝：它带 fee_rate/fee，earnings=税前 subtotal−fee
    assert (a.payout_currency, a.payout_grand_total) == ("USD", 65215)


def test_real_completed_shape_grants_end_to_end(env):
    """把真实 completed 的字段顺序（total=subtotal+tax、grand_total=total）套到我们的价上。"""
    code, resp = _post(_real_txn(txn_id="txn_real_e2e", subtotal="419", tax="80"))
    assert code == 200 and resp["granted_credits"] == 200, resp
    assert _balance() == 220 and _rows(env) == 1


# ── 1c. Critical-3 回归：tax_mode=location 把 subtotal 压低，绝不能据此判少付 ──
# 数值来自 sandbox transactions.preview 对同一张 499 USD 价格的实测（只读、未建单）。
@pytest.mark.parametrize("country,subtotal,tax", [
    ("US", "499", "0"),    # 无税
    ("JP", "454", "45"),   # 10% 消费税，含在标价内
    ("DE", "419", "80"),   # 19% VAT，含在标价内
])
def test_tax_inclusive_pricing_is_not_mistaken_for_underpayment(env, country, subtotal, tax):
    """核心回归：subtotal < 标价是含税定价的正常结果，不是少付。"""
    amounts = paddle_service.extract_payment_amounts(json.loads(_real_txn(
        subtotal=subtotal, tax=tax))["data"])
    assert (amounts.total, amounts.grand_total, amounts.due_amount) == (499, 499, 499)
    if int(tax):
        # 这条断言是本次回归的意义所在：subtotal 必须真的低于标价，否则它没在测 Critical-3
        assert amounts.subtotal < amounts.due_amount, "含税夹具必须造出被压低的 subtotal"
    else:
        assert amounts.subtotal == amounts.due_amount

    code, resp = _post(_real_txn(txn_id=f"txn_tax_{country}", subtotal=subtotal, tax=tax))
    assert code == 200, f"{country} 买家付满 499 却被拒：{resp}"
    assert resp["granted_credits"] == 200, resp
    assert _balance() == 220 and _rows(env) == 1


def test_genuine_underpayment_with_tax_is_still_refused(env):
    """真少付：含税口径下 total 只有 399，即使 subtotal+tax 看着像那么回事也必须拒。"""
    code, resp = _post(_real_txn(txn_id="txn_low", subtotal="363", tax="36",
                                 total="399", grand_total="399"))
    assert code == 400 and resp["detail"] == "amount below configured price", resp
    assert _balance() == 20 and _rows(env) == 0


def test_total_above_grand_total_is_refused(env):
    """税额不能凭空造出付款：total > grand_total 说明 totals 自相矛盾。"""
    code, resp = _post(_real_txn(txn_id="txn_incons", subtotal="499", tax="80",
                                 total="579", grand_total="499"))
    assert code == 400 and resp["detail"] == "inconsistent totals", resp
    assert _balance() == 20 and _rows(env) == 0


# ── 1d. 真实事件的 items[] 没有 price_id，只有内嵌 price.id ───────────
def test_price_id_is_read_from_embedded_price_when_item_has_no_price_id(env):
    """实测：webhook 的 items[] 只有 {price, quantity, proration}。

    路由与校验都必须靠 item.price.id 兜住；若有人把回退链改成只读 item["price_id"]，
    这条会立刻变红（发放会变成 unconfigured_price 而被忽略）。
    """
    body = _real_txn(txn_id="txn_no_pid", price_id=None)
    item = json.loads(body)["data"]["items"][0]
    assert "price_id" not in item and item["price"]["id"] == "pri_real_only"
    assert paddle_service.extract_price_id(json.loads(body)["data"]) == "pri_real_only"

    # pri_real_only 不在后端配置里 → 正确地被当作未配置价格忽略，且不发 Credits
    code, resp = _post(body)
    assert code == 200 and resp.get("ignored") == "unconfigured_price", resp
    assert _balance() == 20 and _rows(env) == 0


def test_price_id_fallback_grants_for_a_configured_price(env):
    """同一条回退链命中配置里的 Price ID 时必须正常发放。"""
    body = json.loads(_real_txn(txn_id="txn_fb", price_id=None))
    body["data"]["items"][0]["price"]["id"] = "pri_200credits"
    code, resp = _post(json.dumps(body).encode())
    assert code == 200 and resp["granted_credits"] == 200, resp
    assert _balance() == 220 and _rows(env) == 1


def test_real_shaped_payment_grants_once(env):
    code, resp = _post(_real_txn())
    assert code == 200, resp
    assert resp["granted_credits"] == 200 and _balance() == 220
    assert _rows(env) == 1


# ── 10. Critical-1 回归：校验不再是死代码（真实形状的少付必须被拒） ──
def test_real_shape_underpayment_is_actually_rejected(env):
    """顶层带 grand_total 的旧夹具会"假通过"；这条用真实形状证明闸门真的在跑。"""
    code, resp = _post(_real_txn(subtotal="399", grand_total="399"))
    assert code == 400, resp
    assert resp["detail"] == "amount below configured price"
    assert _balance() == 20 and _rows(env) == 0


def test_legacy_top_level_amount_shape_is_no_longer_accepted(env):
    """真实 Paddle 从不发顶层 grand_total；这种载荷必须被拒，而不是被当成付款证据。"""
    body = json.dumps({"event_id": "evt_legacy", "event_type": "transaction.completed",
                       "occurred_at": "2026-09-23T00:00:00Z",
                       "data": {"id": "txn_legacy", "status": "completed",
                                "currency_code": "USD", "grand_total": "499",
                                "custom_data": {"user_id": USER, "kind": "credit_pack",
                                                "pack_id": "credits_200", "credits": "200"},
                                "items": [{"price_id": "pri_200credits", "quantity": 1}]}}).encode()
    code, resp = _post(body)
    assert code == 400 and resp["detail"] == "payment totals missing", resp
    assert _balance() == 20 and _rows(env) == 0


# ── 2. USD 少付 ────────────────────────────────────────────────────
def test_usd_underpaid_refused(env):
    code, resp = _post(_real_txn(subtotal="399", grand_total="499"))
    assert code == 400 and resp["detail"] == "amount below configured price", resp
    assert _balance() == 20


def test_usd_overpaid_still_granted(env):
    """取高不拒：Paddle 的 grand_total 可能含税/附加项。"""
    code, resp = _post(_real_txn(subtotal="499", grand_total="599"))
    assert code == 200 and resp["granted_credits"] == 200, resp


# ── 3/4. 本地货币：同币种内比较，绝不做汇率换算 ───────────────────
def test_eur_paid_with_eur_override_grants(env):
    """EUR 4.59 对 override 里的 459 —— 同币种比较，通过。"""
    code, resp = _post(_real_txn(currency="EUR", subtotal="459", grand_total="459",
                                 override={"EUR": 459}))
    assert code == 200 and resp["granted_credits"] == 200, resp
    s = env.connect()
    try:
        row = s.execute(text("SELECT currency, amount_cents FROM credit_pack_purchases")).fetchone()
    finally:
        s.close()
    assert row[0] == "EUR" and int(row[1]) == 459, "落库必须记客户实付币种与金额"


def test_jpy_zero_decimal_not_multiplied_by_100(env):
    """JPY 是最小货币单位即整数日元：690 对 690 必须通过，不能被当成分。"""
    code, resp = _post(_real_txn(currency="JPY", subtotal="690", grand_total="690",
                                 override={"JPY": 690}))
    assert code == 200 and resp["granted_credits"] == 200, resp


def test_jpy_underpaid_refused(env):
    code, resp = _post(_real_txn(currency="JPY", subtotal="600", grand_total="600",
                                 override={"JPY": 690}))
    assert code == 400 and resp["detail"] == "amount below configured price", resp
    assert _balance() == 20


# ── 5/6. 币种白名单 ───────────────────────────────────────────────
@pytest.mark.parametrize("currency", ["BRL", "RUB", "UAH", "ZAR"])
def test_not_allowed_currency_refused(env, currency):
    code, resp = _post(_real_txn(currency=currency, subtotal="499", grand_total="499",
                                 override={currency: 499}))
    assert code == 400 and resp["detail"] == "currency_not_supported", resp
    assert _balance() == 20 and _rows(env) == 0


def test_allow_list_is_env_configurable(env, monkeypatch):
    monkeypatch.setenv("PADDLE_ALLOWED_PAYMENT_CURRENCIES", "USD,GBP")
    assert paddle_service.allowed_payment_currencies() == ("USD", "GBP")
    code, resp = _post(_real_txn(currency="EUR", subtotal="459", grand_total="459",
                                 override={"EUR": 459}))
    assert code == 400 and resp["detail"] == "currency_not_supported", resp


# ── 7/8. 数量与条目数 ─────────────────────────────────────────────
def test_quantity_two_refused(env):
    code, resp = _post(_real_txn(quantity=2))
    assert code == 400 and resp["detail"] == "unexpected quantity", resp
    assert _balance() == 20 and _rows(env) == 0


def test_multi_item_transaction_refused(env):
    extra = {"price_id": "pri_500credits", "quantity": 1,
             "price": {"id": "pri_500credits",
                       "unit_price": {"amount": "999", "currency_code": "USD"}}}
    code, resp = _post(_real_txn(extra_items=[extra]))
    assert code == 400 and resp["detail"] == "unexpected item count", resp
    assert _balance() == 20


# ── 9. 伪造币种：顶层写 EUR 但 price 没有 EUR 定义 ─────────────────
def test_currency_without_price_definition_refused(env):
    code, resp = _post(_real_txn(currency="EUR", subtotal="459", grand_total="459"))
    assert code == 400 and resp["detail"] == "no configured amount for currency", resp
    assert _balance() == 20 and _rows(env) == 0


def test_price_id_mismatch_guard_blocks_forged_routing():
    """纵深防御：路由用的 price_id 与交易内嵌 price 不一致时必须拒。

    当前路由与校验都读同一个 items[0]，所以这条只能直接调函数来证明闸门存在；
    若将来有人改成从 custom_data 或别处取 price_id，这条会立刻抓住。
    """
    from fastapi import HTTPException
    obj = json.loads(_real_txn())["data"]
    ok = paddle_service.extract_payment_amounts(obj)
    assert ok.due_amount == 499
    with pytest.raises(HTTPException) as exc:
        credits_router._verify_paid_amount(label="t", obj=obj, expected_cents=499,
                                           expected_currency="USD",
                                           expected_price_id="pri_2800credits")
    assert exc.value.status_code == 400
    assert exc.value.detail == "price id mismatch"


# ── 幂等与签名仍然有效（不回归） ───────────────────────────────────
def test_duplicate_delivery_grants_once(env):
    body = _real_txn(txn_id="txn_dup")
    assert _post(body)[0] == 200
    code, resp = _post(body)
    assert code == 200 and resp["status"] == "already_processed", resp
    assert _balance() == 220 and _rows(env) == 1


def test_bad_signature_still_rejected(env):
    body = _real_txn(txn_id="txn_sig")
    ts = int(time.time())
    code, resp = _post(body, signature="0" * 64)
    assert code == 401 and resp["detail"] == "invalid signature", (code, resp)
    assert _balance() == 20 and _rows(env) == 0
    assert ts > 0
