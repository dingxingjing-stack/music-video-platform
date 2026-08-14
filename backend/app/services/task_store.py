"""SQLite 持久化任务存储：提交长耗时生成任务后立即返回 task_id，前端轮询状态。

含：
- 每用户任务锁：同一用户（user_key）同时只允许 1 个进行中的生成任务
- 任务超时：超过 TASK_TIMEOUT 秒自动标记 failed 并释放用户锁
- 数据存储于 beta.db (WAL 模式)，进程重启/多实例下保持一致
"""

import os
import time
import uuid
import sqlite3
import threading
from typing import Any, Dict, Optional

# 状态机（内部）：pending -> processing(Agnes) -> generating(ACE-Step)
#   -> separating(Demucs，同容器内隐式) -> uploading(R2)
#   -> completed | completed_with_stems_failed | failed | cancelled
# 对外兼容：completed_with_stems_failed 在 TaskResponse 仍映射 "completed"，
# 并额外携带 stems_state + stems 字段，避免破坏现有前端终态判定。
TASK_TIMEOUT = float(os.getenv("TASK_TIMEOUT", "600"))  # 秒（单任务最大 10 分钟）

_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
_DB_PATH = os.path.join(_DB_DIR, "beta.db")
_DB_LOCK = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    """获取数据库连接（复用 beta.db WAL 模式）"""
    os.makedirs(_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _init_tables(conn)
    return conn


def _init_tables(conn: sqlite3.Connection) -> None:
    """初始化任务表与锁表（幂等）"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ai_tasks (
            task_id TEXT PRIMARY KEY,
            user_key TEXT NOT NULL,
            state TEXT DEFAULT 'pending',
            progress INTEGER DEFAULT 0,
            audio_url TEXT,
            video_url TEXT,
            ai_provider TEXT,
            error TEXT,
            download TEXT,                      -- JSON: {"full_mp3": "key", ...}
            volume_files TEXT,                  -- JSON: {"full_wav": "name", ...}
            stems_state TEXT,                   -- ok / failed / skipped
            stems TEXT,                         -- JSON: {"vocals": "url", ...}
            retries INTEGER DEFAULT 0,
            stem_retries INTEGER DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS task_locks (
            user_key TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ai_tasks_user_key ON ai_tasks(user_key);
        CREATE INDEX IF NOT EXISTS idx_ai_tasks_state ON ai_tasks(state);
    """)
    conn.commit()


def new_task(user_key: Optional[str] = None, task_id: Optional[str] = None) -> str:
    """创建新任务，返回 task_id"""
    tid = task_id or f"task-{uuid.uuid4().hex[:8]}"
    now = time.time()
    conn = _get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""
            INSERT INTO ai_tasks (task_id, user_key, state, progress, created_at, updated_at)
            VALUES (?, ?, 'pending', 0, ?, ?)
        """, (tid, user_key or "", now, now))
        conn.commit()
        return tid
    except sqlite3.IntegrityError:
        conn.rollback()
        # 极小概率 UUID 冲突，重试一次
        tid = f"task-{uuid.uuid4().hex[:8]}"
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""
            INSERT INTO ai_tasks (task_id, user_key, state, progress, created_at, updated_at)
            VALUES (?, ?, 'pending', 0, ?, ?)
        """, (tid, user_key or "", now, now))
        conn.commit()
        return tid
    finally:
        conn.close()


def update(task_id: str, **kw: Any) -> None:
    """更新任务字段，同时刷新 task_locks.updated_at（同事务）"""
    import json
    if not kw:
        return
    now = time.time()
    conn = _get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        # 1. 更新 ai_tasks - JSON serialize dict values for JSON columns
        json_columns = {"download", "volume_files", "stems"}
        fields = []
        params = []
        for k, v in kw.items():
            fields.append(f"{k} = ?")
            if k in json_columns and isinstance(v, (dict, list)):
                params.append(json.dumps(v))
            else:
                params.append(v)
        fields.append("updated_at = ?")
        params.append(now)
        params.append(task_id)
        conn.execute(f"UPDATE ai_tasks SET {', '.join(fields)} WHERE task_id = ?", params)
        # 2. 同事务刷新 task_locks（若存在且匹配）
        conn.execute("""
            UPDATE task_locks SET updated_at = ? WHERE task_id = ?
        """, (now, task_id))
        conn.commit()
    finally:
        conn.close()


def get(task_id: str) -> Optional[Dict[str, Any]]:
    """获取任务；进行中任务超过 TASK_TIMEOUT 无更新 → 标记 failed 并释放锁（同事务）"""
    import json
    conn = _get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM ai_tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        task = dict(row)
        # 解析 JSON 列
        for col in ("download", "volume_files", "stems"):
            if task.get(col) and isinstance(task[col], str):
                try:
                    task[col] = json.loads(task[col])
                except json.JSONDecodeError:
                    task[col] = None
        # 惰性超时检查
        if task["state"] in ("pending", "processing", "generating", "separating", "uploading") \
           and time.time() - task["updated_at"] > TASK_TIMEOUT:
            # 原子：标记 failed + 删除 lock + 更新 updated_at
            conn.execute("""
                UPDATE ai_tasks SET state='failed', error=?, updated_at=? WHERE task_id=?
            """, ("生成超时（超过限制时长），请稍后重试", time.time(), task_id))
            conn.execute("DELETE FROM task_locks WHERE task_id = ?", (task_id,))
            conn.commit()
            task["state"] = "failed"
            task["error"] = "生成超时（超过限制时长），请稍后重试"
        return task
    finally:
        conn.close()


def delete(task_id: str) -> None:
    """删除任务及对应锁"""
    conn = _get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM task_locks WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM ai_tasks WHERE task_id = ?", (task_id,))
        conn.commit()
    finally:
        conn.close()


# ════════════════════════════════════════════════════════════════════════
# 每用户任务锁
# ════════════════════════════════════════════════════════════════════════

def is_user_busy(user_key: Optional[str]) -> bool:
    """该用户是否已有进行中任务"""
    if not user_key:
        return False
    conn = _get_conn()
    try:
        row = conn.execute("""
            SELECT 1 FROM task_locks tl
            JOIN ai_tasks t ON tl.task_id = t.task_id
            WHERE tl.user_key = ?
              AND t.state IN ('pending','processing','generating','separating','uploading')
              AND tl.updated_at + 600 > ?
        """, (user_key, time.time())).fetchone()
        return row is not None
    finally:
        conn.close()


def acquire_lock(user_key: Optional[str], task_id: str) -> bool:
    """尝试为用户加锁。若已有进行中任务则返回 False，否则持锁返回 True"""
    if not user_key:
        return True
    conn = _get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        # 原子检查并插入锁：仅当用户无进行中任务时成功
        cur = conn.execute("""
            INSERT INTO task_locks (user_key, task_id, updated_at)
            SELECT ?, ?, ?
            WHERE NOT EXISTS (
                SELECT 1 FROM task_locks tl
                JOIN ai_tasks t ON tl.task_id = t.task_id
                WHERE tl.user_key = ?
                  AND t.state IN ('pending','processing','generating','separating','uploading')
                  AND tl.updated_at + 600 > ?
            )
        """, (user_key, task_id, time.time(), user_key, time.time()))
        if cur.rowcount == 0:
            conn.rollback()
            return False
        conn.commit()
        return True
    finally:
        conn.close()


def _release_lock_for_task(task_id: str) -> None:
    conn = _get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM task_locks WHERE task_id = ?", (task_id,))
        conn.commit()
    finally:
        conn.close()


def release_lock_for_task(task_id: str) -> None:
    _release_lock_for_task(task_id)