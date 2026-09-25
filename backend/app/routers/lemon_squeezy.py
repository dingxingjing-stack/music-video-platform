"""Lemon Squeezy 路由 —— /api/v1/credits/lemonsqueezy（阶段一：只建单，不发放）。

- GET  /status    公开：LS 链路是否可用 + 已配 Variant 的条目 id（不含任何密钥/凭据）
- POST /checkout  登录：服务端向 LS 建单，只返回 {checkout_url}

与 Paddle 的关系：本文件**不改动** Paddle 的任何行为。两条链路各自独立配置，
前端按 /status 决定某一条目走哪条；LS 未配置时结果与今天完全一致。

安全边界：
1. 客户端只能提交 pack_id 或 plan_id（二选一），模型 extra="forbid" —— 多传任何字段
   （price / credits / variant_id / custom 等）直接 422，不会被后端"顺带采纳"。
2. Variant ID、积分数、金额一律由服务端从配置解析，绝不采信客户端。
3. 本阶段不存在任何发放 Credits 的路径（webhook 尚未实现）。
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from app.services.auth_identity import get_verified_user_id
from app.services.credits_config import CREDIT_PACKS, MEMBERSHIP_PLANS
from app.services import lemon_squeezy_service as ls

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/credits/lemonsqueezy", tags=["credits"])


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
