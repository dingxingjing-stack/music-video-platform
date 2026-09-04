"""
公测灰度权限服务 — Step 2 PostgreSQL 迁移版
通过 app.db.database 统一访问，生产 PG / 开发 SQLite 自动切换
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from typing import Any
import threading

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "beta.db")
_DEFAULT_DB_PATH = DB_PATH
_DB_LOCK = threading.Lock()

DAILY_LIMIT_NORMAL = 10
DAILY_LIMIT_GRAY = 30
GRAY_THRESHOLD_SCORE = 100
GRAY_THRESHOLD_GENS = 50

def _is_test_override() -> bool:
    return DB_PATH != _DEFAULT_DB_PATH

def _get_session():
    if _is_test_override():
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        url = f"sqlite:///{DB_PATH}"
        eng = create_engine(url, connect_args={"check_same_thread": False}, pool_pre_ping=True)
        try:
            from app.db.database import Base
            Base.metadata.create_all(bind=eng)
        except Exception:
            pass
        return sessionmaker(bind=eng)()
    from app.db.database import SessionLocal, Base, engine
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        pass
    return SessionLocal()

def _get_conn():
    # 兼容旧直接 sqlite 访问的测试/脚本
    import sqlite3
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _init_db(conn=None):
    if _is_test_override():
        from sqlalchemy import create_engine
        from app.db.database import Base
        url = f"sqlite:///{DB_PATH}"
        eng = create_engine(url, connect_args={"check_same_thread": False}, pool_pre_ping=True)
        Base.metadata.create_all(bind=eng)
    else:
        from app.db.database import Base, engine
        Base.metadata.create_all(bind=engine)

async def create_or_load(user_id: str) -> dict[str, Any]:
    sess = _get_session()
    try:
        from sqlalchemy import text
        row = sess.execute(text("SELECT * FROM beta_users WHERE user_id=:u"), {"u": user_id}).fetchone()
        if row:
            d = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
            return d
        sess.execute(text("INSERT INTO beta_users (user_id, daily_credits_limit) VALUES (:u, :lim)"), {"u": user_id, "lim": DAILY_LIMIT_NORMAL})
        sess.commit()
        row = sess.execute(text("SELECT * FROM beta_users WHERE user_id=:u"), {"u": user_id}).fetchone()
        return dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
    finally:
        sess.close()

async def check_gray_status(user_id: str) -> dict[str, Any]:
    r = await create_or_load(user_id)
    # Use .get() with defaults to safely handle NULL values from database
    is_gray = bool(r.get("is_gray") or 0)
    daily_credits_used = r.get("daily_credits_used") or 0
    daily_credits_limit = r.get("daily_credits_limit") or DAILY_LIMIT_NORMAL
    total_generations = r.get("total_generations") or 0
    activity_score = r.get("activity_score") or 0
    return {
        "user_id": user_id,
        "is_gray": is_gray,
        "daily_credits_used": daily_credits_used,
        "daily_credits_limit": daily_credits_limit,
        "total_generations": total_generations,
        "activity_score": activity_score,
        "can_apply": (not is_gray) and activity_score >= GRAY_THRESHOLD_SCORE and total_generations >= GRAY_THRESHOLD_GENS,
    }

async def consume_credit(user_id: str, amount: int = 1) -> dict[str, Any]:
    r = await create_or_load(user_id)
    # Use .get() with defaults to safely handle NULL values
    used = r.get("daily_credits_used") or 0
    limit = r.get("daily_credits_limit") or DAILY_LIMIT_NORMAL
    total_generations = r.get("total_generations") or 0
    activity_score = r.get("activity_score") or 0
    is_gray = bool(r.get("is_gray") or 0)
    if used + amount > limit:
        return {"success": False, "message": f"今日额度已用完 ({used}/{limit})"}
    sess = _get_session()
    try:
        from sqlalchemy import text
        nu, ng, ns = used + amount, total_generations + 1, activity_score + 2
        sess.execute(text("UPDATE beta_users SET daily_credits_used=:nu, total_generations=:ng, activity_score=:ns WHERE user_id=:u"), {"nu": nu, "ng": ng, "ns": ns, "u": user_id})
        sess.commit()
    finally:
        sess.close()
    if not is_gray and ns >= GRAY_THRESHOLD_SCORE and ng >= GRAY_THRESHOLD_GENS:
        await auto_gray_promotion(user_id)
    return {"success": True, "used_today": nu, "limit": limit, "remaining": limit - nu}

async def apply_gray(user_id: str, reason: str, contact: str = "", feature_key: str = "") -> dict[str, Any]:
    sess = _get_session()
    try:
        from sqlalchemy import text
        sess.execute(text("INSERT INTO beta_gray_applications(user_id,reason,contact,feature_key) VALUES(:u,:r,:c,:f)"), {"u": user_id, "r": reason, "c": contact, "f": feature_key})
        sess.commit()
    finally:
        sess.close()
    return {"success": True, "message": "申请已提交，1-3 个工作日内审核"}

async def auto_gray_promotion(user_id: str) -> dict[str, Any]:
    sess = _get_session()
    try:
        from sqlalchemy import text
        sess.execute(text("UPDATE beta_users SET is_gray=1, daily_credits_limit=:lim, gray_unlocked_at=:ts WHERE user_id=:u"), {"lim": DAILY_LIMIT_GRAY, "ts": datetime.now(timezone.utc).isoformat(), "u": user_id})
        sess.commit()
    finally:
        sess.close()
    return {"success": True, "message": "恭喜！已自动升级为资深测试用户"}

FEATURE_ACCESS_MAP: dict[str, dict] = {
    "mureka_generate":  {"level": "open",  "name": "AI 作曲生成"},
    "lyrics_generate":  {"level": "open",  "name": "AI 歌词创作"},
    "midi_basic":       {"level": "open",  "name": "基础 MIDI 编曲"},
    "tts":              {"level": "open",  "name": "TTS 人声合成"},
    "daw_edit":         {"level": "open",  "name": "DAW 剪辑"},
    "watermark":        {"level": "open",  "name": "音频水印"},
    "like_favorite":    {"level": "open",  "name": "点赞收藏"},
    "basic_copyright":  {"level": "open",  "name": "基础版权检测"},
    "mv_generate":      {"level": "gray",  "name": "MV 生成"},
    "ws_collab":        {"level": "gray",  "name": "实时协作编辑"},
    "hf_models":        {"level": "gray",  "name": "HF 第三方模型"},
    "subtitle":         {"level": "gray",  "name": "字幕识别"},
    "oneclick_publish": {"level": "gray",  "name": "一键多平台发布"},
    "voice_clone":       {"level": "closed", "name": "声音克隆"},
    "asset_store":       {"level": "closed", "name": "素材商城"},
    "paid_subscription": {"level": "closed", "name": "付费订阅"},
    "messaging":         {"level": "closed", "name": "私信聊天"},
    "ugc_earnings":      {"level": "closed", "name": "UGC 收益提现"},
    "deep_copyright_db": {"level": "closed", "name": "深度版权比对库"},
}

async def get_feature_access(user_id: str) -> dict[str, Any]:
    s = await check_gray_status(user_id)
    f = {}
    for k, c in FEATURE_ACCESS_MAP.items():
        if c["level"] == "open":       f[k] = {"name": c["name"], "level": "open", "accessible": True}
        elif c["level"] == "gray":     f[k] = {"name": c["name"], "level": "gray", "accessible": s["is_gray"]}
        else:                          f[k] = {"name": c["name"], "level": "closed", "accessible": False}
    return {"user_id": user_id, "is_gray": s["is_gray"], "features": f}

async def daily_reset() -> dict[str, Any]:
    sess = _get_session()
    try:
        from sqlalchemy import text
        cur = sess.execute(text("UPDATE beta_users SET daily_credits_used=0 WHERE daily_credits_used>0"))
        sess.commit()
        n = cur.rowcount
    finally:
        sess.close()
    return {"success": True, "message": f"每日额度已重置，影响 {n} 个用户"}
