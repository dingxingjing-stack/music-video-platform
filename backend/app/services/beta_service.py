"""
公测灰度权限服务
- 基于 Supabase，免付费依赖
- 管理用户额度、灰度申请、自动升级
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
}

# 公测额度配置
DAILY_LIMIT_NORMAL = 10   # 普通用户每日免费生成额度
DAILY_LIMIT_GRAY = 30     # 资深测试用户每日额度
GRAY_THRESHOLD_SCORE = 100   # 灰度解锁活跃度阈值
GRAY_THRESHOLD_GENS = 50     # 灰度解锁累计生成次数阈值


async def _supabase_request(method: str, path: str, json_data: dict | None = None, params: dict | None = None) -> dict:
    """Supabase REST API 请求封装"""
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.request(method, url, json=json_data, params=params, headers=HEADERS)
            resp.raise_for_status()
            if resp.status_code == 204:
                return {}
            return resp.json()
    except Exception as e:
        logger.warning(f"Supabase request failed ({method} {path}): {e}")
        # 容错：返回空数据，前端使用本地缓存
        return {}


async def create_or_load(user_id: str) -> dict[str, Any]:
    """首次登录自动创建记录，已存在则返回现有记录"""
    existing = await _supabase_request("GET", "beta_users", params={"user_id": f"eq.{user_id}", "limit": "1"})
    if isinstance(existing, list) and len(existing) > 0:
        return existing[0]

    # 创建新记录
    now = datetime.now(timezone.utc).isoformat()
    new_record = {
        "user_id": user_id,
        "is_gray": False,
        "daily_credits_used": 0,
        "daily_credits_limit": DAILY_LIMIT_NORMAL,
        "total_generations": 0,
        "activity_score": 0,
        "gray_unlocked_at": None,
        "created_at": now,
        "updated_at": now,
    }
    await _supabase_request("POST", "beta_users", json_data=new_record)
    return new_record


async def check_gray_status(user_id: str) -> dict[str, Any]:
    """返回当前用户灰度状态"""
    record = await create_or_load(user_id)
    can_apply = (
        not record.get("is_gray", False)
        and record.get("activity_score", 0) >= GRAY_THRESHOLD_SCORE
        and record.get("total_generations", 0) >= GRAY_THRESHOLD_GENS
    )
    return {
        "user_id": user_id,
        "is_gray": record.get("is_gray", False),
        "daily_credits_used": record.get("daily_credits_used", 0),
        "daily_credits_limit": record.get("daily_credits_limit", DAILY_LIMIT_NORMAL),
        "total_generations": record.get("total_generations", 0),
        "activity_score": record.get("activity_score", 0),
        "can_apply": can_apply,
    }


async def consume_credit(user_id: str, amount: int = 1) -> dict[str, Any]:
    """消费每日额度，超限抛异常"""
    record = await create_or_load(user_id)
    used = record.get("daily_credits_used", 0)
    limit = record.get("daily_credits_limit", DAILY_LIMIT_NORMAL)

    if used + amount > limit:
        return {"success": False, "message": f"今日免费额度已用完 ({used}/{limit})，请明天再来"}

    new_used = used + amount
    new_total = record.get("total_generations", 0) + 1
    new_score = record.get("activity_score", 0) + 2  # 每次生成 +2 活跃度

    await _supabase_request(
        "PATCH", "beta_users",
        json_data={"daily_credits_used": new_used, "total_generations": new_total, "activity_score": new_score, "updated_at": datetime.now(timezone.utc).isoformat()},
        params={"user_id": f"eq.{user_id}"},
    )

    # 检查是否满足自动升级条件
    if not record.get("is_gray") and new_score >= GRAY_THRESHOLD_SCORE and new_total >= GRAY_THRESHOLD_GENS:
        await auto_gray_promotion(user_id)

    return {"success": True, "used_today": new_used, "limit": limit, "remaining": limit - new_used}


async def apply_gray(user_id: str, reason: str, contact: str = "", feature_key: str = "") -> dict[str, Any]:
    """保存灰度申请记录"""
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "user_id": user_id,
        "reason": reason,
        "contact": contact,
        "feature_key": feature_key,
        "status": "pending",
        "created_at": now,
    }
    await _supabase_request("POST", "beta_gray_applications", json_data=record)
    return {"success": True, "message": "申请已提交，我们会在 1-3 个工作日内审核"}


async def auto_gray_promotion(user_id: str) -> dict[str, Any]:
    """当活跃度和生成次数达标时，自动升级为灰度用户"""
    now = datetime.now(timezone.utc).isoformat()
    await _supabase_request(
        "PATCH", "beta_users",
        json_data={"is_gray": True, "daily_credits_limit": DAILY_LIMIT_GRAY, "gray_unlocked_at": now, "updated_at": now},
        params={"user_id": f"eq.{user_id}"},
    )
    logger.info(f"用户 {user_id} 已自动升级为灰度用户")
    return {"success": True, "message": "恭喜！您已自动升级为资深测试用户"}


# 功能权限映射表
FEATURE_ACCESS_MAP: dict[str, dict] = {
    # 全开放
    "mureka_generate":  {"level": "open",  "name": "AI 作曲生成"},
    "lyrics_generate":  {"level": "open",  "name": "AI 歌词创作"},
    "midi_basic":       {"level": "open",  "name": "基础 MIDI 编曲"},
    "tts":              {"level": "open",  "name": "TTS 人声合成"},
    "daw_edit":         {"level": "open",  "name": "DAW 剪辑"},
    "watermark":        {"level": "open",  "name": "音频水印"},
    "like_favorite":    {"level": "open",  "name": "点赞收藏"},
    "basic_copyright":  {"level": "open",  "name": "基础版权检测"},
    # 灰度锁定
    "mv_generate":      {"level": "gray",  "name": "MV 生成"},
    "ws_collab":        {"level": "gray",  "name": "实时协作编辑"},
    "hf_models":        {"level": "gray",  "name": "HF 第三方模型"},
    "subtitle":         {"level": "gray",  "name": "字幕识别"},
    "oneclick_publish": {"level": "gray",  "name": "一键多平台发布"},
    # 完全关闭
    "voice_clone":       {"level": "closed", "name": "声音克隆"},
    "asset_store":       {"level": "closed", "name": "素材商城"},
    "paid_subscription": {"level": "closed", "name": "付费订阅"},
    "messaging":         {"level": "closed", "name": "私信聊天"},
    "ugc_earnings":      {"level": "closed", "name": "UGC 收益提现"},
    "deep_copyright_db": {"level": "closed", "name": "深度版权比对库"},
}


async def get_feature_access(user_id: str) -> dict[str, Any]:
    """返回所有功能权限列表"""
    status = await check_gray_status(user_id)
    access = {}
    for key, cfg in FEATURE_ACCESS_MAP.items():
        if cfg["level"] == "open":
            access[key] = {"name": cfg["name"], "level": "open", "accessible": True}
        elif cfg["level"] == "gray":
            access[key] = {"name": cfg["name"], "level": "gray", "accessible": status["is_gray"]}
        else:
            access[key] = {"name": cfg["name"], "level": "closed", "accessible": False}
    return {"user_id": user_id, "is_gray": status["is_gray"], "features": access}


async def daily_reset() -> dict[str, Any]:
    """每日重置所有用户的 daily_credits_used（供 cron 调用）"""
    await _supabase_request(
        "PATCH", "beta_users",
        json_data={"daily_credits_used": 0, "updated_at": datetime.now(timezone.utc).isoformat()},
        params={"daily_credits_used": "gt.0"},
    )
    logger.info("每日额度已重置")
    return {"success": True, "message": "每日额度已重置"}
