"""
公测灰度权限路由
- 所有端点通过 Authorization Bearer JWT（verified auth.users.id）识别用户
"""

from __future__ import annotations

import hmac
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Depends
from pydantic import BaseModel, Field

from app.services.beta_service import (
    check_gray_status,
    consume_credit,
    apply_gray,
    get_feature_access,
    daily_reset,
)
from app.services.auth_identity import get_verified_user_id

router = APIRouter(prefix="/api/v1/beta", tags=["beta"])


class ApplyGrayRequest(BaseModel):
    feature_key: str = ""
    reason: str
    contact: str = ""


class ConsumeRequest(BaseModel):
    # 严格正整数，拒绝负数 / 0；上限 10 与单次消费粒度匹配
    amount: int = Field(default=1, gt=0, le=10)


@router.get("/status")
async def get_status(user_id: str = Depends(get_verified_user_id)):
    """获取当前用户灰度状态"""
    return await check_gray_status(user_id)


@router.post("/apply-gray")
async def apply_gray_route(req: ApplyGrayRequest, user_id: str = Depends(get_verified_user_id)):
    """申请灰度权限"""
    if not req.reason.strip():
        raise HTTPException(status_code=400, detail="请填写申请理由")
    return await apply_gray(user_id, req.reason, req.contact, req.feature_key)


@router.post("/consume-credit")
async def consume_credit_route(req: ConsumeRequest, user_id: str = Depends(get_verified_user_id)):
    """消费每日免费额度（身份来自 verified JWT，缺 JWT 自动 401）"""
    return await consume_credit(user_id, req.amount)


@router.get("/feature-access")
async def feature_access_route(user_id: str = Depends(get_verified_user_id)):
    """获取所有功能权限列表"""
    return await get_feature_access(user_id)


@router.post("/daily-reset")
async def daily_reset_route(
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
):
    """每日额度重置（运维/定时任务专用，不对外公开）。

    与 /api/v1/auth/credits/add 的 P0-1 收口保持同一口径：ADMIN_API_TOKEN 未配置时
    一律 503（fail-closed），提供时用常量时间比对；不接受普通用户 JWT 作为授权凭据。
    """
    admin_token = (os.getenv("ADMIN_API_TOKEN") or "").strip()
    if not admin_token:
        raise HTTPException(status_code=503, detail="admin_not_configured")
    if not x_admin_token or not hmac.compare_digest(str(x_admin_token), admin_token):
        raise HTTPException(status_code=403, detail="admin token required")

    return await daily_reset()
