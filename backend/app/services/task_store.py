"""任务存储 — Step 2 PostgreSQL 迁移版。

统一通过 app.db.database（DATABASE_URL）访问。
生产：Supabase PostgreSQL；开发/测试：SQLite 自动回退。
所有表由 database.Base 统一建表，create_all 幂等。

多实例锁：PG/SQLite 均通过 DB 条件 INSERT + 事务保证，原进程内 dict 已移除。
"""

import os
import time
import uuid
import logging
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

TASK_TIMEOUT = float(os.getenv("TASK_TIMEOUT", "600"))

# 终态：一旦进入就不可逆（F1）。带 state 的写入必须在数据库层用这个集合裁决，
# 不能只在 Python 里判断——判断与写入之间必有 race。
TERMINAL_STATES = ("completed", "completed_with_stems_failed", "failed")
# text() 不能把 tuple 绑进 IN，这里内联固定字面量（无任何外部输入）
_TERMINAL_LIST = "(" + ", ".join(f"'{s}'" for s in TERMINAL_STATES) + ")"

_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
_DB_PATH = os.path.join(_DB_DIR, "beta.db")
_DEFAULT_DB_PATH = _DB_PATH
_DB_LOCK = threading.Lock()

def _is_test_override() -> bool:
    return _DB_PATH != _DEFAULT_DB_PATH

def _get_session():
    if _is_test_override():
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        url = f"sqlite:///{_DB_PATH}"
        eng = create_engine(url, connect_args={"check_same_thread": False}, pool_pre_ping=True)
        try:
            from app.db.database import Base
            Base.metadata.create_all(bind=eng)
        except Exception:
            pass
        return sessionmaker(bind=eng)()
    # 生产：复用全局 Engine/SessionLocal，不在此处建表（schema init 由 startup 统一完成）
    from app.db.database import SessionLocal
    return SessionLocal()

def _row_to_task(row) -> Dict[str, Any]:
    import json
    if row is None:
        return None
    # row 可能是 ORM 对象或 Row
    if hasattr(row, "_mapping"):
        d = dict(row._mapping)
    elif hasattr(row, "__dict__"):
        d = {c.name: getattr(row, c.name) for c in row.__table__.columns}
    else:
        d = dict(row)
    for col in ("download", "volume_files", "stems"):
        v = d.get(col)
        if isinstance(v, str):
            try:
                d[col] = json.loads(v)
            except Exception:
                d[col] = None
        elif v is None:
            pass
    return d

def new_task(user_key: Optional[str] = None, task_id: Optional[str] = None,
             generation_quota_weight: Optional[int] = None) -> str:
    """建任务行。

    generation_quota_weight：本次生成在 reserve_generation 中实际预留的日/月额度权重，
    建表时就要写入 —— 退款若届时再按 duration 推断，口径可能已与预留不一致。
    非生成类任务（workflow 等）不预留权重时传 None。
    """
    tid = task_id or f"task-{uuid.uuid4().hex[:8]}"
    now = time.time()
    sess = _get_session()
    insert_sql = (
        "INSERT INTO ai_tasks (task_id, user_key, state, progress, created_at, updated_at, generation_quota_weight) "
        "VALUES (:tid, :uk, 'pending', 0, :ca, :ua, :qqw)"
    )
    def _params(task_id_value: str) -> Dict[str, Any]:
        return {"tid": task_id_value, "uk": user_key or "", "ca": now, "ua": now,
                "qqw": generation_quota_weight}
    try:
        from sqlalchemy import text
        sess.execute(text("BEGIN"))
        sess.execute(text(insert_sql), _params(tid))
        sess.commit()
        return tid
    except Exception as e:
        sess.rollback()
        # 极小概率冲突，重试一次
        tid = f"task-{uuid.uuid4().hex[:8]}"
        try:
            sess.execute(text(insert_sql), _params(tid))
            sess.commit()
            return tid
        except Exception:
            sess.rollback()
            raise
    finally:
        sess.close()

def update(task_id: str, **kw: Any) -> None:
    """写入任务字段。

    终态不可逆（F1）：任何携带 state 的写入都由数据库条件更新裁决
    `WHERE ... (state IS NULL OR state NOT IN 终态)`，rowcount==0 即整笔作废。
    否则惰性超时退款后，仍在运行的 Provider 协程可以把 failed 覆写成 completed，
    形成「歌拿到了、钱也退了」的双重收益。
    """
    import json
    if not kw:
        return
    now = time.time()
    sess = _get_session()
    try:
        from sqlalchemy import text
        sess.execute(text("BEGIN"))
        json_columns = {"download", "volume_files", "stems"}
        fields = []
        params: Dict[str, Any] = {}
        for k, v in kw.items():
            if k == "state":
                continue  # state 走下面的条件更新
            if k in json_columns and isinstance(v, (dict, list)):
                fields.append(f"{k} = :{k}")
                params[k] = json.dumps(v)
            else:
                fields.append(f"{k} = :{k}")
                params[k] = v
        params["ua"] = now
        params["tid"] = task_id

        target_state = kw.get("state")
        if target_state is not None:
            guard = sess.execute(text(
                "UPDATE ai_tasks SET state = :st, updated_at = :ua "
                f"WHERE task_id = :tid AND (state IS NULL OR state NOT IN {_TERMINAL_LIST})"
            ), {"st": target_state, "ua": now, "tid": task_id})
            if guard.rowcount == 0:
                # 任务已是终态（或根本不存在）：拒绝任何回写，也不刷新心跳
                sess.rollback()
                logger.warning(
                    "update(%s) ignored: 任务已处于终态，拒绝写入 state=%s", task_id, target_state
                )
                return

        if fields:
            sess.execute(text(
                f"UPDATE ai_tasks SET {', '.join(fields)}, updated_at = :ua WHERE task_id = :tid"
            ), params)
        sess.execute(text("UPDATE task_locks SET updated_at=:ua WHERE task_id=:tid"), {"ua": now, "tid": task_id})
        sess.commit()
    except Exception:
        try:
            sess.rollback()
        except Exception:
            pass
        raise
    finally:
        sess.close()

def try_transition_state(task_id: str, from_states, to_state: str) -> bool:
    """原子状态转换：仅当 task 当前 state 属于 from_states 时才更新为 to_state。

    用数据库条件 UPDATE + rowcount 判定，跨进程/worker 安全（与 reserve_generation
    的并发保证同构，不依赖 threading.Lock）。用于防止并发请求重复启动 GPU：
    同一起点的多个并发请求中，只有第一个能成功把状态从「可重试终态」转换到
    「进行中」，其余 rowcount==0 → 拒绝。

    返回 True 表示本次调用成功抢占状态转换（唯一成功者）。
    """
    from sqlalchemy import text
    if isinstance(from_states, str):
        from_states = (from_states,)
    placeholders = ", ".join(f":fs{i}" for i in range(len(from_states)))
    params = {f"fs{i}": s for i, s in enumerate(from_states)}
    params["tid"] = task_id
    params["to"] = to_state
    params["ua"] = time.time()
    sess = _get_session()
    try:
        sess.execute(text("BEGIN"))
        cur = sess.execute(text(
            f"UPDATE ai_tasks SET state=:to, updated_at=:ua "
            f"WHERE task_id=:tid AND state IN ({placeholders})"
        ), params)
        sess.commit()
        return cur.rowcount == 1
    except Exception:
        try:
            sess.rollback()
        except Exception:
            pass
        raise
    finally:
        sess.close()

def get(task_id: str) -> Optional[Dict[str, Any]]:
    sess = _get_session()
    try:
        from sqlalchemy import text
        sess.execute(text("BEGIN"))
        row = sess.execute(text("SELECT * FROM ai_tasks WHERE task_id=:tid"), {"tid": task_id}).fetchone()
        if row is None:
            sess.rollback()
            return None
        task = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)  # type: ignore
        import json
        for col in ("download", "volume_files", "stems"):
            if task.get(col) and isinstance(task[col], str):
                try:
                    task[col] = json.loads(task[col])
                except Exception:
                    task[col] = None
        # 惰性超时：只标记，不在这里翻状态/删锁（退款必须收敛到
        # task_recovery.finalize_stale_task 这一个出口，否则会出现「判失败但没退款」）
        if task.get("state") in ("pending", "processing", "generating", "separating", "uploading") and time.time() - float(task.get("updated_at") or 0) > TASK_TIMEOUT:
            task["stale_timed_out"] = True
            sess.commit()
            return task
        sess.commit()
        return task
    except Exception:
        try:
            sess.rollback()
        except Exception:
            pass
        raise
    finally:
        sess.close()

def delete(task_id: str) -> None:
    sess = _get_session()
    try:
        from sqlalchemy import text
        sess.execute(text("BEGIN"))
        sess.execute(text("DELETE FROM task_locks WHERE task_id=:tid"), {"tid": task_id})
        sess.execute(text("DELETE FROM ai_tasks WHERE task_id=:tid"), {"tid": task_id})
        sess.commit()
    finally:
        sess.close()

def list_user_tasks(user_key: str) -> list[dict]:
    sess = _get_session()
    try:
        from sqlalchemy import text
        rows = sess.execute(text("SELECT task_id, user_key, state, progress, audio_url, stems_state, created_at, updated_at FROM ai_tasks WHERE user_key=:uk ORDER BY updated_at DESC"), {"uk": user_key}).fetchall()
        out = []
        for row in rows:
            d = row._mapping if hasattr(row, "_mapping") else row
            out.append({"task_id": d["task_id"], "user_key": d["user_key"], "state": d["state"], "progress": d["progress"] or 0, "audio_url": d["audio_url"], "stems_state": d["stems_state"], "created_at": d["created_at"], "updated_at": d["updated_at"]})
        return out
    finally:
        sess.close()

def count_user_tasks(user_key: Optional[str]) -> int:
    """返回某用户的 ai_tasks 总数（SQLAlchemy 直接 COUNT，不加载全部行）。

    供 auth.get_user_stats 等统计端点使用，替代对 ai_tasks 的 PostgREST 读取。
    """
    if not user_key:
        return 0
    sess = _get_session()
    try:
        from sqlalchemy import text
        row = sess.execute(
            text("SELECT COUNT(*) FROM ai_tasks WHERE user_key = :uk"),
            {"uk": user_key},
        ).fetchone()
        return int(row[0]) if row is not None else 0
    finally:
        sess.close()


def is_user_busy(user_key: Optional[str]) -> bool:
    if not user_key:
        return False
    sess = _get_session()
    try:
        from sqlalchemy import text
        row = sess.execute(text("""
            SELECT 1 FROM task_locks tl
            JOIN ai_tasks t ON tl.task_id = t.task_id
            WHERE tl.user_key=:uk
              AND t.state IN ('pending','processing','generating','separating','uploading')
              AND tl.updated_at + 600 > :now
        """), {"uk": user_key, "now": time.time()}).fetchone()
        return row is not None
    finally:
        sess.close()

def acquire_lock(user_key: Optional[str], task_id: str) -> bool:
    """占用用户任务锁。任何情况都不抛异常 —— 失败一律返回 False，由调用方走无副作用分支。

    修复点（P0-3）：
    1. 旧实现是 `INSERT ... SELECT WHERE NOT EXISTS`，而 task_locks.user_key 是主键：
       进程崩溃/部署重启后残留的锁行不会命中 NOT EXISTS 条件，而是直接撞主键
       → IntegrityError 冒到路由层变成 500，此时 Credits 已扣且不会被退回。
    2. 现在先清理该用户的陈旧锁（任务已不存在/已终态/超过 TTL），再用
       `ON CONFLICT DO NOTHING` + rowcount 判定，并把任何数据库异常收敛为 False。
    """
    if not user_key:
        return True
    now = time.time()
    sess = _get_session()
    try:
        from sqlalchemy import text
        sess.execute(text("BEGIN"))
        # 陈旧锁清理：所绑任务已不存在，或已不在活跃状态
        # （不用 DELETE 表别名：SQLite 不支持，PG/SQLite 需同一份 SQL 可跑）
        sess.execute(text("""
            DELETE FROM task_locks
            WHERE user_key = :uk
              AND task_id NOT IN (
                  SELECT task_id FROM ai_tasks
                  WHERE state IN ('pending','processing','generating','separating','uploading')
              )
        """), {"uk": user_key})
        # TTL 过期的锁（即便任务状态还没被惰性刷新）
        sess.execute(text("""
            DELETE FROM task_locks WHERE user_key = :uk AND updated_at + 600 <= :now
        """), {"uk": user_key, "now": now})
        cur = sess.execute(text("""
            INSERT INTO task_locks (user_key, task_id, updated_at)
            VALUES (:uk, :tid, :now)
            ON CONFLICT (user_key) DO NOTHING
        """), {"uk": user_key, "tid": task_id, "now": now})
        if cur.rowcount == 0:
            sess.rollback()
            return False
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

def _release_lock_for_task(task_id: str) -> None:
    sess = _get_session()
    try:
        from sqlalchemy import text
        sess.execute(text("DELETE FROM task_locks WHERE task_id=:tid"), {"tid": task_id})
        sess.commit()
    finally:
        sess.close()

def release_lock_for_task(task_id: str) -> None:
    _release_lock_for_task(task_id)

def log_generation_cost(*, task_id: str, user_key: Optional[str] = None, provider: Optional[str] = None, gpu: Optional[str] = None, result: str = "success", container_duration_ms: int = 0, model_load_ms: Optional[int] = None, generation_ms: Optional[int] = None, cold_warm: Optional[str] = None, container_id: Optional[str] = None, retries: int = 0, estimated_cost_usd: Optional[float] = None) -> None:
    now = time.time()
    sess = _get_session()
    try:
        from sqlalchemy import text
        sess.execute(text("""
            INSERT INTO generation_cost_logs (task_id, user_key, provider, gpu, result, container_duration_ms, model_load_ms, generation_ms, cold_warm, container_id, retries, estimated_cost_usd, created_at, updated_at)
            VALUES (:tid, :uk, :prov, :gpu, :res, :cdm, :mlm, :gm, :cw, :cid, :ret, :cost, :ca, :ua)
        """), {"tid": task_id, "uk": user_key, "prov": provider, "gpu": gpu, "res": result, "cdm": container_duration_ms, "mlm": model_load_ms, "gm": generation_ms, "cw": cold_warm, "cid": container_id, "ret": retries, "cost": estimated_cost_usd if estimated_cost_usd is not None else 0.0, "ca": now, "ua": now})
        sess.commit()
    except Exception:
        try:
            sess.rollback()
        except Exception:
            pass
    finally:
        sess.close()

# 兼容旧接口
def _get_conn():
    import sqlite3
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def _init_tables(conn=None):
    from app.db.database import Base, engine
    Base.metadata.create_all(bind=engine)
