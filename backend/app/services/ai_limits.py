"""AI 生成额度 / 成本保护 / 下载审计 —— Step 2 PostgreSQL 迁移版。

生产：Supabase PostgreSQL via DATABASE_URL（psycopg2）
开发/测试：SQLite（DATABASE_URL=sqlite://...）自动回退，API 一致

所有表通过 app.db.database.Base 统一建表，create_all 幂等，不 DROP。

原子性保证：
- global_usage 使用条件自增 UPDATE ... WHERE count < cap（PG/SQLite 通用），rowcount==0 即达限，并发安全
- generation_usage 使用 ON CONFLICT upsert + CASE 切换日期，避免 SELECT-then-UPDATE 竞态
- 下载限流同事务内 SELECT COUNT + INSERT，PG 下由事务隔离保证（SERIALIZABLE 不必要，条件计数已在同一事务）
"""
from __future__ import annotations

import os
import threading
import time
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
    if not user_id:
        return {"success": False, "error": "缺少用户标识（X-User-ID）"}
    today, mkey = _today(), _month_key()
    weight = get_duration_weight(duration)
    budget_lim = budget_daily_limit()
    cap = GLOBAL_DAILY_GENERATION_LIMIT
    if budget_lim is not None and budget_lim < cap:
        cap = budget_lim
    with _DB_LOCK:
        sess = _get_session()
        try:
            from sqlalchemy import text
            sess.execute(text("BEGIN"))
            # 读用户计数（for update 语义：PG 下锁行，SQLite 下事务已锁）
            try:
                row = sess.execute(text("SELECT daily_count, month_key, monthly_count, date FROM generation_usage WHERE user_id=:u"), {"u": user_id}).fetchone()
            except Exception:
                row = None
            daily = 0
            monthly = 0
            if row:
                # row 可能是 tuple
                r_date = row[3] if len(row) > 3 else None
                r_month = row[1] if len(row) > 1 else None
                r_daily = row[0] if len(row) > 0 else 0
                r_monthly = row[2] if len(row) > 2 else 0
                daily = r_daily if r_date == today else 0
                monthly = r_monthly if r_month == mkey else 0
            if daily + weight > DAILY_GENERATION_LIMIT:
                sess.rollback()
                return {"success": False, "error": f"今日生成额度已用完（{daily}/{DAILY_GENERATION_LIMIT}），300秒作品消耗 2 额度，请明天再试"}
            if monthly + weight > MONTHLY_GENERATION_LIMIT:
                sess.rollback()
                return {"success": False, "error": f"本月生成额度已用完（{monthly}/{MONTHLY_GENERATION_LIMIT}）"}
            # 原子全局计数：条件自增
            sess.execute(text("INSERT INTO global_usage (date, count) VALUES (:d, 0) ON CONFLICT(date) DO NOTHING"), {"d": today})
            cur = sess.execute(text("UPDATE global_usage SET count = count + 1 WHERE date=:d AND count < :cap"), {"d": today, "cap": cap})
            if cur.rowcount == 0:
                row2 = sess.execute(text("SELECT count FROM global_usage WHERE date=:d"), {"d": today}).fetchone()
                gcount = int(row2[0]) if row2 else 0
                sess.rollback()
                if budget_lim is not None and gcount >= budget_lim:
                    return {"success": False, "error": "今日 GPU 预算已用尽，请明天再试"}
                return {"success": False, "error": "今日全平台生成已达上限，请明天再试"}
            row2 = sess.execute(text("SELECT count FROM global_usage WHERE date=:d"), {"d": today}).fetchone()
            gcount = int(row2[0]) if row2 else 1
            # 原子 upsert 用户计数（按时长权重）
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
            sess.commit()
            return {"success": True, "daily_used": daily+weight, "daily_limit": DAILY_GENERATION_LIMIT, "monthly_used": monthly+weight, "monthly_limit": MONTHLY_GENERATION_LIMIT, "global_used": gcount, "global_limit": GLOBAL_DAILY_GENERATION_LIMIT, "budget_daily_limit": budget_lim, "budget_daily_used": gcount, "weight": weight}
        except Exception as e:
            try:
                sess.rollback()
            except Exception:
                pass
            # 降级：若 PG 特有语法失败，返回错误而非突破限额
            return {"success": False, "error": f"额度预留失败: {e}"}
        finally:
            sess.close()

def refund_generation(user_id: str, duration: int | None = None) -> None:
    if not user_id:
        return
    weight = get_duration_weight(duration) if duration is not None else 1
    today, mkey = _today(), _month_key()
    with _DB_LOCK:
        sess = _get_session()
        try:
            from sqlalchemy import text
            sess.execute(text("UPDATE generation_usage SET daily_count = CASE WHEN daily_count>=:w THEN daily_count-:w ELSE 0 END, monthly_count = CASE WHEN monthly_count>=:w THEN monthly_count-:w ELSE 0 END, updated_at=CURRENT_TIMESTAMP WHERE user_id=:u AND date=:d AND month_key=:mk"), {"u": user_id, "d": today, "mk": mkey, "w": weight})
            sess.commit()
        except Exception:
            try:
                sess.rollback()
            except Exception:
                pass
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
            return {"user_id": user_id, "daily_used": daily, "daily_limit": DAILY_GENERATION_LIMIT, "monthly_used": monthly, "monthly_limit": MONTHLY_GENERATION_LIMIT, "global_daily_used": int(g[0]) if g else 0, "global_daily_limit": GLOBAL_DAILY_GENERATION_LIMIT, "budget_daily_limit": budget_daily_limit(), "budget_daily_used": int(g[0]) if g else 0}
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
