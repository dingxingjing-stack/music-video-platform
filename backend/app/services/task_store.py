"""进程内异步任务存储：提交长耗时生成任务后立即返回 task_id，前端轮询状态。

含：
- 每用户任务锁：同一用户（user_key）同时只允许 1 个进行中的生成任务
- 任务超时：超过 TASK_TIMEOUT 秒自动标记 failed 并释放用户锁
"""

import os
import time
import uuid
from typing import Any, Dict, Optional

_TASKS: Dict[str, Dict[str, Any]] = {}
_USER_LOCKS: Dict[str, Dict[str, Any]] = {}   # user_key -> {"task_id", "updated_at"}

TASK_TIMEOUT = float(os.getenv("TASK_TIMEOUT", "180"))  # 秒


def new_task(user_key: Optional[str] = None, task_id: Optional[str] = None) -> str:
    tid = task_id or f"task-{uuid.uuid4().hex[:8]}"
    _TASKS[tid] = {
        "task_id": tid,
        "user_key": user_key,
        "state": "pending",      # pending / processing / completed / failed
        "progress": 0,
        "audio_url": None,
        "video_url": None,
        "ai_provider": None,
        "error": None,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    return tid


def update(task_id: str, **kw: Any) -> None:
    if task_id in _TASKS:
        _TASKS[task_id].update(kw)
        _TASKS[task_id]["updated_at"] = time.time()


def get(task_id: str) -> Optional[Dict[str, Any]]:
    task = _TASKS.get(task_id)
    if task is None:
        return None
    # 惰性超时：进行中任务超过 TASK_TIMEOUT 无更新 → 标记 failed 并释放锁
    if task["state"] in ("pending", "processing") and time.time() - task["updated_at"] > TASK_TIMEOUT:
        task["state"] = "failed"
        task["error"] = "生成超时（超过限制时长），请稍后重试"
        _release_lock_for_task(task_id)
    return task


def delete(task_id: str) -> None:
    _TASKS.pop(task_id, None)


# ═══════════════════════════════════════════════════════════════════════
# 每用户任务锁
# ═══════════════════════════════════════════════════════════════════════
def is_user_busy(user_key: Optional[str]) -> bool:
    """该用户是否已有进行中任务。"""
    if not user_key:
        return False
    holder = _USER_LOCKS.get(user_key)
    if not holder:
        return False
    tid = holder["task_id"]
    task = _TASKS.get(tid) or {}
    state = task.get("state", "pending")
    if task and time.time() - task.get("updated_at", 0) > TASK_TIMEOUT:
        return False
    return state in ("pending", "processing")


def acquire_lock(user_key: Optional[str], task_id: str) -> bool:
    """尝试为用户加锁。若已有进行中任务则返回 False，否则持锁返回 True。"""
    if not user_key:
        return True
    if is_user_busy(user_key):
        return False
    _USER_LOCKS[user_key] = {"task_id": task_id, "updated_at": time.time()}
    return True


def _release_lock_for_task(task_id: str) -> None:
    task = _TASKS.get(task_id) or {}
    uk = task.get("user_key")
    if uk:
        holder = _USER_LOCKS.get(uk)
        if holder and holder["task_id"] == task_id:
            _USER_LOCKS.pop(uk, None)


def release_lock_for_task(task_id: str) -> None:
    _release_lock_for_task(task_id)