"""
会员订阅系统路由 (Subscription Router)

功能:
- 会员等级管理 (免费/高级/VIP)
- 订阅购买/续费/取消
- 权益验证
- 使用配额管理

API 端点:
- GET /api/v1/subscription/plans - 获取会员计划列表
- POST /api/v1/subscription/purchase - 购买会员
- GET /api/v1/subscription/status - 查询会员状态
- PUT /api/v1/subscription/cancel - 取消订阅
- PUT /api/v1/subscription/renew - 续费
- GET /api/v1/subscription/usage - 查询使用配额
- POST /api/v1/subscription/webhook - 支付回调 (Mock)
"""

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, List, Dict

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.services.auth_identity import resolve_auth_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/subscription", tags=["Subscription"])


class PlanTier(str, Enum):
    FREE = "free"
    PREMIUM = "premium"
    VIP = "vip"


class PlanDetail(BaseModel):
    id: str
    name: str
    tier: PlanTier
    price_monthly: float
    price_yearly: float
    features: List[str]
    limits: Dict[str, int]  # 各项功能的使用限额
    popular: bool = False


# 会员计划定义
PLANS = [
    PlanDetail(
        id="plan_free",
        name="免费版",
        tier=PlanTier.FREE,
        price_monthly=0,
        price_yearly=0,
        features=[
            "基础音乐生成 (5 首/月)",
            "基础 MV 模板",
            "720P 视频导出",
            "社区功能"
        ],
        limits={
            "music_generation": 5,
            "mv_templates": 10,
            "video_export_resolution": 720,
            "storage_gb": 1,
            "ai_features": 3
        }
    ),
    PlanDetail(
        id="plan_premium",
        name="高级版",
        tier=PlanTier.PREMIUM,
        price_monthly=29.9,
        price_yearly=299,
        features=[
            "无限音乐生成",
            "全部 MV 模板 (500+)",
            "1080P 视频导出",
            "高级效果器",
            "优先渲染",
            "无广告"
        ],
        limits={
            "music_generation": -1,  # -1 = 无限
            "mv_templates": 500,
            "video_export_resolution": 1080,
            "storage_gb": 50,
            "ai_features": -1
        },
        popular=True
    ),
    PlanDetail(
        id="plan_vip",
        name="VIP 专业版",
        tier=PlanTier.VIP,
        price_monthly=99.9,
        price_yearly=999,
        features=[
            "高级版全部功能",
            "4K 视频导出",
            "专属客服",
            "API 访问",
            "商业授权",
            "团队协作 (5 人)",
            "数据分析"
        ],
        limits={
            "music_generation": -1,
            "mv_templates": -1,
            "video_export_resolution": 2160,  # 4K
            "storage_gb": 500,
            "ai_features": -1,
            "team_members": 5,
            "api_calls_monthly": 10000
        }
    )
]


# 内存存储用户订阅状态
subscriptions_db: Dict[str, dict] = {}


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    TRIAL = "trial"


class SubscriptionResponse(BaseModel):
    user_id: str
    plan_id: str
    tier: PlanTier
    status: SubscriptionStatus
    start_date: datetime
    end_date: datetime
    auto_renew: bool
    trial_days_left: Optional[int] = None


class PurchaseRequest(BaseModel):
    user_id: str = Field(..., description="用户 ID")
    plan_id: str = Field(..., description="计划 ID")
    billing_cycle: str = Field("monthly", description="计费周期：monthly/yearly")
    payment_method: str = Field("alipay", description="支付方式：alipay/wechat/card")


def get_plan_by_id(plan_id: str) -> Optional[PlanDetail]:
    for plan in PLANS:
        if plan.id == plan_id:
            return plan
    return None


@router.get("/plans")
async def get_plans(tier_filter: Optional[PlanTier] = None):
    """获取会员计划列表"""
    if tier_filter:
        return [p for p in PLANS if p.tier == tier_filter]
    return PLANS


@router.post("/purchase", response_model=SubscriptionResponse)
async def purchase_subscription(
    request: PurchaseRequest,
    authorization: Optional[str] = Header(None),
):
    """购买会员订阅（P0 安全收口）。

    原实现的两处致命问题：
      1. **完全无鉴权**，且 `user_id` 取自请求体 —— 任何人可给任意 user_id 开通会员；
      2. **没有任何真实收款**（下方原本是 `TODO: 实际支付流程`），付费套餐也会被
         直接写入为 TRIAL/ACTIVE —— 等于一台「自助发 VIP」机器。
         （真实支付走 Paddle 结账 + 本文件 /webhook 回调。）

    收口规则：
      - 必须携带有效 Authorization（401 否则）；
      - user_id 一律以 token 解析结果为准，body 传入不一致直接 403；
      - 付费套餐（price_monthly > 0）本接口不开通，返回 402 引导走 Paddle 结账；
        仅免费套餐可在此直接激活（本就无需付款）。
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    caller_id = resolve_auth_user_id(authorization)
    if not caller_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # user_id 以 token 为准，禁止 body 覆盖
    if request.user_id and request.user_id.strip() and request.user_id.strip() != caller_id:
        raise HTTPException(status_code=403, detail="user_id does not match authenticated user")

    plan = get_plan_by_id(request.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")

    # 付费套餐：本接口无收款能力，不得在此开通，否则等于白送会员
    if plan.price_monthly > 0:
        raise HTTPException(
            status_code=402,
            detail="paid plan requires checkout: use Paddle checkout (/api/v1/credits/packs), not this endpoint",
        )

    if plan.price_monthly == 0:
        # 免费版直接激活
        end_date = datetime.now() + timedelta(days=365 * 10)  # 10 年
    elif request.billing_cycle == "yearly":
        end_date = datetime.now() + timedelta(days=365)
    else:
        end_date = datetime.now() + timedelta(days=30)
    
    # user_id 一律写 token 解析出的身份，绝不写 body 传入值
    subscription = {
        "user_id": caller_id,
        "plan_id": request.plan_id,
        "tier": plan.tier,
        "status": SubscriptionStatus.ACTIVE if plan.price_monthly == 0 else SubscriptionStatus.TRIAL,
        "start_date": datetime.now(),
        "end_date": end_date,
        "auto_renew": True,
        "billing_cycle": request.billing_cycle,
        "payment_method": request.payment_method,
        "trial_days_left": 7 if plan.price_monthly > 0 else None
    }
    
    subscriptions_db[caller_id] = subscription

    # 注意：付费套餐已在上方 402 拦截，不会走到这里 —— 本接口无收款能力，
    # 真实支付由 Paddle 结账 + /webhook 回调完成（见文件末尾 webhook 与
    # paddle_service）。此处仅保留免费套餐激活路径。
    
    return SubscriptionResponse(**subscription)


@router.get("/status", response_model=Optional[SubscriptionResponse])
async def get_subscription_status(user_id: str = Query(..., description="用户 ID")):
    """查询用户会员状态"""
    if user_id not in subscriptions_db:
        # 默认为免费版
        return SubscriptionResponse(
            user_id=user_id,
            plan_id="plan_free",
            tier=PlanTier.FREE,
            status=SubscriptionStatus.ACTIVE,
            start_date=datetime.now(),
            end_date=datetime.now() + timedelta(days=3650),
            auto_renew=False
        )
    
    sub = subscriptions_db[user_id]
    
    # 检查是否过期
    if sub["end_date"] < datetime.now() and sub["status"] != SubscriptionStatus.CANCELLED:
        sub["status"] = SubscriptionStatus.EXPIRED
    
    return SubscriptionResponse(**sub)


@router.put("/cancel")
async def cancel_subscription(
    user_id: str = Query(..., description="用户 ID"),
    immediate: bool = Query(False, description="是否立即取消")
):
    """取消订阅"""
    if user_id not in subscriptions_db:
        raise HTTPException(status_code=404, detail="未找到订阅")
    
    sub = subscriptions_db[user_id]
    
    if immediate:
        sub["status"] = SubscriptionStatus.CANCELLED
        sub["end_date"] = datetime.now()
    else:
        # 到期后取消自动续费
        sub["auto_renew"] = False
    
    return {"message": "取消成功", "end_date": sub["end_date"]}


@router.put("/renew", response_model=SubscriptionResponse)
async def renew_subscription(
    user_id: str = Query(..., description="用户 ID"),
    plan_id: Optional[str] = Query(None, description="新计划 ID (升级/降级)")
):
    """续费订阅"""
    if user_id not in subscriptions_db:
        raise HTTPException(status_code=404, detail="未找到订阅")
    
    sub = subscriptions_db[user_id]
    
    if plan_id:
        new_plan = get_plan_by_id(plan_id)
        if not new_plan:
            raise HTTPException(status_code=404, detail="计划不存在")
        sub["plan_id"] = plan_id
        sub["tier"] = new_plan.tier
    
    # 延长有效期
    if sub["billing_cycle"] == "yearly":
        sub["end_date"] += timedelta(days=365)
    else:
        sub["end_date"] += timedelta(days=30)
    
    sub["status"] = SubscriptionStatus.ACTIVE
    
    return SubscriptionResponse(**sub)


@router.get("/usage")
async def get_usage_quota(user_id: str = Query(..., description="用户 ID")):
    """查询用户使用配额"""
    # 获取会员状态
    if user_id not in subscriptions_db:
        tier = PlanTier.FREE
    else:
        sub = subscriptions_db[user_id]
        if sub["status"] == SubscriptionStatus.EXPIRED:
            tier = PlanTier.FREE
        else:
            tier = sub["tier"]
    
    # 获取计划限额
    plan = get_plan_by_id(f"plan_{tier.value}")
    if not plan:
        raise HTTPException(status_code=500, detail="计划配置错误")
    
    # TODO: 从数据库查询实际使用量
    mock_usage = {
        "music_generation": 2,  # 已使用 2 首
        "mv_templates": 5,
        "storage_used_gb": 0.5,
        "ai_features": 1
    }
    
    # 计算剩余额度
    quota = {}
    for key, limit in plan.limits.items():
        if limit == -1:
            quota[key] = {"used": mock_usage.get(key, 0), "limit": -1, "remaining": -1}
        else:
            used = mock_usage.get(key, 0)
            quota[key] = {
                "used": used,
                "limit": limit,
                "remaining": max(0, limit - used)
            }
    
    return {
        "user_id": user_id,
        "tier": tier.value,
        "quota": quota,
        "reset_date": datetime.now() + timedelta(days=30)
    }


@router.post("/webhook")
async def payment_webhook(request: Request):
    """支付回调 —— 必须通过 HMAC-SHA256 验签，否则不得改变任何订阅状态。

    P0-5 安全收口（原实现无鉴权、无验签，任何人用 query 传 user_id +
    event_type=payment.completed 就能把用户置为 ACTIVE）：
      - 服务端未配置 SUBSCRIPTION_WEBHOOK_SECRET → 503（该 webhook 等于安全下线，
        因为当前支付系统尚未正式接入，绝不允许保留可伪造入口）；
      - 必须带 X-Webhook-Signature: sha256=<hex>，值为
        HMAC_SHA256(secret, raw_query + "\\n" + raw_body)，用 hmac.compare_digest 比较；
      - 缺失/不匹配 → 403，且不修改任何状态。
    """
    import hashlib
    import hmac
    import os

    secret = (os.getenv("SUBSCRIPTION_WEBHOOK_SECRET") or "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="webhook_not_configured")

    raw_body = await request.body()
    signed_payload = f"{request.url.query}\n".encode("utf-8") + raw_body
    provided = (request.headers.get("X-Webhook-Signature") or "").strip()
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    if not provided or not hmac.compare_digest(provided, expected):
        logger.warning("Rejected subscription webhook with invalid signature from %s",
                       request.client.host if request.client else "unknown")
        raise HTTPException(status_code=403, detail="invalid webhook signature")

    event_type = request.query_params.get("event_type", "")
    payment_id = request.query_params.get("payment_id", "")
    user_id = request.query_params.get("user_id", "")
    amount = request.query_params.get("amount", "")

    print(f"支付回调（已验签）：{event_type}, user={user_id}, amount={amount}, payment={payment_id}")

    if event_type == "payment.completed":
        if user_id in subscriptions_db:
            subscriptions_db[user_id]["status"] = SubscriptionStatus.ACTIVE
            subscriptions_db[user_id]["trial_days_left"] = None

    return {"status": "success", "message": "回调处理完成"}