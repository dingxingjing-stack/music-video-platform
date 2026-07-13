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

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from enum import Enum

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
async def purchase_subscription(request: PurchaseRequest):
    """购买会员订阅"""
    plan = get_plan_by_id(request.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    
    if plan.price_monthly == 0:
        # 免费版直接激活
        end_date = datetime.now() + timedelta(days=365 * 10)  # 10 年
    elif request.billing_cycle == "yearly":
        end_date = datetime.now() + timedelta(days=365)
    else:
        end_date = datetime.now() + timedelta(days=30)
    
    subscription = {
        "user_id": request.user_id,
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
    
    subscriptions_db[request.user_id] = subscription
    
    # TODO: 实际支付流程
    # 1. 创建支付订单
    # 2. 调起支付 (支付宝/微信/Stripe)
    # 3. 处理支付回调
    # 4. 激活订阅
    
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
async def payment_webhook(
    event_type: str = Query(..., description="事件类型"),
    payment_id: str = Query(..., description="支付订单 ID"),
    user_id: str = Query(..., description="用户 ID"),
    amount: float = Query(..., description="支付金额")
):
    """支付回调 (Mock - 实际需对接支付宝/微信/Stripe)"""
    # TODO: 验证签名
    # TODO: 处理不同事件类型
    # - payment.completed: 支付成功
    # - payment.failed: 支付失败
    # - subscription.renewed: 续费成功
    
    print(f"支付回调：{event_type}, user={user_id}, amount={amount}")
    
    if event_type == "payment.completed":
        if user_id in subscriptions_db:
            subscriptions_db[user_id]["status"] = SubscriptionStatus.ACTIVE
            subscriptions_db[user_id]["trial_days_left"] = None
    
    return {"status": "success", "message": "回调处理完成"}