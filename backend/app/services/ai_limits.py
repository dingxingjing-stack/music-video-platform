"""AI 生成额度 / 成本保护 / 下载审计 —— Step 2 PostgreSQL 迁移版。

生产：Supabase PostgreSQL via DATABASE_URL（psycopg2）
开发/测试：SQLite（DATABASE_URL=sqlite://...）自动回退，API 一致

所有表通过 app.db.database.Base 统一建表，create_all 幂等，不 DROP。

原子性保证：
- global_usage 使用条件自增 UPDATE ... WHERE count < cap（PG/SQLite 通用），rowcount==0 即达限，并发安全
- generation_usage 使用 ON CONFLICT upsert + CASE 切换日期，避免 SELECT-then-UPDATE 竞态
- beta_users 使用条件更新 WHERE ... + amount <= limit，避免竞态
- 统一额度预留在单一数据库事务中完成：全部成功或全部回滚，无部分消费残留
- 下载限流同事务内 SELECT COUNT + INSERT，PG 下由事务隔离保证
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

# 保留原常量（环境变量覆盖）
DAILY_GENERATION_LIMIT = int(os.getenv("DAILY_GENERATION_LIMIT", "1"))
MONTHLY_GENERATION_LIMIT = int(os.getenv("MONTHLY_GENERATION_LIMIT", "15"))
GLOBAL_DAILY_GENERATION_LIMIT = int(os.getenv("GLOBAL_DAILY_GENERATION_LIMIT", "30"))
MAX_AUDIO_DURATION_SECONDS = int(os.getenv("MAX_AUDIO_DURATION_SECONDS", "300"))
MAX_CONCURRENT_JOBS_PER_USER = int(os.getenv("MAX_CONCURRENT_JOBS_PER_USER", "1"))
MAX_AUTO_RETRIES = int(os.getenv("MAX_AUTO_RETRIES", "1"))
MAX_TASK_RUNTIME_SECONDS = int(os.getenv("MAX_TASK_RUNTIME_SECONDS", "900"))
DOWNLOAD_RATE_LIMIT = int(os.getenv("DOWNLOAD_RATE_LIMIT", "10"))
DOWNLOAD_RATE_WINDOW_SECONDS = int(os.getenv("DOWNLOAD_RATE_WINDOW_SECONDS", "3600"))
MODAL_BUDGET_DAILY = os.getenv("FAL_BUDGET_DAILY") or os.getenv("GPU_BUDGET_DAILY") or os.getenv("MODAL_BUDGET_DAILY", "")

# beta_users 默认值（与 beta_service 对齐）
DAILY_LIMIT_NORMAL = 10
DAILY_LIMIT_GRAY = 30

# ── 为测试兼容保留旧变量（测试会 monkeypatch _DB_PATH） ──
_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
_DB_PATH = os.path.join(_DB_DIR, "beta.db")
_DEFAULT_DB_PATH = _DB_PATH
_DB_LOCK = threading.Lock()

def _is_test_override() -> bool:
    return _DB_PATH != _DEFAULT_DB_PATH

def _get_session():
    """返回 Session；测试覆盖时使用临时 SQLite 文件，否则使用全局 database.SessionLocal。"""
    if _is_test_override():
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        # 测试复用/创建临时 SQLite
        url = f"sqlite:///{_DB_PATH}"
        eng = create_engine(url, connect_args={"check_same_thread": False}, pool_pre_ping=True)
        # 确保表存在（幂等）
        try:
            from app.db.database import Base
            Base.metadata.create_all(bind=eng)
        except Exception:
            pass
        return sessionmaker(bind=eng)()
    from app.db.database import SessionLocal, Base, engine
    # 首次确保建表（生产安全：不 DROP）
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        pass
    return SessionLocal()

def _today() -> str:
    import datetime
    return datetime.date.today().isoformat()

def _month_key() -> str:
    import datetime
    return datetime.date.today().strftime("%Y-%m")

def budget_daily_limit() -> Optional[int]:
    if not MODAL_BUDGET_DAILY:
        return None
    try:
        return max(int(MODAL_BUDGET_DAILY), 0)
    except (TypeError, ValueError):
        return None

def budget_hard_stop_reached() -> bool:
    lim = budget_daily_limit()
    if lim is None:
        return False
    today = _today()
    with _DB_LOCK:
        sess = _get_session()
        try:
            from sqlalchemy import text
            row = sess.execute(text("SELECT count FROM global_usage WHERE date=:d"), {"d": today}).fetchone()
            return bool(row and row[0] >= lim)
        finally:
            sess.close()

def global_hard_stop_reached() -> bool:
    """全平台成本硬停判断（只读、不扣额度）。

    覆盖更全的 global 硬停线：取 min(GLOBAL_DAILY_GENERATION_LIMIT, GPU 预算)。
    用于「不纳入用户 generation quota 但仍会消耗真实 GPU 成本」的只读口，
    例如 retry-stems（分轨重试不计普通生成额度，但必须受全平台 cost 保护）。

    返回 True 表示已达到全平台硬停，应拒绝任何新的 GPU 工作。
    """
    today = _today()
    with _DB_LOCK:
        sess = _get_session()
        try:
            from sqlalchemy import text
            row = sess.execute(text("SELECT count FROM global_usage WHERE date=:d"), {"d": today}).fetchone()
            cnt = int(row[0]) if row else 0
        finally:
            sess.close()
    # 上限 = 全平台每日上限 与 GPU 预算 的较小者（与 reserve_generation 的 cap 语义一致）
    cap = GLOBAL_DAILY_GENERATION_LIMIT
    budget_lim = budget_daily_limit()
    if budget_lim is not None and budget_lim < cap:
        cap = budget_lim
    return cnt >= cap

def check_and_log_download(user_id: str, job_id: str, file_type: str, ip_address: str = "") -> bool:
    if not user_id:
        return True
    with _DB_LOCK:
        sess = _get_session()
        try:
            from sqlalchemy import text
            cutoff = time.time() - DOWNLOAD_RATE_WINDOW_SECONDS
            now = time.time()
            sess.execute(text("BEGIN"))
            # 清理过期（兼容 Float 时间戳，历史 TEXT 类型会被 SQLite 隐式转换失败则跳过）
            try:
                sess.execute(text("DELETE FROM download_logs WHERE user_id=:u AND created_at < :cut"), {"u": user_id, "cut": cutoff})
            except Exception:
                pass
            row = sess.execute(text("SELECT COUNT(*) FROM download_logs WHERE user_id=:u AND created_at > :cut"), {"u": user_id, "cut": cutoff}).fetchone()
            cnt = int(row[0]) if row else 0
            if cnt >= DOWNLOAD_RATE_LIMIT:
                sess.rollback()
                return False
            sess.execute(text("INSERT INTO download_logs (user_id, job_id, file_type, ip_address, created_at) VALUES (:u, :j, :f, :ip, :now)"), {"u": user_id, "j": job_id, "f": file_type, "ip": ip_address or "", "now": now})
            sess.commit()
            return True
        except Exception:
            try:
                sess.rollback()
            except Exception:
                pass
            return False
        finally:
            sess.close()

def _init_db_pg(conn=None):
    # 由 database.Base.create_all 已处理，此函数保留兼容旧调用
    pass

def get_duration_weight(duration: int | None) -> int:
    """时长权重：≤120s 1 credit，>120s 2 credits（180/240/300 均 2）"""
    try:
        d = int(duration) if duration is not None else 0
    except Exception:
        d = 0
    return 2 if d > 120 else 1

def reserve_generation(user_id: str, duration: int | None = None) -> dict[str, Any]:
    """
    统一额度预留 —— 全部真实 AI 生成的唯一权威入口。

    在**单一数据库事务**中原子性完成四层检查 + 四层扣减（全过才提交，任一失败整体回滚）：
    1. beta_users 权益（每日 credits）：daily_credits_used + weight <= daily_credits_limit
       —— 权威限额来源是 beta_users.daily_credits_limit（10 普通 / 30 灰度），
          由 beta_service 灰度升级时写入，此处只读、不再硬编码 10/30 双份。
    2. generation_usage 每日生成数：daily_count + weight <= DAILY_GENERATION_LIMIT
    3. generation_usage 每月生成数：monthly_count + weight <= MONTHLY_GENERATION_LIMIT
    4. global_usage 全平台硬停：count < min(GLOBAL_DAILY_GENERATION_LIMIT, GPU 预算)

    并发安全（不依赖 Python threading.Lock，跨进程/Worker 有效）：
    - PostgreSQL：BEGIN 后对 beta_users 用户行 `SELECT ... FOR UPDATE` 加行级锁，
      序列化同一用户的所有预留；global_usage 用 `UPDATE ... WHERE count < cap`
      条件自增（rowcount==0 即达限）做跨用户硬停。
    - SQLite（开发/测试）：写事务自带库级锁；beta_users 的最终扣减是单条
      条件 UPDATE（`WHERE used + weight <= limit`）原子判定 rowcount，杜绝
      SELECT-then-UPDATE 竞态导致的超卖。
    """
    if not user_id:
        return {"success": False, "error": "缺少用户标识（X-User-ID）"}
    today, mkey = _today(), _month_key()
    weight = get_duration_weight(duration)
    budget_lim = budget_daily_limit()
    cap = GLOBAL_DAILY_GENERATION_LIMIT
    if budget_lim is not None and budget_lim < cap:
        cap = budget_lim

    sess = _get_session()
    try:
        from sqlalchemy import text
        # 生产 PG 行级锁；SQLite 无 FOR UPDATE 语法，靠写事务 + 条件更新兜底
        is_pg = "postgresql" in (sess.get_bind().dialect.name or "")
        lock_clause = " FOR UPDATE" if is_pg else ""

        sess.execute(text("BEGIN"))

        # 1) 确保 beta_users 行存在（幂等，保留现有数据）
        sess.execute(text("""
            INSERT INTO beta_users (user_id, is_gray, daily_credits_used, daily_credits_limit, total_generations, activity_score, updated_at)
            VALUES (:u, 0, 0, :lim, 0, 0, :ts)
            ON CONFLICT(user_id) DO NOTHING
        """), {"u": user_id, "lim": DAILY_LIMIT_NORMAL, "ts": datetime.now(timezone.utc).isoformat()})

        # 2) 锁定并读取 beta_users 权益（权威限额来源 = 数据库行内 daily_credits_limit）
        row = sess.execute(text(
            "SELECT daily_credits_used, daily_credits_limit, is_gray "
            "FROM beta_users WHERE user_id = :u" + lock_clause
        ), {"u": user_id}).fetchone()

        if not row:
            sess.rollback()
            return {"success": False, "error": "用户不存在"}

        beta_used = row[0] or 0
        beta_limit = row[1] or DAILY_LIMIT_NORMAL
        is_gray = bool(row[2] or 0)

        if beta_used + weight > beta_limit:
            sess.rollback()
            return {"success": False, "error": f"今日额度已用完（{beta_used}/{beta_limit}），300 秒作品消耗 2 额度，请明天再试"}

        # 3) 读取 generation_usage 日/月计数（已被用户行锁串行化，PG 下无竞态）
        gu = sess.execute(text(
            "SELECT daily_count, monthly_count, date, month_key FROM generation_usage WHERE user_id=:u"
        ), {"u": user_id}).fetchone()
        daily = 0
        monthly = 0
        if gu:
            r_date = gu[2] if len(gu) > 2 else None
            r_month = gu[3] if len(gu) > 3 else None
            daily = (gu[0] or 0) if r_date == today else 0
            monthly = (gu[1] or 0) if r_month == mkey else 0

        if daily + weight > DAILY_GENERATION_LIMIT:
            sess.rollback()
            return {"success": False, "error": f"今日生成额度已用完（{daily}/{DAILY_GENERATION_LIMIT}），300 秒作品消耗 2 额度，请明天再试"}

        if monthly + weight > MONTHLY_GENERATION_LIMIT:
            sess.rollback()
            return {"success": False, "error": f"本月生成额度已用完（{monthly}/{MONTHLY_GENERATION_LIMIT}）"}

        # 4) global_usage 全平台硬停：原子条件自增（跨用户，PG/SQLite 通用）
        sess.execute(text("INSERT INTO global_usage (date, count) VALUES (:d, 0) ON CONFLICT(date) DO NOTHING"), {"d": today})
        gcur = sess.execute(text(
            "UPDATE global_usage SET count = count + :inc WHERE date=:d AND count < :cap"
        ), {"d": today, "cap": cap, "inc": 1})
        if gcur.rowcount == 0:
            row2 = sess.execute(text("SELECT count FROM global_usage WHERE date=:d"), {"d": today}).fetchone()
            gcount = int(row2[0]) if row2 else 0
            sess.rollback()
            if budget_lim is not None and gcount >= budget_lim:
                return {"success": False, "error": "今日 GPU 预算已用尽，请明天再试"}
            return {"success": False, "error": "今日全平台生成已达上限，请明天再试"}

        row2 = sess.execute(text("SELECT count FROM global_usage WHERE date=:d"), {"d": today}).fetchone()
        gcount = int(row2[0]) if row2 else 1

        # 5) beta_users 条件扣减（最终守卫：单条原子 UPDATE + rowcount 判定）
        ts = datetime.now(timezone.utc).isoformat()
        bcur = sess.execute(text("""
            UPDATE beta_users
            SET daily_credits_used = COALESCE(daily_credits_used, 0) + :w,
                total_generations   = COALESCE(total_generations, 0) + 1,
                activity_score      = COALESCE(activity_score, 0) + 2,
                updated_at          = :ts
            WHERE user_id = :u
              AND COALESCE(daily_credits_used, 0) + :w <= COALESCE(daily_credits_limit, :def_limit)
        """), {"u": user_id, "w": weight, "ts": ts, "def_limit": DAILY_LIMIT_NORMAL})

        if bcur.rowcount == 0:
            # 并发极端情况：上面检查通过但扣减时已超限（SQLite 无行锁时的兜底）
            sess.rollback()
            return {"success": False, "error": "并发冲突，额度不足，请重试"}

        # 6) generation_usage 日/月 upsert（同一事务内，与上面扣减一起提交/回滚）
        sess.execute(text("""
            INSERT INTO generation_usage (user_id, date, daily_count, month_key, monthly_count)
            VALUES (:u, :d, :dc, :mk, :mc)
            ON CONFLICT(user_id) DO UPDATE SET
              date=excluded.date,
              daily_count=CASE WHEN generation_usage.date=excluded.date THEN generation_usage.daily_count+:w ELSE :w2 END,
              month_key=excluded.month_key,
              monthly_count=CASE WHEN generation_usage.month_key=excluded.month_key THEN generation_usage.monthly_count+:w ELSE :w2 END,
              updated_at=CURRENT_TIMESTAMP
        """), {"u": user_id, "d": today, "dc": daily+weight, "mk": mkey, "mc": monthly+weight, "w": weight, "w2": weight})

        # 7) 提交 —— 三表更新要么全部生效、要么全部回滚，无部分消费残留
        sess.commit()

        return {
            "success": True,
            "daily_used": daily+weight,
            "daily_limit": DAILY_GENERATION_LIMIT,
            "monthly_used": monthly+weight,
            "monthly_limit": MONTHLY_GENERATION_LIMIT,
            "global_used": gcount,
            "global_limit": GLOBAL_DAILY_GENERATION_LIMIT,
            "budget_daily_limit": budget_lim,
            "budget_daily_used": gcount,
            "weight": weight,
            "beta_credits_used": beta_used + weight,
            "beta_credits_limit": beta_limit,
            "is_gray": is_gray,
        }
    except Exception as e:
        try:
            sess.rollback()
        except Exception:
            pass
        # 降级：任何异常都回滚并失败，绝不突破限额
        return {"success": False, "error": f"额度预留失败: {e}"}
    finally:
        sess.close()

def refund_generation(user_id: str, duration: int | None = None, reason: str = "provider_failure") -> dict[str, Any]:
    """
    统一退款语义 —— 根据失败原因决定是否退还用户额度。
    
    Args:
        reason: 失败原因，决定退款策略：
            - "validation_failed"      : 验证失败，provider 请求未发送 → 无预留或立即回滚
            - "request_not_sent"       : provider 请求确定未发送 → 回滚用户预留
            - "provider_failed"        : provider 明确返回失败 → 回滚用户预留
            - "timeout_unknown"        : 超时/未知结果，请求可能已发送 → **不退款**，防免费生成漏洞
            - "persistence_failed"     : provider 成功但持久化失败 → **不退款**，可能已产生真实成本
    
    返回:
        dict: {"success": bool, "refunded": bool, "weight": int, "reason": str, "error?: str"}
    
    注意: global_usage **永不退款**（成本保护硬停），防止 "失败→退款→重试" 空转 GPU 预算。
    """
    if not user_id:
        return {"success": False, "error": "缺少用户标识", "refunded": False}
    
    # 超时/未知结果、持久化失败 —— 不退款
    if reason in ("timeout_unknown", "persistence_failed"):
        return {"success": False, "error": f"不退款: {reason}", "refunded": False, "reason": reason}
    
    weight = get_duration_weight(duration) if duration is not None else 1
    today, mkey = _today(), _month_key()
    
    sess = _get_session()
    try:
        from sqlalchemy import text
        sess.execute(text("BEGIN"))
        
        # 退还 beta_users daily_credits_used（不低于 0）
        sess.execute(text("""
            UPDATE beta_users
            SET daily_credits_used = CASE WHEN daily_credits_used >= :w THEN daily_credits_used - :w ELSE 0 END,
                updated_at = :ts
            WHERE user_id = :u
        """), {"u": user_id, "w": weight, "ts": datetime.now(timezone.utc).isoformat()})
        
        # 退还 generation_usage（daily_count, monthly_count，不低于 0）。
        # 注意：generation_usage.user_id 是主键，每用户只有一行；reserve 在跨日/跨月时会
        # 用新 date/month_key 改写该行，因此退款必须按 user_id 单一条件扣减，
        # 否则跨午夜 reserve/refund 不匹配旧日期行 → 出现部分退款（beta 退了、generation 漏退）。
        sess.execute(text("""
            UPDATE generation_usage
            SET daily_count = CASE WHEN daily_count >= :w THEN daily_count - :w ELSE 0 END,
                monthly_count = CASE WHEN monthly_count >= :w THEN monthly_count - :w ELSE 0 END,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = :u
        """), {"u": user_id, "w": weight})
        
        # global_usage 永不退款 —— 成本保护硬停
        # 这是有意为之，防止 "失败→退款→重试" 空转 GPU 预算漏洞
        
        sess.commit()
        return {"success": True, "refunded": True, "weight": weight, "reason": reason}
    except Exception as e:
        try:
            sess.rollback()
        except Exception:
            pass
        return {"success": False, "error": f"退款失败: {e}", "refunded": False, "reason": reason}
    finally:
        sess.close()

async def generation_usage_status(user_id: str) -> dict[str, Any]:
    today, mkey = _today(), _month_key()
    with _DB_LOCK:
        sess = _get_session()
        try:
            from sqlalchemy import text
            row = None
            try:
                row = sess.execute(text("SELECT daily_count, month_key, monthly_count, date FROM generation_usage WHERE user_id=:u"), {"u": user_id}).fetchone()
            except Exception:
                row = None
            g = None
            try:
                g = sess.execute(text("SELECT count FROM global_usage WHERE date=:d"), {"d": today}).fetchone()
            except Exception:
                pass
            daily = 0
            monthly = 0
            if row:
                r_date = row[3] if len(row) > 3 else None
                r_month = row[1] if len(row) > 1 else None
                if r_date == today:
                    daily = row[0]
                if r_month == mkey:
                    monthly = row[2]
            # 同时返回 beta_users 状态
            beta_row = None
            try:
                beta_row = sess.execute(text("SELECT daily_credits_used, daily_credits_limit, is_gray FROM beta_users WHERE user_id=:u"), {"u": user_id}).fetchone()
            except Exception:
                pass
            beta_used = beta_row[0] if beta_row else 0
            beta_limit = beta_row[1] if beta_row else DAILY_LIMIT_NORMAL
            is_gray = bool(beta_row[2]) if beta_row else False
            return {
                "user_id": user_id,
                "daily_used": daily,
                "daily_limit": DAILY_GENERATION_LIMIT,
                "monthly_used": monthly,
                "monthly_limit": MONTHLY_GENERATION_LIMIT,
                "global_daily_used": int(g[0]) if g else 0,
                "global_daily_limit": GLOBAL_DAILY_GENERATION_LIMIT,
                "budget_daily_limit": budget_daily_limit(),
                "budget_daily_used": int(g[0]) if g else 0,
                "beta_credits_used": beta_used,
                "beta_credits_limit": beta_limit,
                "is_gray": is_gray
            }
        finally:
            sess.close()

# 兼容旧接口：保留 _get_conn / _init_db 供测试/旧代码检查，但已不再作为主路径
def _get_conn():
    # 为静态检查兼容，返回 sqlite 连接（仅测试/迁移脚本可能调用）
    import sqlite3
    import pathlib
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def _init_db(conn=None):
    if conn is not None:
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS generation_usage (user_id TEXT PRIMARY KEY, date TEXT NOT NULL, daily_count INTEGER NOT NULL DEFAULT 0, month_key TEXT NOT NULL, monthly_count INTEGER NOT NULL DEFAULT 0, updated_at TEXT DEFAULT (datetime('now')));
                CREATE TABLE IF NOT EXISTS global_usage (date TEXT PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS download_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, job_id TEXT NOT NULL, file_type TEXT NOT NULL, ip_address TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now')));
            """)
        except Exception:
            pass
    else:
        from app.db.database import Base, engine
        Base.metadata.create_all(bind=engine)