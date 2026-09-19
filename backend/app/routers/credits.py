"""Credits 路由 —— /api/v1/credits

- GET  /packages       公开：套餐列表（无需登录）
- GET  /costs          公开：信用消耗规则（可配置占位）
- GET  /balance        登录：当前余额 + 奖励领取状态
- POST /purchase       登录：购买（当前支付未接入 → payment_not_configured，绝不直接加 Credits）
- POST /bonus/welcome | /bonus/email-verification | /bonus/first-song（内部/幂等领取）

身份：凡涉及用户余额/状态的端点，唯一可信来源 = verified JWT（get_verified_user_id）。
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.auth_identity import get_verified_user_id
from app.services.credits_config import PACKAGES, CREDIT_COSTS, FREE_TOTAL
from app.services import credits_service

router = APIRouter(prefix="/api/v1/credits", tags=["credits"])

# 支付 Provider 是否已接入；当前未接入。
PAYMENT_PROVIDER_CONFIGURED = os.getenv("PAYMENT_PROVIDER", "").strip().lower() in ("stripe", "lemon_squeezy", "paddle")


class PurchaseRequest(BaseModel):
    package_id: str
    # 预留：payment_method / idempotency_key 供未来支付接入
    payment_method: str = "card"
    idempotency_key: str | None = None


@router.get("/packages")
async def list_packages():
    """套餐列表（公开，仅供展示；价格以本后端为准）。"""
    return {"free_total": FREE_TOTAL, "packages": PACKAGES}


@router.get("/costs")
async def list_costs():
    """信用消耗规则（可配置；credit_cost=0 表示未定价/Coming soon）。"""
    return {"credit_costs": CREDIT_COSTS}


@router.get("/balance")
async def get_balance(user_id: str = Depends(get_verified_user_id)):
    summary = credits_service.get_credit_summary(user_id)
    return summary


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


@router.post("/bonus/welcome")
async def welcome_bonus(user_id: str = Depends(get_verified_user_id)):
    return credits_service.claim_welcome_bonus(user_id)


@router.post("/bonus/email-verification")
async def email_verification_bonus(user_id: str = Depends(get_verified_user_id)):
    return credits_service.claim_email_verification_bonus(user_id)


@router.post("/bonus/first-song")
async def first_song_bonus(user_id: str = Depends(get_verified_user_id)):
    return credits_service.claim_first_song_bonus(user_id)