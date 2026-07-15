"""
公测灰度权限路由
- 所有端点通过 X-User-ID 请求头识别用户（公测免鉴权方案）
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.services.beta_service import (
    check_gray_status,
    consume_credit,
    apply_gray,
    get_feature_access,
    daily_reset,
)

router = APIRouter(prefix="/api/v1/beta", tags=["beta"])


class ApplyGrayRequest(BaseModel):
    feature_key: str = ""
    reason: str
    contact: str = ""


class ConsumeRequest(BaseModel):
    amount: int = 1


@router.get("/status")
async def get_status(x_user_id: str = Header("beta_user", alias="X-User-ID")):
    """获取当前用户灰度状态"""
    return await check_gray_status(x_user_id)


@router.post("/apply-gray")
async def apply_gray_route(req: ApplyGrayRequest, x_user_id: str = Header("beta_user", alias="X-User-ID")):
    """申请灰度权限"""
    if not req.reason.strip():
        raise HTTPException(status_code=400, detail="请填写申请理由")
    return await apply_gray(x_user_id, req.reason, req.contact, req.feature_key)


@router.post("/consume-credit")
async def consume_credit_route(req: ConsumeRequest, x_user_id: str = Header("beta_user", alias="X-User-ID")):
    """消费每日免费额度"""
    return await consume_credit(x_user_id, req.amount)


@router.get("/feature-access")
async def feature_access_route(x_user_id: str = Header("beta_user", alias="X-User-ID")):
    """获取所有功能权限列表"""
    return await get_feature_access(x_user_id)


@router.post("/daily-reset")
async def daily_reset_route():
    """每日额度重置（供 cron 调用，不对外公开）"""
    return await daily_reset()
