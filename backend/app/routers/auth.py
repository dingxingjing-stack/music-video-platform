"""
Supabase/SQLite 用户认证路由
功能：登录、注册、用户管理
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict
from datetime import datetime
import os

# 尝试导入 SQLite 服务（优先）或 Supabase 服务
try:
    from app.services.sqlite_service import (
        get_user, create_user, log_activity, increment_user_credits, decrement_user_credits
    )
    DB_BACKEND = "sqlite"
except ImportError:
    from app.services.supabase_service import (
        get_user, create_user, log_activity, 
        SupabaseService as _svc
    )
    increment_user_credits = _svc.increment_user_credits
    decrement_user_credits = _svc.decrement_user_credits
    DB_BACKEND = "supabase"

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
    注册新用户
    
    需要 Supabase Auth 的 Bearer Token
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    # 从 Header 中提取 user_id (实际应从 JWT 解析)
    # 这里简化处理，实际应该用 Supabase Auth 验证 JWT
    supabase_user_id = authorization.replace("Bearer ", "")
    
    # 检查用户是否已存在
    existing_user = get_user(supabase_user_id)
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")
    
    # 创建用户
    try:
        user = create_user(
            email=user_data.email,
            supabase_user_id=supabase_user_id,
            username=user_data.username,
            age=user_data.age
        )
        
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
    
    supabase_user_id = authorization.replace("Bearer ", "")
    
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
    authorization: Optional[str] = Header(None)
):
    """
    增加用户额度（仅管理员或服务）
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required")
    
    try:
        new_credits = increment_user_credits(user_id, amount)
        
        # 记录日志
        log_activity(
            user_id=user_id,
            action="CREDITS_ADDED",
            metadata={"amount": amount, "new_credits": new_credits}
        )
        
        return {
            "success": True,
            "new_credits": new_credits,
            "added": amount
        }
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
    
    supabase_user_id = authorization.replace("Bearer ", "")
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
    
    # 获取任务数量
    tasks_response = supabase.table("tasks")\
        .select("id", count="exact")\
        .eq("user_id", user_id)\
        .execute()
    
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "user_id": user_id,
        "email": user["email"],
        "credits": user["credits"],
        "total_songs": songs_response.count,
        "total_tasks": tasks_response.count,
        "subscription_tier": user["subscription_tier"]
    }