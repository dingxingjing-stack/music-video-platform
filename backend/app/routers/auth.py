"""
Supabase/SQLite 用户认证路由
功能：登录、注册、用户管理
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict
from datetime import datetime
import os

from app.services.auth_identity import resolve_auth_user_id

# 生产/已配置 Supabase 时优先 Supabase，否则回退 SQLite（本地/测试）
_SUPABASE_CFG = bool(os.getenv("SUPABASE_URL") and (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")))
try:
    if _SUPABASE_CFG:
        from app.services.supabase_service import (
            get_user, create_user, ensure_user, log_activity,
            increment_user_credits, decrement_user_credits,
        )
        DB_BACKEND = "supabase"
    else:
        from app.services.sqlite_service import (
            get_user, create_user, ensure_user, log_activity, increment_user_credits, decrement_user_credits
        )
        DB_BACKEND = "sqlite"
except ImportError:
    from app.services.sqlite_service import (
        get_user, create_user, ensure_user, log_activity, increment_user_credits, decrement_user_credits
    )
    DB_BACKEND = "sqlite"

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])


class UserCreate(BaseModel):
    email: EmailStr
    username: Optional[str] = None
    age: Optional[int] = None


class UserResponse(BaseModel):
    id: str
    email: str
    username: Optional[str] = None
    credits: int = 100
    avatar_url: Optional[str] = None
    subscription_tier: str = 'free'
    created_at: str


@router.post("/register", response_model=UserResponse)
async def register_user(user_data: UserCreate, authorization: Optional[str] = Header(None)):
    """
    注册新用户（Phase 3-2A：幂等 ensure_user）
    
    需要 Supabase Auth 的 Bearer Token。幂等：同一 auth UUID 重复调用不产生第二个用户。
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    # 正确验证 Bearer JWT（Supabase Auth），取 auth user id（UUID）；
    # 禁止把整段 JWT 当作 user_id。验证失败 → 401。
    supabase_user_id = resolve_auth_user_id(authorization)
    if not supabase_user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # 幂等确保 public.users 存在（已存在返回既有，不报 400）
    try:
        user = ensure_user(supabase_user_id, user_data.email)

        # 注册赠送 50 Credits（幂等，重复 register 不会重复发放）
        try:
            import threading
            credits_service = __import__("app.services.credits_service", fromlist=["claim_welcome_bonus"])
            credits_service.claim_welcome_bonus(supabase_user_id)
        except Exception:
            # 发放失败不阻断注册（避免 credits 表未就绪时注册失败）
            pass

        # 记录活动日志
        log_activity(
            user_id=user["id"],
            action="USER_REGISTERED",
            metadata={"email": user_data.email}
        )

        return UserResponse(**user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


@router.get("/me", response_model=UserResponse)
async def get_current_user(authorization: Optional[str] = Header(None)):
    """
    获取当前用户信息
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    supabase_user_id = resolve_auth_user_id(authorization)
    if not supabase_user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = get_user(supabase_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(**user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user_by_id(user_id: str):
    """
    根据 ID 获取用户信息
    """
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserResponse(**user)


@router.post("/credits/add")
async def add_user_credits(
    user_id: str,
    amount: int,
    authorization: Optional[str] = Header(None),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
):
    """管理员专用：为指定用户增加额度（旧 users.credits 账本）。

    P0-1 安全收口（原实现只判断「Authorization 头非空」，任何人不验证 JWT 就能给任意
    用户任意加额度）：
      - 必须提供 X-Admin-Token，且与环境变量 ADMIN_API_TOKEN 常量时间相等；
      - ADMIN_API_TOKEN 未配置时该端点一律 503（默认关闭，fail-closed）；
      - 不接受普通用户 JWT 作为授权凭据；客户端传入的 user_id/amount 仍需边界校验。
    """
    import hmac
    import os

    admin_token = (os.getenv("ADMIN_API_TOKEN") or "").strip()
    if not admin_token:
        raise HTTPException(status_code=503, detail="admin_not_configured")
    if not x_admin_token or not hmac.compare_digest(str(x_admin_token), admin_token):
        raise HTTPException(status_code=403, detail="admin token required")

    if not user_id or not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id required")
    if amount <= 0 or amount > 100_000:
        raise HTTPException(status_code=400, detail="amount 必须在 1..100000 之间")

    try:
        new_credits = increment_user_credits(user_id.strip(), amount)
        
        # 记录日志
        log_activity(
            user_id=user_id.strip(),
            action="CREDITS_ADDED",
            metadata={"amount": amount, "new_credits": new_credits}
        )
        
        return {
            "success": True,
            "new_credits": new_credits,
            "added": amount
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/credits/consume")
async def consume_user_credits(
    amount: int,
    authorization: Optional[str] = Header(None)
):
    """
    消耗用户额度
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required")

    supabase_user_id = resolve_auth_user_id(authorization)
    if not supabase_user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = get_user(supabase_user_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    success = decrement_user_credits(user["id"], amount)
    
    if not success:
        raise HTTPException(
            status_code=402,
            detail="Insufficient credits. Please upgrade your plan."
        )
    
    # 记录日志
    log_activity(
        user_id=user["id"],
        action="CREDITS_CONSUMED",
        metadata={"amount": amount, "remaining": user["credits"] - amount}
    )
    
    return {
        "success": True,
        "consumed": amount,
        "remaining": user["credits"] - amount
    }


@router.get("/{user_id}/stats")
async def get_user_stats(user_id: str):
    """
    获取用户统计信息
    """
    from app.services.supabase_service import supabase
    
    # 获取歌曲数量
    songs_response = supabase.table("songs")\
        .select("id", count="exact")\
        .eq("user_id", user_id)\
        .execute()
    
    # 获取任务数量 —— ai_tasks 统一走 SQLAlchemy（task_store），不再经 Supabase/PostgREST
    # （生产 service_role → ai_tasks 会 403；见 Phase 2B 审计）
    from app.services import task_store
    total_tasks = task_store.count_user_tasks(user_id)
    
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "user_id": user_id,
        "email": user["email"],
        "credits": user["credits"],
        "total_songs": songs_response.count,
        "total_tasks": total_tasks,
        "subscription_tier": user["subscription_tier"]
    }
