"""Lemon Squeezy 路由 —— /api/v1/credits/lemonsqueezy。

- GET  /status    公开：LS 链路是否可用 + 已配 Variant 的条目 id（不含任何密钥/凭据）
- POST /checkout  登录：服务端向 LS 建单，只返回 {checkout_url}
- POST /webhook   LS 回调：验签 → 解析 → 投递台账 → **一次性 Credit Pack 履约**

路径前缀沿用既有 router 的 /api/v1/credits/lemonsqueezy，与 Paddle 的
/api/v1/credits/paddle/webhook 同构；不新建第二个 router，也不改已发布给
前端的 /status 与 /checkout 地址。

与 Paddle 的关系：本文件**不改动** Paddle 的任何行为。两条链路各自独立配置，
前端按 /status 决定某一条目走哪条；LS 未配置时结果与今天完全一致。

安全边界：
1. 客户端只能提交 pack_id 或 plan_id（二选一），模型 extra="forbid" —— 多传任何字段
   （price / credits / variant_id / custom 等）直接 422，不会被后端"顺带采纳"。
2. Variant ID、积分数、金额一律由服务端从配置解析，绝不采信客户端。
3. webhook 只认 LS 自己的 X-Signature（原始 body 的 HMAC-SHA256 hexdigest，
   无 timestamp / 无 nonce / 无容差），与 Paddle 的 ts:h1 完全不通用。
4. 本文件只做编排：验签、落投递台账、把事件交给 service 履约。
   这里不出现任何余额操作，也不写 subscription / invoice / membership 相关记录
   —— 那些属于 P2-5 之后的阶段，本阶段一律 ignored。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import IntegrityError

from app.db import database as db
from app.db.database import LemonSqueezyWebhookDelivery
from app.services.auth_identity import get_verified_user_id
from app.services.credits_config import CREDIT_PACKS, MEMBERSHIP_PLANS
from app.services import lemon_squeezy_service as ls

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/credits/lemonsqueezy", tags=["credits"])

# 投递台账里原始 payload 的体积上限。LS 实测单条 2.3–3.5 KB，给到 20 KB 足够，
# 同时挡掉"合法签名 + 超大 body"把台账撑爆。
_DELIVERY_PAYLOAD_MAX_CHARS = 20_000

# 台账 outcome 只在本阶段用于日志与响应，不落库（表里没有该列，P2-2 已定形）。
_RECORDED = "recorded"
_DUPLICATE = "duplicate"
_LEDGER_FAILED = "ledger_failed"


class LemonSqueezyCheckoutRequest(BaseModel):
    """只允许指定"买哪个条目"。任何其它字段（含价格/积分/Variant ID）一律拒收。"""
    model_config = ConfigDict(extra="forbid")

    pack_id: Optional[str] = None
    plan_id: Optional[str] = None


@router.get("/status")
async def lemonsqueezy_status():
    """供前端判断走哪条链路。只暴露布尔与条目 id，不回显任何凭据或 Variant ID。"""
    return {
        "enabled": ls.checkout_enabled(),
        # 单独暴露：enabled=false 时用它区分"凭据没配"还是"只差 webhook secret"。
        "webhook_configured": ls.webhook_enabled(),
        "items": ls.configured_items(),
    }


@router.post("/checkout")
async def create_lemonsqueezy_checkout(req: LemonSqueezyCheckoutRequest,
                                       user_id: str = Depends(get_verified_user_id)):
    """为积分包或会员订阅创建 Lemon Squeezy Checkout（本端点不发放任何 Credits）。"""
    if bool(req.pack_id) == bool(req.plan_id):
        raise HTTPException(422, "必须且只能指定 pack_id 或 plan_id 之一")

    if req.pack_id:
        item = next((p for p in CREDIT_PACKS if p["id"] == req.pack_id), None)
        if item is None:
            raise HTTPException(404, "积分包不存在或未开放购买")
        item_id = item["id"]
        custom = {"user_id": user_id, "kind": "credit_pack",
                  "pack_id": item_id, "credits": str(item["credits"])}
    else:
        plan = next((p for p in MEMBERSHIP_PLANS if p["id"] == req.plan_id), None)
        if plan is None:
            raise HTTPException(404, "会员计划不存在或未开放订阅")
        item_id = plan["id"]
        custom = {"user_id": user_id, "kind": "membership",
                  "plan_id": item_id, "credits_per_month": str(plan["credits_per_month"])}

    if not ls.checkout_enabled():
        # 区分两种"没配好"：凭据不全 vs 只差 Webhook secret。后者单独给码，
        # 因为它是"能收钱但发不了货"的状态，运维看到要立刻补 secret 而不是去查 API key。
        if not ls.webhook_enabled():
            logger.error("Lemon Squeezy checkout blocked: LEMONSQUEEZY_WEBHOOK_SECRET 未配置，"
                         "付款后无法回调发货，已拒绝建单")
            raise HTTPException(503, "lemonsqueezy_webhook_not_configured")
        raise HTTPException(503, "lemonsqueezy_not_configured")
    variant_id = ls.variant_id_for(item_id)
    if not variant_id:
        # 商店/密钥配了但这一档没配 Variant：宁可 503 也不让前端拿到一个错商品的链接
        raise HTTPException(503, "lemonsqueezy_variant_not_configured")

    redirect_url = (os.environ.get("LEMONSQUEEZY_REDIRECT_URL") or "").strip() or None
    try:
        order = await ls.create_checkout(variant_id=variant_id, custom=custom,
                                         redirect_url=redirect_url)
    except ls.LemonSqueezyError as exc:
        logger.warning("Lemon Squeezy checkout failed for %s: code=%s status=%s",
                       user_id, exc.code or "-", exc.status or "-")
        raise HTTPException(502, exc.code or "lemonsqueezy_checkout_failed")

    return {"checkout_url": order["checkout_url"]}


# ── Webhook（P2-3：验签 + 解析 + 投递台账，零发放）────────────────────────
def _record_delivery(event: ls.LsEvent, raw_body: bytes) -> str:
    """把一次投递写进 lemonsqueezy_webhook_deliveries。

    幂等**只依赖数据库 UNIQUE(ls_event_id)**：直接 INSERT，撞约束就判定为重复投递。
    刻意不写"先 SELECT 再 INSERT"—— 两条并发重投会双双通过应用层检查，然后各自
    发放一次权益（P2-4/P2-6 就建立在这个底线之上）。

    返回 _RECORDED / _DUPLICATE / _LEDGER_FAILED。
    """
    payload_text = raw_body.decode("utf-8", errors="replace")[:_DELIVERY_PAYLOAD_MAX_CHARS]
    sess = None
    try:
        sess = db.SessionLocal()
        sess.add(LemonSqueezyWebhookDelivery(
            ls_event_id=event.delivery_id,
            event_name=event.event_name,
            object_type=event.object_type,
            object_id=event.object_id or None,
            test_mode=event.test_mode,
            payload=payload_text,
        ))
        sess.commit()
        return _RECORDED
    except IntegrityError:
        sess.rollback()
        return _DUPLICATE
    except Exception as exc:  # noqa: BLE001 - 台账写不进去时不能假装处理成功
        if sess is not None:
            sess.rollback()
        logger.error("Lemon Squeezy delivery ledger failed: %s", type(exc).__name__)
        return _LEDGER_FAILED
    finally:
        if sess is not None:
            sess.close()


@router.post("/webhook")
async def lemonsqueezy_webhook(request: Request,
                               x_signature: Optional[str] = Header(None, alias="X-Signature")):
    """Lemon Squeezy 回调入口。

    链路：原始 body → X-Signature 验签 → 解析 → 投递台账（UNIQUE 幂等）→ 履约编排。
    本阶段只有"一次性 Credit Pack"会真正履约；subscription / invoice / refund 一律
    只落投递台账，不产生任何业务记录。

    状态码语义（LS 非 200 会按 5/25/125 s 重投 3 次）：
      503 未配 LEMONSQUEEZY_WEBHOOK_SECRET —— 等于本回调下线（fail-closed）；
      401 验签失败 —— 不解析 body、不落库、不改任何状态，响应不含期望值/密钥/长度；
      400 签名正确但 body 不是合法 JSON，或缺 meta.webhook_id / event_name / data.type；
          以及金额、币种、数量、身份、档位与服务端配置不符（拒绝履约并要求上游重投，
          绝不静默吞掉一笔已付款的订单）；
      500 台账或发放本身失败 —— claim 已释放，重投可以补发；
      200 已处理 / 结构性忽略（不是我们的商品、状态未到已付、生产收到 test 事件）。

    重复投递：仍然会再走一次履约编排，但发放侧由 ls_order_id 的数据库 UNIQUE 兜底，
    结果恒为 already_processed。之所以不在这里对 duplicate 提前 return，是因为
    "首次投递已记账、发放却失败"的那种重试必须还能救回来。

    刻意不做的事：没有时间戳、没有 nonce、没有容差、不重排 JSON 再验签、
    不复用 Paddle 的验签器，也不在本阶段读取 subscription/invoice 做任何发放判断。
    """
    if not ls.webhook_secret():
        raise HTTPException(503, "lemonsqueezy_webhook_not_configured")

    raw_body = await request.body()          # 必须是原始字节：绝不用 request.json()
    if not ls.verify_webhook_signature(raw_body, x_signature):
        client = request.client.host if request.client else "unknown"
        logger.warning("Rejected Lemon Squeezy webhook with invalid signature from %s", client)
        raise HTTPException(401, "invalid signature")

    try:
        payload: Any = json.loads(raw_body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("payload is not a JSON object")
    except (ValueError, UnicodeDecodeError):
        # 只记来源，不回显 body：body 里可能有买家邮箱与姓名。
        logger.warning("Lemon Squeezy webhook body is not a valid JSON object; rejected")
        raise HTTPException(400, "invalid webhook payload")

    event = ls.parse_webhook_event(payload)
    if not event.delivery_id or not event.event_name or not event.object_type:
        logger.warning("Lemon Squeezy webhook missing meta.webhook_id / event_name / data.type "
                       "(event=%s); rejected", event.event_name or "-")
        raise HTTPException(400, "malformed webhook event")

    outcome = _record_delivery(event, raw_body)
    if outcome == _LEDGER_FAILED:
        # 台账写不进去 ⇒ 让 LS 重投，绝不静默吞掉一次投递。
        raise HTTPException(500, "delivery ledger unavailable")
    duplicate_delivery = outcome == _DUPLICATE

    result = ls.fulfill_credit_pack_order(event)
    if result.status == ls.REJECTED:
        logger.warning("Lemon Squeezy %s delivery %s rejected for fulfilment: code=%s",
                       event.event_name, event.order_id or event.object_id, result.code)
        raise HTTPException(400, result.code)
    if result.status == ls.ERROR:
        raise HTTPException(500, result.code)

    return {"received": True, "duplicate": duplicate_delivery}
