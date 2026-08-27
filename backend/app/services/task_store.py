"""任务存储 — Step 2 PostgreSQL 迁移版。

统一通过 app.db.database（DATABASE_URL）访问。
生产：Supabase PostgreSQL；开发/测试：SQLite 自动回退。
所有表由 database.Base 统一建表，create_all 幂等。

多实例锁：PG/SQLite 均通过 DB 条件 INSERT + 事务保证，原进程内 dict 已移除。
"""

import os
import time
import uuid
import threading
from typing import Any, Dict, Optional

TASK_TIMEOUT = float(os.getenv("TASK_TIMEOUT", "600"))

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
    from app.db.database import SessionLocal, Base, engine
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        pass
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

def new_task(user_key: Optional[str] = None, task_id: Optional[str] = None) -> str:
    tid = task_id or f"task-{uuid.uuid4().hex[:8]}"
    now = time.time()
    sess = _get_session()
    try:
        from sqlalchemy import text
        sess.execute(text("BEGIN"))
        sess.execute(text("INSERT INTO ai_tasks (task_id, user_key, state, progress, created_at, updated_at) VALUES (:tid, :uk, 'pending', 0, :ca, :ua)"), {"tid": tid, "uk": user_key or "", "ca": now, "ua": now})
        sess.commit()
        return tid
    except Exception as e:
        sess.rollback()
        # 极小概率冲突，重试一次
        tid = f"task-{uuid.uuid4().hex[:8]}"
        try:
            sess.execute(text("INSERT INTO ai_tasks (task_id, user_key, state, progress, created_at, updated_at) VALUES (:tid, :uk, 'pending', 0, :ca, :ua)"), {"tid": tid, "uk": user_key or "", "ca": now, "ua": now})
            sess.commit()
            return tid
        except Exception:
            sess.rollback()
            raise
    finally:
        sess.close()

def update(task_id: str, **kw: Any) -> None:
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
            if k in json_columns and isinstance(v, (dict, list)):
                fields.append(f"{k} = :{k}")
                params[k] = json.dumps(v)
            else:
                fields.append(f"{k} = :{k}")
                params[k] = v
        fields.append("updated_at = :ua")
        params["ua"] = now
        params["tid"] = task_id
        sess.execute(text(f"UPDATE ai_tasks SET {', '.join(fields)} WHERE task_id = :tid"), params)
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
        # 惰性超时
        if task.get("state") in ("pending", "processing", "generating", "separating", "uploading") and time.time() - float(task.get("updated_at") or 0) > TASK_TIMEOUT:
            sess.execute(text("UPDATE ai_tasks SET state='failed', error=:err, updated_at=:ua WHERE task_id=:tid"), {"err": "生成超时（超过限制时长），请稍后重试", "ua": time.time(), "tid": task_id})
            sess.execute(text("DELETE FROM task_locks WHERE task_id=:tid"), {"tid": task_id})
            sess.commit()
            task["state"] = "failed"
            task["error"] = "生成超时（超过限制时长），请稍后重试"
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
    if not user_key:
        return True
    sess = _get_session()
    try:
        from sqlalchemy import text
        sess.execute(text("BEGIN"))
        cur = sess.execute(text("""
            INSERT INTO task_locks (user_key, task_id, updated_at)
            SELECT :uk, :tid, :now
            WHERE NOT EXISTS (
                SELECT 1 FROM task_locks tl
                JOIN ai_tasks t ON tl.task_id = t.task_id
                WHERE tl.user_key=:uk2
                  AND t.state IN ('pending','processing','generating','separating','uploading')
                  AND tl.updated_at + 600 > :now2
            )
        """), {"uk": user_key, "tid": task_id, "now": time.time(), "uk2": user_key, "now2": time.time()})
        if cur.rowcount == 0:
            sess.rollback()
            return False
        sess.commit()
        return True
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
