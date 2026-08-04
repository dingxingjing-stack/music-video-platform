"""进程内异步任务存储：提交长耗时生成任务后立即返回 task_id，前端轮询状态。"""

import time
import uuid
from typing import Any, Dict, Optional

_TASKS: Dict[str, Dict[str, Any]] = {}


def new_task(task_id: Optional[str] = None) -> str:
    tid = task_id or f"task-{uuid.uuid4().hex[:8]}"
    _TASKS[tid] = {
        "task_id": tid,
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
    return _TASKS.get(task_id)
