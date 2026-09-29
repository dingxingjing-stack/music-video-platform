"""
分轨导出路由 (Stems Export Router) — RETIRED (P5-B.10)

P5-A 实测：
  POST /api/v1/export/stems  — service 层已有 production 门禁，返回
    success=False 后被路由翻成 HTTP 500（状态码语义错误）。
  GET  /api/v1/export/stems/{track_id} — 对任意 track_id 恒返回
    status=completed / "分轨已就绪"，且**没有** production 门禁，是生产
    可见的假成功（docstring 自陈 TODO 异步任务队列从未实现）。
两端口统一 410 Gone。真实分轨重试仍走
  POST /api/v1/ai/task/{task_id}/retry-stems（本文件未触碰）。
"""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/export", tags=["分轨导出"])


def _retired(name: str):
    raise HTTPException(
        status_code=410,
        detail=(
            f"Stem export '{name}' has been retired (no real stem provider). "
            "Use POST /api/v1/ai/task/{task_id}/retry-stems for an existing task.",
        ),
    )


@router.post("/stems")
async def export_stems():
    """P5-B.10.2：已退休（410 Gone）。"""
    _retired("POST /api/v1/export/stems")


@router.get("/stems/{track_id}")
async def get_stems_status(track_id: str):
    """P5-B.10.1：已退休（410 Gone，原先对任意 track_id 恒报 completed）。"""
    _retired("GET /api/v1/export/stems/{track_id}")