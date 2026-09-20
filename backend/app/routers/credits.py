"""Credits 路由 —— /api/v1/credits

- GET  /packages       公开：旧 beta 套餐列表（无需登录，保留兼容）
- GET  /costs          公开：信用消耗规则（可配置占位）
- GET  /balance        登录：当前余额 + 奖励领取状态
- POST /purchase       登录：购买（当前支付未接入 → payment_not_configured，绝不直接加 Credits）
- POST /bonus/welcome | /bonus/email-verification | /bonus/first-song（内部/幂等领取）

积分补充包（一次性，Paddle）：
- GET  /packs          公开：已配置的一次性积分包（价格与积分数来自后端配置）
- POST /checkout       登录：服务端向 Paddle 建单，返回 transaction_id 给 Paddle.js
- GET  /purchases      登录：本人积分包购买记录
- POST /paddle/webhook Paddle 回调：验签 + 幂等发放（发放 Credits 的唯一入口）

身份：凡涉及用户余额/状态的端点，唯一可信来源 = verified JWT（get_verified_user_id）。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from app.services.auth_identity import get_verified_user_id
from app.services.credits_config import (
    PACKAGES,
    CREDIT_COSTS,
    FREE_TOTAL,
    CREDIT_PACKS,
    MEMBERSHIP_PLANS,
    MEMBERSHIP_INTERVAL,
    get_credit_packs,
    get_pack,
    resolve_pack_by_price_id,
    get_membership_plans,
    get_membership_plan,
    resolve_plan_by_price_id,
)
from app.services import credit_pack_service, credits_service, membership_service, paddle_mirror, paddle_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/credits", tags=["credits"])

# 支付 Provider 是否已接入；积分补充包由 PADDLE_API_KEY 是否配置决定。
PAYMENT_PROVIDER_CONFIGURED = os.getenv("PAYMENT_PROVIDER", "").strip().lower() in ("stripe", "lemon_squeezy", "paddle")


class PurchaseRequest(BaseModel):
    package_id: str
    # 预留：payment_method / idempotency_key 供未来支付接入
    payment_method: str = "card"
    idempotency_key: str | None = None


class PackCheckoutRequest(BaseModel):
    """客户端只能指定"要买哪个包 / 订哪个会员"；积分数量、价格、Price ID 全部由后端决定。"""
    pack_id: Optional[str] = None
    plan_id: Optional[str] = None


@router.get("/packages")
async def list_packages():
    """LEGACY：Beta 时期的草稿套餐表，已不再是任何购买路径的数据源。

    现行价格只在前两处生效：credits_config.MEMBERSHIP_PLANS（订阅）与
    CREDIT_PACKS（一次性补充包）；前端 PricingPage 也不再读这个端点。
    保留只为兼容可能的外部引用，并明确标为 deprecated，前端绝不据此下单。
    """
    return {"free_total": FREE_TOTAL, "packages": PACKAGES,
            "deprecated": True, "use": "/api/v1/credits/plans 与 /api/v1/credits/packs"}


@router.get("/packs")
async def list_packs():
    """一次性积分补充包（公开展示）。未配置 Paddle Price ID 的包不会出现。"""
    return {
        "currency": "USD",
        "recurring": False,
        "paddle_configured": paddle_service.checkout_enabled(),
        "paddle_env": paddle_service.paddle_env() if paddle_service.checkout_enabled() else None,
        "client_token": paddle_service.client_token() or None,
        "packs": _public_packs(),
    }


@router.get("/plans")
async def list_plans():
    """会员计划（Recurring / Monthly，公开展示）。未配置的不会出现，前端不出现假按钮。"""
    return {
        "currency": "USD",
        "interval": MEMBERSHIP_INTERVAL,
        "recurring": True,
        "paddle_configured": paddle_service.checkout_enabled(),
        "paddle_env": paddle_service.paddle_env() if paddle_service.checkout_enabled() else None,
        "client_token": paddle_service.client_token() or None,
        "plans": _public_plans(),
    }


@router.get("/billing-status")
async def billing_status():
    """配置自检：只回答"某项是否已配置"，绝不回显任何密钥/Token 的值。"""
    required = {
        "PADDLE_API_KEY": bool(paddle_service.api_key()),
        "PADDLE_CLIENT_TOKEN": bool(paddle_service.client_token()),
        "PADDLE_WEBHOOK_SECRET": bool(paddle_service.webhook_secrets()),
    }
    credit_pack_prices = {name: bool(os.getenv(name)) for name in
                          (p["price_env"] for p in CREDIT_PACKS)}
    membership_prices = {name: bool(os.getenv(name)) for name in
                         (p["price_env"] for p in MEMBERSHIP_PLANS)}
    return {
        "paddle_env": paddle_service.paddle_env(),
        "api_base_url": paddle_service.api_base_url(),
        "webhook_path": "/api/v1/credits/paddle/webhook",
        "credentials_present": required,
        "missing_credentials": [k for k, v in required.items() if not v],
        "credit_pack_prices_configured": sum(credit_pack_prices.values()),
        "membership_prices_configured": sum(membership_prices.values()),
        "packs_ready": all(credit_pack_prices.values()) and all(required.values()),
        "plans_ready": all(membership_prices.values()) and all(required.values()),
        "credential_warnings": paddle_service.credential_warnings(),
        "checkout_blocked_reason": paddle_service.checkout_blocked_reason(),
        "price_env_keys": {"credit_packs": sorted(credit_pack_prices),
                           "memberships": sorted(membership_prices)},
    }


@router.get("/membership")
async def get_membership(user_id: str = Depends(get_verified_user_id)):
    """当前会员等级与到期时间（同一套用户/积分系统，不另建账号）。

    paid_access 由订阅镜像判定（active/trialing 才算有效），与等级信息一并返回，
    供账号页决定"续费/管理订阅"入口是否出现。
    """
    return {"membership": membership_service.get_active_membership(user_id),
            "paid_access": paddle_mirror.has_paid_access(user_id)}


@router.post("/portal-session")
async def create_portal_session(user_id: str = Depends(get_verified_user_id)):
    """铸造 Paddle 客户门户会话：改卡、取消、看发票都在 Paddle 托管页完成。

    安全边界：身份只来自 JWT；customer_id 只从服务端镜像反查（get_customer_id_for_user），
    绝不接受客户端传来的 ctre_...，否则任何人拿到别人的 customer id 就能进别人账单页。
    """
    if not paddle_service.api_key():
        raise HTTPException(503, "payment_not_configured")
    customer_id = paddle_mirror.get_customer_id_for_user(user_id)
    if not customer_id:
        # 从未产生过任何 Paddle 交易/订阅 → 没有客户实体，门户无从登录
        raise HTTPException(404, "no_paddle_customer")
    sub_ids = [s["paddle_subscription_id"]
               for s in paddle_mirror.list_user_subscriptions(user_id)
               if s.get("status") in paddle_mirror.GRANTING_STATUSES]
    try:
        session = await paddle_service.create_portal_session(customer_id, sub_ids or None)
    except paddle_service.PaddleError as exc:
        logger.warning("Paddle portal session failed for %s: %s", user_id, type(exc).__name__)
        raise HTTPException(502, str(exc))
    return session


@router.get("/costs")
async def list_costs():
    """信用消耗规则（可配置；credit_cost=0 表示未定价/Coming soon）。"""
    return {"credit_costs": CREDIT_COSTS}


@router.get("/balance")
async def get_balance(user_id: str = Depends(get_verified_user_id)):
    summary = credits_service.get_credit_summary(user_id)
    return summary


@router.get("/purchases")
async def list_pack_purchases(user_id: str = Depends(get_verified_user_id)):
    return {"purchases": credit_pack_service.list_purchases(user_id)}


@router.post("/checkout")
async def create_checkout(req: PackCheckoutRequest, user_id: str = Depends(get_verified_user_id)):
    """为一次性积分包或会员订阅创建 Paddle 交易（本端点不发放任何 Credits）。

    打开 Checkout ≠ 付款成功；Credits / 会员等级只在 /paddle/webhook 验签通过后写入。
    身份与商品语义（kind）由服务端写进 custom_data，客户端无法伪造。
    """
    if bool(req.pack_id) == bool(req.plan_id):
        raise HTTPException(422, "必须且只能指定 pack_id 或 plan_id 之一")

    if req.pack_id:
        item = get_pack(req.pack_id)
        if item is None:
            raise HTTPException(404, "积分包不存在或未开放购买")
        custom_data = {"user_id": user_id, "kind": "credit_pack", "pack_id": item["id"],
                       "credits": str(item["credits"])}
        recurring, price_id = False, item["paddle_price_id"]
    else:
        plan = get_membership_plan(req.plan_id or "")
        if plan is None:
            raise HTTPException(404, "会员计划不存在或未开放订阅")
        custom_data = {"user_id": user_id, "kind": "membership", "plan_id": plan["id"],
                       "credits_per_month": str(plan["credits_per_month"])}
        recurring, price_id = True, plan["paddle_price_id"]

    if not paddle_service.checkout_enabled():
        raise HTTPException(503, "payment_not_configured")
    blocked = paddle_service.checkout_blocked_reason()
    if blocked:
        # 宁可拒绝下单，也不让沙箱凭据碰到 live 环境（或反之）
        logger.error("Paddle checkout blocked: %s", blocked)
        raise HTTPException(503, blocked)
    email = await paddle_service.lookup_user_email(user_id)
    try:
        order = await paddle_service.create_checkout_transaction(
            price_id=price_id, custom_data=custom_data, email=email)
    except paddle_service.PaddleError as exc:
        logger.warning("Paddle checkout failed for %s: %s", user_id, type(exc).__name__)
        raise HTTPException(502, str(exc))
    result = {
        "transaction_id": order["transaction_id"],
        "checkout_url": order.get("checkout_url"),
        "currency": item["currency"] if req.pack_id else plan["currency"],
        "recurring": recurring,
        "price_usd": (item["price_usd"] if req.pack_id else plan["price_usd"]),
    }
    if req.pack_id:
        result.update({"pack_id": item["id"], "credits": item["credits"]})
    else:
        result.update({"plan_id": plan["id"], "interval": plan["interval"],
                       "credits_per_month": plan["credits_per_month"]})
    return result


@router.post("/purchase")
async def purchase(req: PurchaseRequest, user_id: str = Depends(get_verified_user_id)):
    """购买套餐。支付未接入时明确返回 payment_not_configured，绝不直接加 Credits。"""
    pkg = next((p for p in PACKAGES if p["id"] == req.package_id), None)
    if pkg is None:
        raise HTTPException(404, "套餐不存在")
    if not PAYMENT_PROVIDER_CONFIGURED:
        raise HTTPException(402, "payment_not_configured")
    # 未来：创建支付会话 → 回调成功后 credits_service.add_credits(user_id, pkg["credits"], "purchase", ...)
    raise HTTPException(501, "payment_not_configured")


def _extract_any_price_id(obj: dict[str, Any]) -> Optional[str]:
    """transaction 与 subscription 对象上的 Price ID 字段名不同，这里统一取。"""
    price_id = paddle_service.extract_price_id(obj)
    if price_id:
        return price_id
    for key in ("price_id", "recurring_price_id"):
        if obj.get(key):
            return str(obj[key])
    price = obj.get("price")
    if isinstance(price, dict) and price.get("id"):
        return str(price["id"])
    return None


# 表示"这一周期的钱已收到"的事件；其余事件只同步状态，绝不再发一次积分。
# 事件名以 Paddle 官方 SDK 的 EventTypeName 为准（Paddle Billing v2 没有
# subscription.payment_succeeded；周期扣款成功体现为 transaction.paid /
# transaction.completed，试用转正为 subscription.activated）。
PAYING_EVENTS = {
    "transaction.completed",
    "transaction.paid",
    "subscription.created",
    "subscription.activated",
    "subscription.resumed",
    "subscription.imported",
}
# 仅同步状态的事件（不发放、也不回收已到账的积分）
SYNC_ONLY_EVENTS = {
    "transaction.created",
    "transaction.billed",
    "transaction.ready",
    "transaction.updated",
    "transaction.past_due",
    "transaction.canceled",
    "transaction.payment_failed",
    "subscription.updated",
    "subscription.trialing",
    "subscription.past_due",
    "subscription.canceled",
    "subscription.paused",
}
# 客户资料事件：只镜像，永不发放、永不改等级
CUSTOMER_EVENTS = {"customer.created", "customer.updated", "customer.imported"}


def _resolve_event_user(custom: dict[str, Any], obj: dict[str, Any]) -> Optional[str]:
    """事件里可信的用户标识：只认服务端写入的 custom_data.user_id，或已登记过的订阅归属。"""
    user_id = str(custom.get("user_id") or "").strip()
    if user_id:
        return user_id
    sub_id = paddle_service.extract_subscription_id(obj)
    return membership_service.get_user_id_for_subscription(sub_id) if sub_id else None


def _mirror_event(event_type: str, obj: dict[str, Any], price_id: Optional[str],
                  user_id: Optional[str], attributable: bool) -> None:
    """把已验签事件写进客户/订阅镜像。best-effort：镜像失败只记日志，绝不断掉发放。

    只镜像能归因到我们目录或我们用户的事件；后台另建的陌生商品不落库，避免噪声。
    """
    if not attributable:
        return
    try:
        paddle_mirror.mirror_from_event(event_type, obj, user_id=user_id, price_id=price_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Paddle mirror failed for %s event %s: %s", event_type, obj.get("id"), exc)


def _route_membership(event_id: str, event_type: str, obj: dict[str, Any],
                      price_id: Optional[str], custom: dict[str, Any]) -> dict[str, Any]:
    """进会员处理路径，并区别对待"归属冲突"这一种异常。

    - 付款类事件撞上归属冲突 = 有钱进来却要落到别人头上，绝不能静默确认：抛出 → 5xx →
      Paddle 重投，日志留下痕迹，需要人工看；
    - 纯状态同步（updated/canceled/paused）撞上冲突：重投也不可能变好，记 error 后确认掉，
      归属保持不变。
    """
    try:
        return _handle_membership(event_id, event_type, obj, price_id, custom)
    except ValueError:
        if event_type in PAYING_EVENTS:
            raise
        logger.error("Paddle %s targets a subscription owned by another user; state not synced",
                     event_type)
        return {"received": True, "ignored": "owner_conflict"}


def _public_packs() -> list[dict]:
    """对外只暴露展示需要的字段：Price ID 属于服务端目录信息，不下发给浏览器。"""
    return [{k: p[k] for k in ("id", "credits", "price_usd", "price_cents", "currency", "recurring")}
            for p in get_credit_packs()]


def _public_plans() -> list[dict]:
    return [{k: p[k] for k in ("id", "name", "price_usd", "price_cents", "currency",
                              "credits_per_month", "interval", "recurring")}
            for p in get_membership_plans()]


def _verify_paid_amount(*, label: str, obj: dict[str, Any],
                        expected_cents: int, expected_currency: str) -> None:
    """核对 Paddle 实收：只拒绝"低于配置价"与币种不符。

    取高不拒是因为 Paddle 的 grand_total 含税/可能含附加项；取低必须拒——
    那是"用便宜的交易套取高价商品"的唯一现实路径。订阅续费事件里通常没有金额字段，
    取不到金额时不阻断（由 Price ID 与周期锚点保证正确性与幂等）。
    """
    amount_cents, currency = paddle_service.extract_transaction_amount(obj)
    if amount_cents is not None and amount_cents < expected_cents:
        logger.error("Paddle %s paid %s (%s) < configured %s — refusing",
                     label, amount_cents, currency, expected_cents)
        raise HTTPException(400, "amount below configured price")
    if currency and currency != expected_currency:
        logger.error("Paddle %s currency %s != configured %s", label, currency, expected_currency)
        raise HTTPException(400, "currency mismatch")


def _handle_credit_pack(event_id: str, txn: dict[str, Any], custom: dict[str, Any],
                        pack: dict[str, Any], price_id: str) -> dict[str, Any]:
    """一次性积分包：验签通过后按 Price ID 配置的积分数量幂等发放。"""
    if str(custom.get("kind") or "") != "credit_pack":
        logger.warning("Paddle transaction %s maps to a pack but lacks custom_data.kind=credit_pack",
                       txn.get("id"))
        raise HTTPException(400, "unexpected custom_data")

    user_id = str(custom.get("user_id") or "").strip()
    if not user_id:
        logger.warning("Paddle transaction %s has no user_id in custom_data", txn.get("id"))
        raise HTTPException(400, "missing user id")

    txn_id = str(txn.get("id") or "").strip()
    if not txn_id:
        raise HTTPException(400, "missing transaction id")

    _verify_paid_amount(label=f"credit pack {pack['id']} txn {txn_id}", obj=txn,
                        expected_cents=pack["price_cents"], expected_currency=pack["currency"])
    amount_cents, currency = paddle_service.extract_transaction_amount(txn)

    try:
        result = credit_pack_service.grant_pack_credits(
            transaction_id=txn_id,
            user_id=user_id,
            pack=pack,
            price_id=str(price_id),
            event_id=event_id or None,
            currency=currency or pack["currency"],
            amount_cents=amount_cents if amount_cents is not None else pack["price_cents"],
        )
    except RuntimeError as exc:
        # 让 Paddle 重投（占位已释放，重试可再次尝试发放）
        logger.error("Credit pack grant failed for %s: %s", txn_id, exc)
        raise HTTPException(500, "grant failed, please retry delivery")

    return {"received": True, "processed": True, "transaction_id": txn_id,
            "status": result["status"], "granted_credits": result.get("credits", 0)}


def _handle_membership(event_id: str, event_type: str, obj: dict[str, Any],
                       price_id: Optional[str], custom: dict[str, Any]) -> dict[str, Any]:
    """会员订阅：同步等级/周期，并在"本周期已付款"时发放月度积分（每周期一次）。

    绝不发放积分的两种情况：状态非有效（canceled/past_due/paused）、或该周期锚点已发过。
    """
    subscription_id = (str(obj.get("subscription_id") or "") if event_type.startswith("transaction.")
                       else (paddle_service.extract_subscription_id(obj) or ""))
    subscription_id = subscription_id or (str(obj.get("id")) if event_type.startswith("subscription.") else "")
    if not subscription_id:
        raise HTTPException(400, "missing subscription id")

    plan = resolve_plan_by_price_id(price_id)
    user_id = str(custom.get("user_id") or "").strip() or (
        membership_service.get_user_id_for_subscription(subscription_id) or "")
    if plan is None:
        # 后台另建的订阅商品：只记日志，绝不发放、绝不改等级
        logger.info("Paddle subscription %s price %s is not a configured membership plan; ignored",
                    subscription_id, price_id)
        return {"received": True, "ignored": "unconfigured_price"}
    if not user_id:
        logger.warning("Paddle subscription %s cannot be linked to a user", subscription_id)
        raise HTTPException(400, "missing user id")

    # 先验金额再落库：便宜的交易不能把会员等级"买"出来
    if event_type.startswith("transaction."):
        _verify_paid_amount(label=f"membership {plan['id']} subscription {subscription_id}",
                            obj=obj, expected_cents=plan["price_cents"],
                            expected_currency=plan["currency"])

    # 关键区分：transaction.* 上的 status 是"交易状态"（paid/completed/past_due…），
    # subscription.* 上的 status 才是"订阅状态"（active/trialing/paused/canceled…）。
    # 把交易状态当订阅状态会让续费付款被误判成非有效会员而漏发积分。
    raw_status = str(obj.get("status") or "").lower()
    if event_type.startswith("transaction."):
        status = "active" if event_type in PAYING_EVENTS else (raw_status or "active")
    else:
        status = raw_status or ("active" if event_type in PAYING_EVENTS else "unknown")
    period_start, period_end = paddle_service.extract_billing_period(obj)

    membership_service.upsert_subscription(
        subscription_id=subscription_id, user_id=user_id, plan=plan, status=status,
        period_start=period_start, period_end=period_end,
        cancel_at_period_end=bool(obj.get("cancel_at_period_end")),
    )

    # 发放锚点只认"计费周期起点"。刻意不用 transaction id 兜底：
    # 同一周期可能先来 transaction.paid 再来 transaction.completed，用交易号当锚点
    # 会让这两条通知各发一次积分（双倍发放）。取不到周期时宁可跳过并打日志，
    # 由后续 subscription.* 事件（带 current_billing_period_start）补上。
    anchor = period_start
    if event_type not in PAYING_EVENTS or status not in membership_service.ACTIVE_STATUSES:
        return {"received": True, "processed": True, "plan_id": plan["id"], "status": status,
                "granted_credits": 0}
    if not anchor:
        logger.warning("Subscription %s payment event %s carries no billing period; grant skipped",
                       subscription_id, event_type)
        return {"received": True, "processed": True, "plan_id": plan["id"], "status": status,
                "granted_credits": 0, "warn": "no_period_anchor"}

    try:
        result = membership_service.grant_period_credits(subscription_id=subscription_id,
                                                        user_id=user_id, plan=plan, anchor=anchor)
    except RuntimeError as exc:
        logger.error("Membership grant failed for %s/%s: %s", subscription_id, anchor, exc)
        raise HTTPException(500, "grant failed, please retry delivery")

    return {"received": True, "processed": True, "plan_id": plan["id"], "status": status,
            "grant": result["status"], "granted_credits": result.get("credits", 0)}


@router.post("/paddle/webhook")
async def paddle_webhook(request: Request,
                         paddle_signature: Optional[str] = Header(None, alias="Paddle-Signature")):
    """Paddle 回调（积分包 + 会员订阅共用一个入口）。

    安全要点：
      - 未配置 PADDLE_WEBHOOK_SECRET → 503（fail-closed，等于该回调下线）；
      - 签名不符 → 401，且不解析 body、不改任何状态；
      - 发放数量只由 Price ID 在后端配置里查到的数字决定（客户端谎报无效）；
      - 金额/币种与配置不一致 → 400 且不发；
      - 幂等：积分包按 transaction_id 唯一约束，会员按"周期锚点"CAS；
        因此同一事件重投、续费周期、跨周期补发都只生效一次。
    """
    if not paddle_service.webhook_enabled():
        raise HTTPException(503, "paddle_webhook_not_configured")

    raw_body = await request.body()
    if not paddle_service.verify_webhook_signature(raw_body, paddle_signature):
        client = request.client.host if request.client else "unknown"
        logger.warning("Rejected Paddle webhook with invalid signature from %s", client)
        raise HTTPException(401, "invalid signature")

    try:
        payload: dict[str, Any] = json.loads(raw_body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("payload is not an object")
    except (ValueError, UnicodeDecodeError):
        # 坏负载重试也不会变好，直接确认掉，避免 Paddle 无限重投
        logger.warning("Paddle webhook body is not valid JSON; acked and ignored")
        return {"received": True, "processed": False}

    event_id, event_type, obj = paddle_service.parse_event(payload)
    custom = obj.get("custom_data") if isinstance(obj.get("custom_data"), dict) else {}
    kind = str(custom.get("kind") or "")
    price_id = _extract_any_price_id(obj)
    pack = resolve_pack_by_price_id(price_id)
    plan = resolve_plan_by_price_id(price_id)
    event_user = _resolve_event_user(custom, obj)
    # 客户资料事件本身就带 customer_id，没有 user_id 也要镜像（归属之后再从交易回链）
    attributable = (pack is not None or plan is not None
                    or bool(custom.get("user_id")) or event_type in CUSTOMER_EVENTS)

    # 镜像先于发放决策：投影失败只记日志，不影响下面的钱和权益。
    _mirror_event(event_type, obj, price_id, event_user, attributable)

    # 路由主依据 = 后端登记的 Price ID（custom_data 只作辅助与交叉校验）：
    # 续费交易万一不带 custom_data，也能凭订阅归属正确发放。
    if kind == "membership" or plan is not None:
        return _route_membership(event_id, event_type, obj, price_id, custom)

    if event_type in CUSTOMER_EVENTS:
        return {"received": True, "processed": True, "mirrored": True, "event_type": event_type}

    # subscription.* 的状态变化（取消/暂停/降级）也必须落到台账，
    # 否则 /credits/membership 会在订阅已死后继续报"生效中"。
    # 归因不到我们用户的陌生订阅不进这条路径（避免 400 → 无谓重投）。
    if event_type.startswith("subscription.") and plan is not None and event_user:
        return _route_membership(event_id, event_type, obj, price_id, custom)

    if event_type in ("transaction.completed", "transaction.paid"):
        status = str(obj.get("status") or "")
        if event_type == "transaction.completed" and status and status != "completed":
            logger.info("Paddle %s event carries status %s; not granting", event_id, status)
            return {"received": True, "ignored": f"status:{status}"}
        if pack is not None:
            # 一次性积分包严格按 §五：只认 transaction.completed
            if event_type != "transaction.completed":
                return {"received": True, "ignored": event_type}
            return _handle_credit_pack(event_id, obj, custom, pack, str(price_id))
        logger.info("Paddle transaction %s price %s is not a configured product; ignored",
                    obj.get("id"), price_id)
        return {"received": True, "ignored": "unconfigured_price"}

    if event_type in SYNC_ONLY_EVENTS:
        return {"received": True, "ignored": event_type}

    return {"received": True, "ignored": event_type or "unknown"}


@router.post("/bonus/welcome")
async def welcome_bonus(user_id: str = Depends(get_verified_user_id)):
    return credits_service.claim_welcome_bonus(user_id)


@router.post("/bonus/email-verification")
async def email_verification_bonus(user_id: str = Depends(get_verified_user_id)):
    return credits_service.claim_email_verification_bonus(user_id)


@router.post("/bonus/first-song")
async def first_song_bonus(user_id: str = Depends(get_verified_user_id)):
    return credits_service.claim_first_song_bonus(user_id)