"""MV (Music Video) endpoints – with NVAPI/Gemini/Creatomate fallback.

Routes:
  GET  /api/v1/mv/templates     – static template list
  POST /api/v1/mv/render        – generate music (NVAPI) → Creatomate video render
  GET  /api/v1/mv/status/{id}   – poll task status
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.services.inference import PredictResult, TaskStatus  # type: ignore
from app.websocket_manager import manager  # type: ignore

logger = logging.getLogger(__name__)

router = APIRouter()

# ═══════════════════════════════════════════════════════════════════════
# Static template list
# ═══════════════════════════════════════════════════════════════════════
class TemplateInfo(BaseModel):
    id: str
    name: str
    thumbnail: str
    duration_sec: int
    license: str

_STATIC_TEMPLATES: List[TemplateInfo] = [
    TemplateInfo(id="tmpl_001", name="Epic Trailer",     thumbnail="https://example.com/thumbs/epic_trailer.jpg", duration_sec=30, license="premium"),
    TemplateInfo(id="tmpl_002", name="Minimalist Promo", thumbnail="https://example.com/thumbs/minimalist.jpg",   duration_sec=20, license="free"),
    TemplateInfo(id="tmpl_003", name="Retro 80s",       thumbnail="https://example.com/thumbs/retro80.jpg",      duration_sec=25, license="free"),
    TemplateInfo(id="tmpl_004", name="Cinematic Story",  thumbnail="https://example.com/thumbs/cinematic.jpg",    duration_sec=45, license="premium"),
    TemplateInfo(id="tmpl_005", name="Animated Sketch",  thumbnail="https://example.com/thumbs/sketch.jpg",       duration_sec=30, license="free"),
]

@router.get("/templates", response_model=List[TemplateInfo])
async def list_templates() -> List[TemplateInfo]:
    return _STATIC_TEMPLATES

# ═══════════════════════════════════════════════════════════════════════
# Configuration helpers
# ═══════════════════════════════════════════════════════════════════════
def _is_real_key(value: str | None) -> bool:
    """Return True only when value looks like a real API token."""
    if not value:
        return False
    stripped = value.strip()
    if len(stripped) < 16 or stripped.startswith("***"):
        return False
    for p in ("***", "YOUR_", "your_", "redacted", "[REDACTED]", "placeholder"):
        if stripped.startswith(p):
            return False
    return True

NVAPI_BASE_URL   = os.getenv("NVAPI_BASE_URL",   "https://api.nvidia.com/v1")
NVAPI_API_KEY    = os.getenv("NVAPI_API_KEY")
GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY")
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1")

# Mureka configuration
MUREKA_API_KEY = os.getenv("MUREKA_API_KEY")
MUREKA_MODEL = os.getenv("MUREKA_MODEL", "v9")
MUREKA_BASE_URL = os.getenv("MUREKA_BASE_URL", "https://api.mureka.ai/v1")

# Creatomate configuration
CREATOMATE_API_KEY = os.getenv("CREATOMATE_API_KEY")
CREATOMATE_BASE_URL = os.getenv("CREATOMATE_BASE_URL", "https://api.creatomate.com/v2")
CREATOMATE_TEMPLATE_ID = os.getenv("CREATOMATE_TEMPLATE_ID", "ad45bcc0-11c0-4a85-bbd0-27f721bde32e")

NVAPI_KEY_VALID   = _is_real_key(NVAPI_API_KEY)
MUREKA_KEY_VALID  = _is_real_key(MUREKA_API_KEY)
CREATOMATE_KEY_VALID = _is_real_key(CREATOMATE_API_KEY)
GEMINI_KEY_VALID  = _is_real_key(GEMINI_API_KEY)

# ═══════════════════════════════════════════════════════════════════════
# Mureka music generation (primary) with NVAPI fallback
# ═══════════════════════════════════════════════════════════════════════
_PLACEHOLDER_AUDIO = "https://example.com/dummy_music.mp3"

async def mureka_generate_music(
    prompt: str,
    duration: int = 30,
    style: str = "pop",
    lyrics: str = "",
) -> Dict[str, Any]:
    """Generate music via Mureka API. Falls back to NVAPI, then placeholder."""
    if MUREKA_KEY_VALID:
        return await _mureka_call(prompt, duration, style, lyrics)
    if NVAPI_KEY_VALID:
        return await nvapi_generate_music(prompt, duration)
    logger.warning("No valid music API key — using placeholder audio")
    return {"audio_url": _PLACEHOLDER_AUDIO}


async def _mureka_call(prompt: str, duration: int, style: str, lyrics: str) -> Dict[str, Any]:
    """Call Mureka song/generate endpoint.
    
    Required fields: lyrics (non-empty), style
    Optional: duration
    NOTE: Mureka does NOT accept 'model' or 'prompt' fields.
    """
    url = f"{MUREKA_BASE_URL}/song/generate"
    headers = {"Authorization": f"Bearer {MUREKA_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "lyrics": lyrics or prompt,
        "style": style,
    }
    if duration:
        payload["duration"] = duration
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            err = resp.text[:300]
            if "quota" in err.lower() or "429" in err:
                logger.warning("Mureka quota exceeded — using placeholder audio")
            else:
                logger.error("Mureka error %s: %s", resp.status_code, err)
            return {"audio_url": _PLACEHOLDER_AUDIO}
        data = resp.json()
        audio_url = (
            data.get("audio_url")
            or data.get("output_url")
            or data.get("url")
            or data.get("result", {}).get("audio_url")
            or data.get("data", {}).get("audio_url")
        )
        return {"audio_url": audio_url or _PLACEHOLDER_AUDIO, "raw": data}
    except Exception as exc:
        logger.exception("Mureka request failed: %s", exc)
        return {"audio_url": _PLACEHOLDER_AUDIO}

# ═══════════════════════════════════════════════════════════════════════
# Creatomate helpers
# ═══════════════════════════════════════════════════════════════════════
async def creatomate_create_render(audio_url: str, modifications: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Create a Creatomate render job. Returns {render_id, status_url}."""
    if not CREATOMATE_KEY_VALID:
        raise HTTPException(status_code=500, detail="Creatomate API key not configured")
    
    headers = {
        "Authorization": f"Bearer {CREATOMATE_API_KEY}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "template_id": CREATOMATE_TEMPLATE_ID,
        "modifications": {
            "Video.source": audio_url,
            **(modifications or {}),
        },
    }
    
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{CREATOMATE_BASE_URL}/renders",
            json=payload,
            headers=headers,
        )
    if resp.status_code not in (200, 201, 202):
        logger.error("Creatomate create error %s: %s", resp.status_code, resp.text)
        raise HTTPException(status_code=502, detail="Failed to create Creatomate render")
    data = resp.json()
    return {
        "render_id": data.get("id"),
        "status_url": data.get("status_url"),
    }


async def creatomate_check_status(render_id: str) -> Dict[str, Any]:
    """Check Creatomate render status. Returns {state, progress, video_url}."""
    if not CREATOMATE_KEY_VALID:
        raise HTTPException(status_code=500, detail="Creatomate API key not configured")
    
    headers = {"Authorization": f"Bearer {CREATOMATE_API_KEY}"}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{CREATOMATE_BASE_URL}/renders/{render_id}", headers=headers)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to query Creatomate status")
    
    data = resp.json()
    status = data.get("status", "failed")
    mapping = {
        "created": "queued",
        "processing": "processing",
        "completed": "completed",
        "failed": "failed",
    }
    return {
        "state": mapping.get(status, "failed"),
        "progress": int(data.get("progress", 0)),
        "video_url": data.get("download_url"),
    }

# ═══════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════
# In‑memory task cache & Creatomate polling
# ═══════════════════════════════════════════════════════════════════════
_MV_TASK_CACHE: Dict[str, Dict[str, Any]] = {}

async def _poll_creatomate(task_id: str, render_id: str, interval: int = 30):
    while True:
        try:
            status = await creatomate_check_status(render_id)
            _MV_TASK_CACHE[task_id] = status
            await manager.broadcast(task_id, PredictResult(
                task_id=task_id,
                status=TaskStatus.RUNNING if status["state"] != "completed" else TaskStatus.COMPLETED,
                progress=status["progress"],
                message=f"Creatomate rendering: {status['state']}",
                result_url=status.get("video_url"),
            ))
            if status["state"] in ("completed", "failed"):
                break
        except Exception as exc:
            logger.exception("Polling Creatomate failed for %s", task_id)
            await manager.broadcast(task_id, PredictResult(
                task_id=task_id, status=TaskStatus.FAILED, progress=0,
                message=str(exc)[:200],
            ))
            break
        await asyncio.sleep(interval)

# ═══════════════════════════════════════════════════════════════════════
# Render endpoint
# ═══════════════════════════════════════════════════════════════════════
@router.post("/render")
async def mv_render(request: Request):
    """Create MV rendering job. Falls back to audio-only when no InVideo key."""
    body = await request.json()
    audio_url = body.get("audio_url", "")

    # ── Generate music via Mureka if no audio_url provided ──
    if not audio_url:
        prompt = body.get("prompt", "upbeat electronic dance music")
        lyrics = body.get("lyrics", "")
        style = body.get("style", "pop")
        music_res = await mureka_generate_music(prompt, duration=30, style=style, lyrics=lyrics)
        audio_url = music_res.get("audio_url") or _PLACEHOLDER_AUDIO

    task_id = body.get("source_track_id", f"mv-{uuid.uuid4().hex[:8]}")
    if not task_id.startswith("mv-"):
        task_id = f"mv-{task_id}"
    template_id = body.get("template_id", _STATIC_TEMPLATES[0].id)

    # ── If Creatomate key is not valid → audio-only fallback ──
    if not CREATOMATE_KEY_VALID:
        _MV_TASK_CACHE[task_id] = {"state": "completed", "progress": 100, "video_url": audio_url}
        await manager.broadcast(task_id, PredictResult(
            task_id=task_id, status=TaskStatus.COMPLETED, progress=100,
            message="NVAPI music generated — no Creatomate step (fallback).",
            result_url=audio_url,
        ))
        return {"task_id": task_id, "status_url": f"/api/v1/mv/status/{task_id}", "audio_url": audio_url}

    # ── Full Creatomate render path ──
    mods = body.get("modifications", {})
    creatomate_resp = await creatomate_create_render(audio_url, mods)
    render_id = creatomate_resp.get("render_id")
    if not render_id:
        raise HTTPException(status_code=502, detail="Creatomate did not return a render ID")

    _MV_TASK_CACHE[task_id] = {"state": "queued", "progress": 0, "video_url": None}
    await manager.broadcast(task_id, PredictResult(
        task_id=task_id, status=TaskStatus.PENDING, progress=0,
        message="Creatomate render created, waiting for processing...",
    ))
    asyncio.create_task(_poll_creatomate(task_id, render_id))
    return {"task_id": task_id, "status_url": f"/api/v1/mv/status/{task_id}"}

# ═══════════════════════════════════════════════════════════════════════
# Status endpoint
# ═══════════════════════════════════════════════════════════════════════
@router.get("/status/{task_id}")
async def get_status(task_id: str):
    return _MV_TASK_CACHE.get(task_id, {"task_id": task_id, "state": "unknown", "progress": 0, "video_url": None})

# ---------------------------------------------------------------------------
# Gemini text generation endpoint (optional)
# ---------------------------------------------------------------------------
@router.post("/gemini/generate")
async def gemini_generate(request: Request):
    """Generate text via Gemini API.
    Expected JSON body: {"prompt": "your prompt text"}
    """
    if not GEMINI_KEY_VALID:
        raise HTTPException(status_code=500, detail="Gemini API key not configured")
    body = await request.json()
    prompt = body.get("prompt", "")
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    endpoint = f"{GEMINI_BASE_URL}/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(endpoint, json=payload)
    if resp.status_code != 200:
        logger.error("Gemini error %s: %s", resp.status_code, resp.text)
        raise HTTPException(status_code=502, detail="Gemini generation failed")
    return resp.json()
