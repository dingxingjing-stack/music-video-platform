"""Workflow endpoints — extracted from main.py.

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
    """Helper: run a workflow coroutine in background and catch exceptions."""
    logger.info("Workflow task starting: %s(%s, %s)", coroutine_fn.__name__, args, kwargs)
    try:
        await coroutine_fn(*args, **kwargs)
        logger.info("Workflow task completed: %s", coroutine_fn.__name__)
    except Exception as e:
        logger.exception("Workflow task failed: %s", e)


# ---------------------------------------------------------------------------
# Workflow Path A — Suno-style music generation
# ---------------------------------------------------------------------------


@router.post("/workflow/a", tags=["workflows"])
async def workflow_path_a(request: Request):
    """Path A: Suno-style — one-click music generation."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    task_id = body.get("task_id") or str(__import__('uuid').uuid4())[:8]
    prompt = body.get("prompt", "")
    if not prompt:
        raise HTTPException(status_code=422, detail="'prompt' is required")

    engine = _get_workflow_engine()

    asyncio.create_task(
        _run_workflow_async(
            engine.run_path_a,
            task_id,
            prompt=prompt,
            duration=float(body.get("duration", 10.0)),
            temperature=float(body.get("temperature", 0.8)),
        )
    )

    return {
        "task_id": task_id,
        "status": "started",
        "websocket": f"/ws/progress/{task_id}",
        "path": "a",
    }


# ---------------------------------------------------------------------------
# Workflow Path B — Hybrid music + TTS
# ---------------------------------------------------------------------------


@router.post("/workflow/b", tags=["workflows"])
async def workflow_path_b(request: Request):
    """Path B: Hybrid — MusicGen background + TTS vocals."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    task_id = body.get("task_id") or str(__import__('uuid').uuid4())[:8]
    prompt = body.get("prompt", "")
    tts_text = body.get("tts_text", "")
    if not prompt or not tts_text:
        raise HTTPException(
            status_code=422,
            detail="'prompt' and 'tts_text' are required",
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
        )
    )

    return {
        "task_id": task_id,
        "status": "started",
        "websocket": f"/ws/progress/{task_id}",
        "path": "b",
    }


# ---------------------------------------------------------------------------
# Workflow Path C — Remix (Demucs stem separation)
# ---------------------------------------------------------------------------


@router.post("/workflow/c", tags=["workflows"])
async def workflow_path_c(request: Request):
    """Path C: Remix — upload audio -> Demucs stem separation."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    task_id = body.get("task_id") or str(__import__('uuid').uuid4())[:8]
    audio_b64 = body.get("audio_base64", "")
    if not audio_b64:
        raise HTTPException(
            status_code=422,
            detail="'audio_base64' is required",
        )

    engine = _get_workflow_engine()

    asyncio.create_task(
        _run_workflow_async(
            engine.run_path_c,
            task_id,
            audio_base64=audio_b64,
            stem_count=body.get("stem_count", "4"),
            remove_reverb=bool(body.get("remove_reverb", False)),
        )
    )

    return {
        "task_id": task_id,
        "status": "started",
        "websocket": f"/ws/progress/{task_id}",
        "path": "c",
    }


# ---------------------------------------------------------------------------
# Workflow Path D — MIDI render
# ---------------------------------------------------------------------------


@router.post("/workflow/d", tags=["workflows"])
async def workflow_path_d(request: Request):
    """Path D: Original Creation — MIDI project -> render to audio."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    task_id = body.get("task_id") or str(__import__('uuid').uuid4())[:8]
    midi_project = body.get("midi_project")
    if not midi_project:
        raise HTTPException(
            status_code=422,
            detail="'midi_project' is required",
        )

    engine = _get_workflow_engine()

    asyncio.create_task(
        _run_workflow_async(
            engine.run_path_d,
            task_id,
            midi_project=midi_project,
            output_format=body.get("outputFormat", "wav"),
            soundfont_path=body.get("soundfontPath"),
        )
    )

    return {
        "task_id": task_id,
        "status": "started",
        "websocket": f"/ws/progress/{task_id}",
        "path": "d",
    }
