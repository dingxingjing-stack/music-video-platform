"""Workflow endpoints �?extracted from main.py.

Paths A (Suno-style music), B (Hybrid music+TTS), C (Remix stems), D (MIDI render).
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

from fastapi import HTTPException, Request, APIRouter
router = APIRouter()

from app.services.workflow import WorkflowEngine
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
                    ai_limits.refund_generation(user_key)


# ---------------------------------------------------------------------------
# Workflow Path A �?Suno-style music generation
# ---------------------------------------------------------------------------


@router.post("/a", tags=["workflows"])
async def workflow_path_a(request: Request):
    """Path A: Suno-style �?one-click music generation."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    prompt = body.get("prompt", "")
    if not prompt:
        raise HTTPException(status_code=422, detail="'prompt' is required")

    # Extract user_key (same as ai_music)
    x_user_id = request.headers.get("X-User-ID")
    user_key = x_user_id or body.get("user_id") or (request.client.host if request.client else None)
    if not user_key:
        raise HTTPException(status_code=403, detail="Missing user identification")

    # Skip quota check in mock mode
    if os.getenv("WORKFLOW_MODE", "mock").lower() != "mock":
        reserved_result = ai_limits.reserve_generation(user_key)
        if not reserved_result["success"]:
            raise HTTPException(status_code=429, detail=reserved_result["error"])
        reserved = True
    else:
        reserved = False

    task_id = task_store.new_task(user_key=user_key)
    if not task_store.acquire_lock(user_key, task_id):
        task_store.delete(task_id)
        if reserved:
            ai_limits.refund_generation(user_key)
        raise HTTPException(
            status_code=429,
            detail="您有一个生成任务正在进行中，请完成后再试",
        )

    engine = _get_workflow_engine()

    asyncio.create_task(
        _run_workflow_async(
            engine.run_path_a,
            task_id,
            prompt=prompt,
            duration=float(body.get("duration", 10.0)),
            temperature=float(body.get("temperature", 0.8)),
            user_key=user_key,
            reserved=reserved,
        )
    )

    return {
        "task_id": task_id,
        "status": "started",
        "websocket": f"/ws/progress/{task_id}",
        "path": "a",
    }


# ---------------------------------------------------------------------------
# Workflow Path B �?Hybrid music + TTS
# ---------------------------------------------------------------------------


@router.post("/b", tags=["workflows"])
async def workflow_path_b(request: Request):
    """Path B: Hybrid �?MusicGen background + TTS vocals."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    prompt = body.get("prompt", "")
    tts_text = body.get("tts_text", "")
    if not prompt or not tts_text:
        raise HTTPException(
            status_code=422,
            detail="'prompt' and 'tts_text' are required",
        )

    # Extract user_key (same as ai_music)
    x_user_id = request.headers.get("X-User-ID")
    user_key = x_user_id or body.get("user_id") or (request.client.host if request.client else None)
    if not user_key:
        raise HTTPException(status_code=403, detail="Missing user identification")

    # Skip quota check in mock mode
    if os.getenv("WORKFLOW_MODE", "mock").lower() != "mock":
        reserved_result = ai_limits.reserve_generation(user_key)
        if not reserved_result["success"]:
            raise HTTPException(status_code=429, detail=reserved_result["error"])
        reserved = True
    else:
        reserved = False

    task_id = task_store.new_task(user_key=user_key)
    if not task_store.acquire_lock(user_key, task_id):
        task_store.delete(task_id)
        if reserved:
            ai_limits.refund_generation(user_key)
        raise HTTPException(
            status_code=429,
            detail="您有一个生成任务正在进行中，请完成后再试",
        )

    engine = _get_workflow_engine()

    asyncio.create_task(
        _run_workflow_async(
            engine.run_path_b,
            task_id,
            prompt=prompt,
            tts_text=tts_text,
            duration=float(body.get("duration", 10.0)),
            tts_language=body.get("tts_language", "zh"),
            reference_audio_b64=body.get("reference_audio"),
            user_key=user_key,
            reserved=reserved,
        )
    )

    return {
        "task_id": task_id,
        "status": "started",
        "websocket": f"/ws/progress/{task_id}",
        "path": "b",
    }


# ---------------------------------------------------------------------------
# Workflow Path C �?Remix (Demucs stem separation)
# ---------------------------------------------------------------------------


@router.post("/c", tags=["workflows"])
async def workflow_path_c(request: Request):
    """Path C: Remix �?upload audio -> Demucs stem separation."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    audio_b64 = body.get("audio_base64", "")
    if not audio_b64:
        raise HTTPException(
            status_code=422,
            detail="'audio_base64' is required",
        )

    # Extract user_key (same as ai_music)
    x_user_id = request.headers.get("X-User-ID")
    user_key = x_user_id or body.get("user_id") or (request.client.host if request.client else None)
    if not user_key:
        raise HTTPException(status_code=403, detail="Missing user identification")

    # Skip quota check in mock mode
    if os.getenv("WORKFLOW_MODE", "mock").lower() != "mock":
        reserved_result = ai_limits.reserve_generation(user_key)
        if not reserved_result["success"]:
            raise HTTPException(status_code=429, detail=reserved_result["error"])
        reserved = True
    else:
        reserved = False

    task_id = task_store.new_task(user_key=user_key)
    if not task_store.acquire_lock(user_key, task_id):
        task_store.delete(task_id)
        if reserved:
            ai_limits.refund_generation(user_key)
        raise HTTPException(
            status_code=429,
            detail="您有一个生成任务正在进行中，请完成后再试",
        )

    engine = _get_workflow_engine()

    asyncio.create_task(
        _run_workflow_async(
            engine.run_path_c,
            task_id,
            audio_base64=audio_b64,
            stem_count=body.get("stem_count", "4"),
            remove_reverb=bool(body.get("remove_reverb", False)),
            user_key=user_key,
            reserved=reserved,
        )
    )

    return {
        "task_id": task_id,
        "status": "started",
        "websocket": f"/ws/progress/{task_id}",
        "path": "c",
    }


# ---------------------------------------------------------------------------
# Workflow Path D �?MIDI render
# ---------------------------------------------------------------------------


@router.post("/d", tags=["workflows"])
async def workflow_path_d(request: Request):
    """Path D: Original Creation �?MIDI project -> render to audio."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    midi_project = body.get("midi_project")
    if not midi_project:
        raise HTTPException(
            status_code=422,
            detail="'midi_project' is required",
        )

    # Extract user_key (same as ai_music)
    x_user_id = request.headers.get("X-User-ID")
    user_key = x_user_id or body.get("user_id") or (request.client.host if request.client else None)
    if not user_key:
        raise HTTPException(status_code=403, detail="Missing user identification")

    # Skip quota check in mock mode
    if os.getenv("WORKFLOW_MODE", "mock").lower() != "mock":
        reserved_result = ai_limits.reserve_generation(user_key)
        if not reserved_result["success"]:
            raise HTTPException(status_code=429, detail=reserved_result["error"])
        reserved = True
    else:
        reserved = False

    task_id = task_store.new_task(user_key=user_key)
    if not task_store.acquire_lock(user_key, task_id):
        task_store.delete(task_id)
        if reserved:
            ai_limits.refund_generation(user_key)
        raise HTTPException(
            status_code=429,
            detail="您有一个生成任务正在进行中，请完成后再试",
        )

    engine = _get_workflow_engine()

    asyncio.create_task(
        _run_workflow_async(
            engine.run_path_d,
            task_id,
            midi_project=midi_project,
            output_format=body.get("outputFormat", "wav"),
            soundfont_path=body.get("soundfontPath"),
            user_key=user_key,
            reserved=reserved,
        )
    )

    return {
        "task_id": task_id,
        "status": "started",
        "websocket": f"/ws/progress/{task_id}",
        "path": "d",
    }
