"""
公测灰度权限服务 — SQLite
启动自动建表，零手动操作
"""

from __future__ import annotations

import os
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "beta.db")

DAILY_LIMIT_NORMAL = 10
DAILY_LIMIT_GRAY = 30
GRAY_THRESHOLD_SCORE = 100
GRAY_THRESHOLD_GENS = 50

def _get_conn() -> sqlite3.Connection:
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _init_db(conn)
    return conn

def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS beta_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL UNIQUE,
            is_gray INTEGER DEFAULT 0,
            daily_credits_used INTEGER DEFAULT 0,
            daily_credits_limit INTEGER DEFAULT 10,
            total_generations INTEGER DEFAULT 0,
            activity_score INTEGER DEFAULT 0,
            gray_unlocked_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS beta_gray_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            contact TEXT DEFAULT '',
            feature_key TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS beta_bug_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            report_type TEXT DEFAULT 'bug',
            description TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_bu_user_id ON beta_users(user_id);
        CREATE INDEX IF NOT EXISTS idx_bga_user_id ON beta_gray_applications(user_id);
    """)

async def create_or_load(user_id: str) -> dict[str, Any]:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM beta_users WHERE user_id = ?", (user_id,)).fetchone()
        if row: return dict(row)
        conn.execute(
            "INSERT INTO beta_users (user_id, daily_credits_limit) VALUES (?, ?)",
            (user_id, DAILY_LIMIT_NORMAL),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM beta_users WHERE user_id = ?", (user_id,)).fetchone())
    finally:
        conn.close()

async def check_gray_status(user_id: str) -> dict[str, Any]:
    r = await create_or_load(user_id)
    return {
        "user_id": user_id,
        "is_gray": bool(r.get("is_gray", 0)),
        "daily_credits_used": r.get("daily_credits_used", 0),
        "daily_credits_limit": r.get("daily_credits_limit", DAILY_LIMIT_NORMAL),
        "total_generations": r.get("total_generations", 0),
        "activity_score": r.get("activity_score", 0),
        "can_apply": not r.get("is_gray") and r["activity_score"] >= GRAY_THRESHOLD_SCORE and r["total_generations"] >= GRAY_THRESHOLD_GENS,
    }

async def consume_credit(user_id: str, amount: int = 1) -> dict[str, Any]:
    r = await create_or_load(user_id)
    used, limit = r["daily_credits_used"], r["daily_credits_limit"]
    if used + amount > limit:
        return {"success": False, "message": f"今日额度已用完 ({used}/{limit})"}
    conn = _get_conn()
    try:
        nu, ng, ns = used + amount, r["total_generations"] + 1, r["activity_score"] + 2
        conn.execute("UPDATE beta_users SET daily_credits_used=?, total_generations=?, activity_score=? WHERE user_id=?",
                     (nu, ng, ns, user_id))
        conn.commit()
    finally:
        conn.close()
    if not r["is_gray"] and ns >= GRAY_THRESHOLD_SCORE and ng >= GRAY_THRESHOLD_GENS:
        await auto_gray_promotion(user_id)
    return {"success": True, "used_today": nu, "limit": limit, "remaining": limit - nu}

async def apply_gray(user_id: str, reason: str, contact: str = "", feature_key: str = "") -> dict[str, Any]:
    conn = _get_conn()
    try:
        conn.execute("INSERT INTO beta_gray_applications(user_id,reason,contact,feature_key) VALUES(?,?,?,?)",
                     (user_id, reason, contact, feature_key))
        conn.commit()
    finally:
        conn.close()
    return {"success": True, "message": "申请已提交，1-3 个工作日内审核"}

async def auto_gray_promotion(user_id: str) -> dict[str, Any]:
    conn = _get_conn()
    try:
        conn.execute("UPDATE beta_users SET is_gray=1, daily_credits_limit=?, gray_unlocked_at=? WHERE user_id=?",
                     (DAILY_LIMIT_GRAY, datetime.now(timezone.utc).isoformat(), user_id))
        conn.commit()
    finally:
        conn.close()
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
    conn = _get_conn()
    try:
        conn.execute("UPDATE beta_users SET daily_credits_used=0 WHERE daily_credits_used>0")
        conn.commit()
        n = conn.execute("SELECT changes()").fetchone()[0]
    finally:
        conn.close()
    return {"success": True, "message": f"每日额度已重置，影响 {n} 个用户"}