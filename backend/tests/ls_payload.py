"""Lemon Squeezy webhook 夹具 —— 形状来自 2026-09-25 真实 Test Mode 投递。

存在理由（与 tests/paddle_payload.py 同一教训）：LS 的真实 payload 与官方文档示例
**不一致**，夹具若照文档自造字段，解析与金额校验会在测试里"通过"而在真实回调上
静默失效。这里逐键照抄实测抓到的形状：

  meta 实测 4 键：test_mode / event_name / custom_data / webhook_id
      （文档只说 meta 里有 event_name，是错的）
  order   data.type = "orders"                  attributes 含 first_order_item（扁平）
      实测**没有** order_items / order_item_ids / subscription_id
  subscription data.type = "subscriptions"      attributes 含 first_subscription_item
      实测**没有** interval / interval_count / current_period_start / cancel_at_period_end
  invoice data.type = "subscription-invoices"   attributes 含 subscription_id + billing_reason
      实测**没有** product_id / variant_id / order_id / quantity / price_id

因此本模块刻意不提供 interval，也不给 invoice 造 product/variant/order 字段；
需要这些值时只能由服务端台账反查（P2-5/P2-6）。

id 的类型也照实测：JSON:API 的 data.id 是字符串，attributes 里的数值 id 是整数。
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Optional

# 实测值（test store 482388）
STORE_ID = 482388
CUSTOMER_ID = 9989025
PACK_PRODUCT_ID = 1387476
PACK_VARIANT_ID = 2167238
PACK_PRICE_ID = 3637193
PLAN_PRODUCT_ID = 1387446
PLAN_VARIANT_ID = 2167193
PLAN_PRICE_ID = 3637141
ORDER_ID = 9569465
SUB_ORDER_ID = 9569523
SUBSCRIPTION_ID = 2556628
SUB_ORDER_ITEM_ID = 9493618
SUB_ITEM_ID = 10135648
INVOICE_ID = 8554443
ORDER_UUID = "dd18772b-334c-4308-9989-3995c889911f"
DELIVERY_ID = "a2d4dd6c-f570-4089-8255-e6babb691ffe"

_PACK_CUSTOM = {"user_id": "2091d35f-4a21-4257-9d8a-67546f988dc0", "kind": "credit_pack",
                "pack_id": "credits_200", "credits": "200", "probe": "ls-wh-order"}
_SUB_CUSTOM = {"user_id": "987654", "kind": "membership", "plan_id": "starter",
               "credits_per_month": "100", "probe": "ls-wh-sub"}


def _meta(event_name: str, custom: dict[str, Any], webhook_id: str,
          test_mode: bool) -> dict[str, Any]:
    return {"test_mode": test_mode, "event_name": event_name,
            "custom_data": custom, "webhook_id": webhook_id}


def _money(subtotal: int, tax: int, discount: int = 0) -> dict[str, Any]:
    """LS 把同一组金额用 4 种口径各写一遍，这里按实测键名一次性铺齐。"""
    total = subtotal - discount + tax
    fmt = lambda c: "${}.{:02d}".format(c // 100, c % 100)  # noqa: E731
    return {
        "subtotal": subtotal, "discount_total": discount, "tax": tax, "setup_fee": 0,
        "total": total, "refunded_amount": 0,
        "subtotal_usd": subtotal, "discount_total_usd": discount, "tax_usd": tax,
        "setup_fee_usd": 0, "total_usd": total, "refunded_amount_usd": 0,
        "subtotal_formatted": fmt(subtotal), "discount_total_formatted": fmt(discount),
        "tax_formatted": fmt(tax), "setup_fee_formatted": "$0.00",
        "total_formatted": fmt(total), "refunded_amount_formatted": "$0.00",
    }


def order_payload(*, event_name: str = "order_created", webhook_id: str = DELIVERY_ID,
                  order_id: int = ORDER_ID, order_number: int = 4823881,
                  custom: Optional[dict[str, Any]] = None,
                  variant_id: int = PACK_VARIANT_ID, product_id: int = PACK_PRODUCT_ID,
                  price_id: int = PACK_PRICE_ID, price_cents: int = 499, quantity: int = 1,
                  currency: str = "USD", tax: int = 0, discount: int = 0,
                  status: str = "paid", refunded: bool = False,
                  test_mode: bool = True) -> dict[str, Any]:
    """`order_created`：一次性包与订阅首付都是这个对象。"""
    attrs: dict[str, Any] = {
        "store_id": STORE_ID, "customer_id": CUSTOMER_ID, "affiliate_id": None,
        "referral_amount": 0, "identifier": ORDER_UUID,
        "order_number": order_number,
        "user_name": "LS WH Probe", "user_email": "ls.wh.probe@example.com",
        "currency": currency, "currency_rate": "1.0000",
        "tax_name": None, "tax_rate": "0.00", "tax_inclusive": False,
        "status": status, "status_formatted": "Paid",
        "refunded": refunded, "refunded_at": None,
        **_money(price_cents * quantity, tax, discount),
        "first_order_item": {
            "id": 9493562, "order_id": order_id, "product_id": product_id,
            "variant_id": variant_id, "price_id": price_id,
            "product_name": "200 Credits", "variant_name": "Default",
            "price": price_cents, "quantity": quantity,
            "test_mode": test_mode,
            "created_at": "2026-09-25T15:48:35.000000Z",
            "updated_at": "2026-09-25T15:48:35.000000Z",
        },
        "urls": {"receipt": "https://melovar.lemonsqueezy.com/receipts/order/1"},
        "created_at": "2026-09-25T15:48:35.000000Z",
        "updated_at": "2026-09-25T15:48:36.000000Z",
        "test_mode": test_mode,
    }
    return {"meta": _meta(event_name, custom if custom is not None else dict(_PACK_CUSTOM),
                          webhook_id, test_mode),
            "data": {"type": "orders", "id": str(order_id), "attributes": attrs}}


def subscription_payload(*, event_name: str = "subscription_created",
                         webhook_id: str = "a2d4e024-d285-43e4-92bf-5f93e9fd4c9e",
                         subscription_id: int = SUBSCRIPTION_ID,
                         order_id: int = SUB_ORDER_ID,
                         custom: Optional[dict[str, Any]] = None,
                         variant_id: int = PLAN_VARIANT_ID,
                         product_id: int = PLAN_PRODUCT_ID,
                         price_id: int = PLAN_PRICE_ID,
                         status: str = "active", cancelled: bool = False,
                         ends_at: Optional[str] = None,
                         test_mode: bool = True) -> dict[str, Any]:
    """`subscription_*`：注意**没有** interval —— 实测确认 payload 不提供计费周期。"""
    attrs: dict[str, Any] = {
        "store_id": STORE_ID, "customer_id": CUSTOMER_ID, "order_id": order_id,
        "order_item_id": SUB_ORDER_ITEM_ID, "product_id": product_id,
        "variant_id": variant_id, "product_name": "Starter", "variant_name": "Default",
        "user_name": "LS WH Probe", "user_email": "ls.wh.probe@example.com",
        "status": status, "status_formatted": "Active",
        "card_brand": "visa", "card_last_four": "4242", "payment_processor": "stripe",
        "pause": None, "cancelled": cancelled, "trial_ends_at": None,
        "billing_anchor": 25,
        "first_subscription_item": {
            "id": SUB_ITEM_ID, "subscription_id": subscription_id, "price_id": price_id,
            "quantity": 1, "is_usage_based": False,
            "created_at": "2026-09-25T15:56:12.000000Z",
            "updated_at": "2026-09-25T15:56:12.000000Z",
        },
        "urls": {
            "update_payment_method": "https://melovar.lemonsqueezy.com/checkout/buy/x",
            "customer_portal": "https://melovar.lemonsqueezy.com/portal/y",
            "customer_portal_update_subscription": "https://melovar.lemonsqueezy.com/portal/z",
        },
        "renews_at": "2026-10-25T15:56:05.000000Z", "ends_at": ends_at,
        "created_at": "2026-09-25T15:56:07.000000Z",
        "updated_at": "2026-09-25T15:56:12.000000Z",
        "test_mode": test_mode,
    }
    return {"meta": _meta(event_name, custom if custom is not None else dict(_SUB_CUSTOM),
                          webhook_id, test_mode),
            "data": {"type": "subscriptions", "id": str(subscription_id),
                     "attributes": attrs}}


def invoice_payload(*, event_name: str = "subscription_payment_success",
                    webhook_id: str = "a2d4e054-de02-4383-a26a-a460f3f0e0d2",
                    invoice_id: int = INVOICE_ID,
                    subscription_id: int = SUBSCRIPTION_ID,
                    custom: Optional[dict[str, Any]] = None,
                    billing_reason: str = "initial", status: str = "paid",
                    total_cents: int = 499, currency: str = "USD",
                    refunded: bool = False, test_mode: bool = True) -> dict[str, Any]:
    """`subscription_payment_success` / `_recovered` / `_failed` / `_refunded`。

    实测关键点：invoice 只有 subscription_id，**没有** product_id / variant_id /
    order_id / quantity；且 success 与 recovered 会**共用同一个 invoice id**。
    """
    attrs: dict[str, Any] = {
        "store_id": STORE_ID, "subscription_id": subscription_id,
        "customer_id": CUSTOMER_ID, "affiliate_id": None, "referral_amount": 0,
        "user_name": "LS WH Probe", "user_email": "ls.wh.probe@example.com",
        "billing_reason": billing_reason, "card_brand": "visa", "card_last_four": "4242",
        "currency": currency, "currency_rate": "1.0000",
        "status": status, "status_formatted": "Paid",
        "refunded": refunded, "refunded_at": None,
        "tax_inclusive": False,
        **_money(total_cents, 0),
        "urls": {"invoice_url": "https://melovar.lemonsqueezy.com/invoices/1"},
        "created_at": "2026-09-25T15:56:38.000000Z",
        "updated_at": "2026-09-25T15:56:44.000000Z",
        "test_mode": test_mode,
    }
    return {"meta": _meta(event_name, custom if custom is not None else dict(_SUB_CUSTOM),
                          webhook_id, test_mode),
            "data": {"type": "subscription-invoices", "id": str(invoice_id),
                     "attributes": attrs}}


def encode(payload: dict[str, Any], **kwargs: Any) -> bytes:
    """返回**将要被签名与发送的那一份字节**。验签永远针对这些字节，不做二次序列化。"""
    kwargs.setdefault("separators", (",", ":"))
    return json.dumps(payload, **kwargs).encode("utf-8")


def sign(body: bytes, secret: str) -> str:
    """LS 官方算法：HMAC-SHA256(secret, raw body) 的 hex digest，无 ts: 前缀。"""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
