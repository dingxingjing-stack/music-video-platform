"""MV (Music Video) endpoints – 零成本本地合成。

Routes:
  GET  /api/v1/mv/templates     – static template list
  POST /api/v1/mv/render        – MusicGen 音频 → FFmpeg 图片拼接视频（无付费 API）
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
from app.services.musicgen_client import download_audio, generate_music
from app.services.mv_composer import compose_slideshow_video

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
# In‑memory task cache
# ═══════════════════════════════════════════════════════════════════════
_MV_TASK_CACHE: Dict[str, Dict[str, Any]] = {}

# ═══════════════════════════════════════════════════════════════════════
# Render endpoint
# ═══════════════════════════════════════════════════════════════════════
@router.post("/render")
async def mv_render(request: Request):
    """生成 MV：MusicGen 音频 → FFmpeg 图片拼接视频（零成本，无付费 API，无 mock）。"""
    body = await request.json()
    audio_url = body.get("audio_url", "")

    # ── 生成音乐 via MusicGen (Modal 本地开源模型)，无外部付费 API ──
    if not audio_url:
        prompt = body.get("prompt", "upbeat electronic dance music")
        lyrics = body.get("lyrics", "") or prompt
        style = body.get("style", "pop")
        duration = int(body.get("duration", 30) or 30)
        audio_url = await generate_music(prompt=lyrics or prompt, duration=min(duration, 60))
        if not audio_url:
            raise HTTPException(status_code=502, detail="音乐生成失败：MusicGen 不可用")

    task_id = body.get("source_track_id", f"mv-{uuid.uuid4().hex[:8]}")
    if not task_id.startswith("mv-"):
        task_id = f"mv-{task_id}"

    # 从共享卷读取音频本地路径（供 FFmpeg 合成）
    audio_local = await download_audio(audio_url)
    if not audio_local or not os.path.exists(audio_local):
        logger.warning("MV 音频文件不可用: %s", audio_url)
        raise HTTPException(status_code=502, detail="音频文件不可用")

    # ── FFmpeg 图片拼接简易视频（零成本） ──
    title = body.get("title", "AI Music Video")
    lyric_lines = body.get("lyric_lines") or body.get("lyrics", "").splitlines() or [title, "AI Music Video"]
    lyric_lines = [l for l in lyric_lines if l and not l.strip().startswith("[")] or [title]

    _MV_TASK_CACHE[task_id] = {"state": "processing", "progress": 40, "video_url": None}
    await manager.broadcast(task_id, PredictResult(
        task_id=task_id, status=TaskStatus.RUNNING, progress=40,
        message="FFmpeg 图片拼接中...",
    ))

    fname = await compose_slideshow_video(audio_local, title=title, lyric_lines=lyric_lines)
    if not fname:
        _MV_TASK_CACHE[task_id] = {"state": "failed", "progress": 0, "video_url": None}
        await manager.broadcast(task_id, PredictResult(
            task_id=task_id, status=TaskStatus.FAILED, progress=0,
            message="视频合成失败",
        ))
        raise HTTPException(status_code=500, detail="视频合成失败")

    video_url = f"/generated/{fname}"
    _MV_TASK_CACHE[task_id] = {"state": "completed", "progress": 100, "video_url": video_url}
    await manager.broadcast(task_id, PredictResult(
        task_id=task_id, status=TaskStatus.COMPLETED, progress=100,
        message="MV 生成完成（零成本 FFmpeg 拼接）",
        result_url=video_url,
    ))
    return {"task_id": task_id, "status_url": f"/api/v1/mv/status/{task_id}", "audio_url": audio_url, "video_url": video_url}

# ═══════════════════════════════════════════════════════════════════════
# Status endpoint
# ═══════════════════════════════════════════════════════════════════════
@router.get("/status/{task_id}")
async def get_status(task_id: str):
    return _MV_TASK_CACHE.get(task_id, {"task_id": task_id, "state": "unknown", "progress": 0, "video_url": None})
