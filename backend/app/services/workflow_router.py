"""Workflow endpoints �?extracted from main.py.

Paths A (Suno-style music), B (Hybrid music+TTS), C (Remix stems), D (MIDI render).
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

from fastapi import HTTPException, Request, APIRouter, Depends
router = APIRouter()

from app.services.workflow import WorkflowEngine
from app.services.auth_identity import get_verified_user_id
from . import ai_limits
from . import task_store

logger = logging.getLogger(__name__)

# Globals set by main.py before mounting
_bcast = None  # _websocket_broadcast
_config = {}   # service configs
_WORKFLOW_ENGINE: Optional[WorkflowEngine] = None


def _get_workflow_engine() -> WorkflowEngine:
    global _WORKFLOW_ENGINE
    if _WORKFLOW_ENGINE is None:
        soundfont = os.getenv("MIDI_SOUNDFONT_PATH")
        _WORKFLOW_ENGINE = WorkflowEngine(
            broadcast=_bcast,
            musicgen_url=_config.get("music", {}).get("space_url"),
            tts_url=_config.get("tts", {}).get("space_url"),
            demucs_url=_config.get("demucs", {}).get("space_url"),
            musicgen_token=_config.get("music", {}).get("api_token"),
            tts_token=_config.get("tts", {}).get("api_token"),
            demucs_token=_config.get("demucs", {}).get("api_token"),
            use_mock=(os.getenv("WORKFLOW_MODE", "mock").lower() == "mock"),
            soundfont_path=soundfont,
        )
    return _WORKFLOW_ENGINE


async def _run_workflow_async(coroutine_fn, *args, **kwargs) -> None:
    """Helper: run a workflow coroutine in background, handle exceptions, and refund quota on failure."""
    user_key = kwargs.pop("user_key", None)
    reserved = kwargs.pop("reserved", False)
    duration = kwargs.pop("duration", None)
    logger.info("Workflow task starting: %s(%s, %s)", coroutine_fn.__name__, args, kwargs)
    try:
        await coroutine_fn(*args, **kwargs)
        logger.info("Workflow task completed: %s", coroutine_fn.__name__)
    except Exception as e:
        logger.exception("Workflow task failed: %s", e)
        if user_key is not None and reserved:
            task_id = args[0] if args else None
            if task_id:
                task_store.update(task_id, state="failed", error=str(e))
    finally:
        # If we reserved quota and the task ended in a failed state, refund the user's daily/monthly quota.
        if reserved and user_key is not None:
            # Extract task_id from args (first positional argument is task_id)
            task_id = args[0] if args else None
            if task_id:
                task = task_store.get(task_id)
                if task and task.get("state") == "failed":
                    ai_limits.refund_generation(user_key, duration, reason="provider_failed", task_id=task_id)


# ---------------------------------------------------------------------------
# Workflow Path A �?Suno-style music generation
# ---------------------------------------------------------------------------


@router.post("/a", tags=["workflows"])
async def workflow_path_a():
    """P5-B.8：Workflow Path A 已退休（410 Gone）。

    原链路 prompt -> MusicGen (HF Space)，依赖已退出 Melovar 当前架构的 Hugging Face Space 后端；
    其所需的 MUSICGEN_SPACE_URL / GPT_SOVITS_SPACE_URL / DEMUCS_SPACE_URL
    在 backend/.env.example 中根本不存在，端点过去只会"先返回 started、
    再在后台断言失败"。真实生歌请用 POST /api/v1/ai/generate（Yinchao -> TemPolor）。
    """
    raise HTTPException(
        status_code=410,
        detail=(
            "Workflow path 'a' has been retired. "
            "Use POST /api/v1/ai/generate.",
        ),
    )




@router.post("/b", tags=["workflows"])
async def workflow_path_b():
    """P5-B.8：Workflow Path B 已退休（410 Gone）。

    原链路 MusicGen + GPT-SoVITS TTS (HF Space)，依赖已退出 Melovar 当前架构的 Hugging Face Space 后端；
    其所需的 MUSICGEN_SPACE_URL / GPT_SOVITS_SPACE_URL / DEMUCS_SPACE_URL
    在 backend/.env.example 中根本不存在，端点过去只会"先返回 started、
    再在后台断言失败"。真实生歌请用 POST /api/v1/ai/generate（Yinchao -> TemPolor）。
    """
    raise HTTPException(
        status_code=410,
        detail=(
            "Workflow path 'b' has been retired. "
            "Use POST /api/v1/ai/generate.",
        ),
    )




@router.post("/c", tags=["workflows"])
async def workflow_path_c():
    """P5-B.8：Workflow Path C 已退休（410 Gone）。

    原链路 MusicGen + Demucs remix stems (HF Space)，依赖已退出 Melovar 当前架构的 Hugging Face Space 后端；
    其所需的 MUSICGEN_SPACE_URL / GPT_SOVITS_SPACE_URL / DEMUCS_SPACE_URL
    在 backend/.env.example 中根本不存在，端点过去只会"先返回 started、
    再在后台断言失败"。真实生歌请用 POST /api/v1/ai/generate（Yinchao -> TemPolor）。
    """
    raise HTTPException(
        status_code=410,
        detail=(
            "Workflow path 'c' has been retired. "
            "Use POST /api/v1/ai/generate.",
        ),
    )




@router.post("/d", tags=["workflows"])
async def workflow_path_d():
    """P5-B.8：Workflow Path D 已退休（410 Gone）。

    原链路 MIDI render workflow，依赖已退出 Melovar 当前架构的 Hugging Face Space 后端；
    其所需的 MUSICGEN_SPACE_URL / GPT_SOVITS_SPACE_URL / DEMUCS_SPACE_URL
    在 backend/.env.example 中根本不存在，端点过去只会"先返回 started、
    再在后台断言失败"。真实生歌请用 POST /api/v1/ai/generate（Yinchao -> TemPolor）。
    """
    raise HTTPException(
        status_code=410,
        detail=(
            "Workflow path 'd' has been retired. "
            "Use POST /api/v1/ai/generate.",
        ),
    )
