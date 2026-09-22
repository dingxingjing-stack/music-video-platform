"""Paddle 回调夹具的真实载荷形状工具。

存在理由：Paddle Billing v2 的 transaction 对象把金额放在 details.totals
（客户支付币种）与 details.payout_totals（余额币种）里，顶层只有 currency_code，
**没有**顶层 grand_total / subtotal / amounts；price 定义则内嵌在 items[].price。
夹具若自造顶层金额字段，金额校验会在测试里"通过"而在真实回调上静默失效
（Critical-1 就是这么漏掉的）。所有交易夹具都应经 normalize_transaction_payload()
转成真实形状后再签名发出。
"""

from __future__ import annotations

from typing import Any, Optional

from app.services import credits_config


def _stub_country(currency_code: str) -> str:
    # 金额校验只按 unit_price.currency_code 取 override 的币种，从不读 country_codes；
    # 这里只需让夹具在形状上像真数据，不必维护币种→国家对照表。
    return currency_code[:2].upper()


def configured_price_block(price_id: str, *, currency: Optional[str] = None,
                           override: Optional[dict[str, int]] = None) -> dict[str, Any]:
    """按后端配置（真实 Price ID → 金额）造一个 Paddle price 对象。

    配置来源与生产校验用的是同一份 credits_config，所以夹具不会和实现各说各话。
    override 按 Paddle schema 记载的列表形状落：unit_price_overrides:
    [{country_codes, unit_price: {amount, currency_code}}]。
    """
    cfg = credits_config.resolve_pack_by_price_id(price_id) or \
        credits_config.resolve_plan_by_price_id(price_id)
    base_currency = (cfg or {}).get("currency", "USD")
    amount = str((cfg or {}).get("price_cents", 0))
    price: dict[str, Any] = {
        "id": price_id, "description": f"fixture price {price_id}",
        "unit_price": {"amount": amount, "currency_code": base_currency},
        "unit_price_overrides": [
            {"country_codes": [_stub_country(code)],
             "unit_price": {"amount": str(value), "currency_code": code}}
            for code, value in sorted((override or {}).items())],
    }
    return price


def normalize_transaction_payload(data: dict[str, Any], *,
                                  override: Optional[dict[str, int]] = None) -> dict[str, Any]:
    """把简写的交易夹具转成真实 Paddle 形状。

    - 顶层 grand_total/subtotal → 移进 details.totals（同币种）
    - items[0] 补上内嵌 price（金额取自后端配置）
    已经是真实形状（有 details 且无顶层 grand_total）的原样返回。

    这些老夹具不涉及税，所以 tax=0、total 与 subtotal 同值——这是自洽的，不是偷懒。
    含税（tax_mode=location 压低 subtotal）的口径由 test_payment_amount_verification.py
    里的 JP/DE 专项用例覆盖；只测 tax=0 会让"误比 subtotal"这类 bug 全绿通过。
    """
    if "grand_total" not in data and "subtotal" not in data:
        return data

    out = dict(data)
    currency = str(out.get("currency_code") or "USD").upper()
    subtotal = out.pop("subtotal", None)
    grand_total = out.pop("grand_total", None)
    if subtotal is None:
        subtotal = grand_total
    totals = {"subtotal": str(subtotal) if subtotal is not None else None,
              "tax": "0", "total": str(subtotal) if subtotal is not None else None,
              "grand_total": str(grand_total) if grand_total is not None else None,
              "currency_code": currency}
    details = dict(out.get("details") or {})
    details["totals"] = totals
    details.setdefault("payout_totals", None)
    out["details"] = details

    items = []
    for item in out.get("items") or []:
        entry = dict(item) if isinstance(item, dict) else item
        if isinstance(entry, dict) and "price" not in entry and entry.get("price_id"):
            entry["price"] = configured_price_block(str(entry["price_id"]), override=override)
        items.append(entry)
    out["items"] = items
    return out
