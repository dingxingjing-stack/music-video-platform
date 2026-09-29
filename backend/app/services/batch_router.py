"""Batch endpoints – RETIRED (P5-B.9).

原实现是 self-declared `placeholder implementation (stub)`：
  POST /a、POST /b 只做入参校验就返回 status="started" 并给出一个
  永远不会有任何进度的 /ws/progress/<id>；GET /status/<id> 恒返回
  queue=0 / active=0。三端点均无鉴权、无队列、无处理，属假成功。
当前 Melovar 生产不存在批处理链路，故统一改为 410 Gone。
"""

import logging

from fastapi import APIRouter, HTTPException

router = APIRouter()
logger = logging.getLogger(__name__)


def _retired(name: str):
    raise HTTPException(
        status_code=410,
        detail=(
            f"Batch endpoint '{name}' has been retired. "
            "Use POST /api/v1/ai/generate.",
        ),
    )


@router.post("/a", tags=["batch"])
async def batch_path_a():
    """P5-B.9：批处理 stub 已退休（410 Gone）。"""
    _retired("a")


@router.post("/b", tags=["batch"])
async def batch_path_b():
    """P5-B.9：批处理 stub 已退休（410 Gone）。"""
    _retired("b")


@router.get("/status/{task_id}", tags=["batch"])
async def batch_status(task_id: str):
    """P5-B.9：批处理状态 stub 已退休（410 Gone）。"""
    _retired("status")