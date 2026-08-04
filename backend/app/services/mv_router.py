"""MV (Music Video) endpoints – 零成本本地合成（异步任务架构）。

Routes:
  GET  /api/v1/mv/templates     – static template list
  POST /api/v1/mv/render        – 提交任务：MusicGen 音频 → FFmpeg 图片拼接视频（立即返回 task_id）
  GET  /api/v1/mv/status/{id}   – poll task status；completed 时返回 video_url / audio_url
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.services.inference import PredictResult, TaskStatus  # type: ignore
from app.websocket_manager import manager  # type: ignore
from app.services.musicgen_client import download_audio, generate_music
from app.services.mv_composer import compose_slideshow_video
from app.services import task_store

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
# Render endpoint（异步任务）
# ═══════════════════════════════════════════════════════════════════════
@router.post("/render")
async def mv_render(request: Request):
    """提交 MV 生成任务，立即返回 task_id（后台 MusicGen 音频 → FFmpeg 拼接）。"""
    body = await request.json()
    audio_url = body.get("audio_url", "")

    task_id = f"mv-{uuid.uuid4().hex[:8]}"
    task_store.new_task(task_id)
    asyncio.create_task(_run_mv(task_id, body, audio_url))
    return {
        "task_id": task_id,
        "status_url": f"/api/v1/mv/status/{task_id}",
        "audio_url": audio_url or None,
        "video_url": None,
    }


async def _run_mv(task_id: str, body: Dict[str, Any], audio_url: str):
    """后台执行：生成音频（如缺省）→ 下载到本地 → FFmpeg 合成视频。"""
    try:
        task_store.update(task_id, state="processing", progress=10)

        # ── 生成音乐 via MusicGen (Modal 本地开源模型) ──
        if not audio_url:
            prompt = body.get("prompt", "upbeat electronic dance music")
            lyrics = body.get("lyrics", "") or prompt
            duration = int(body.get("duration", 30) or 30)
            task_store.update(task_id, progress=30, ai_provider="musicgen")
            audio_url = await generate_music(prompt=lyrics or prompt, duration=min(duration, 60))
            if not audio_url:
                task_store.update(task_id, state="failed", error="音乐生成失败：MusicGen 不可用")
                return

        # ── 下载音频到本地（FFmpeg 合成用） ──
        task_store.update(task_id, progress=60)
        audio_local = await download_audio(audio_url)
        if not audio_local or not os.path.exists(audio_local):
            logger.warning("MV 音频文件不可用: %s", audio_url)
            task_store.update(task_id, state="failed", error="音频文件不可用")
            return

        # ── FFmpeg 图片拼接视频 ──
        title = body.get("title", "AI Music Video")
        lyric_lines = body.get("lyric_lines") or body.get("lyrics", "").splitlines() or [title, "AI Music Video"]
        lyric_lines = [l for l in lyric_lines if l and not l.strip().startswith("[")] or [title]

        await manager.broadcast(task_id, PredictResult(
            task_id=task_id, status=TaskStatus.RUNNING, progress=75,
            message="FFmpeg 图片拼接中...",
        ))

        fname = await compose_slideshow_video(audio_local, title=title, lyric_lines=lyric_lines)
        if not fname:
            task_store.update(task_id, state="failed", error="视频合成失败")
            return

        video_url = f"/generated/{fname}"
        task_store.update(
            task_id, state="completed", progress=100,
            audio_url=audio_url, video_url=video_url,
        )
        await manager.broadcast(task_id, PredictResult(
            task_id=task_id, status=TaskStatus.COMPLETED, progress=100,
            message="MV 生成完成（零成本 FFmpeg 拼接）",
            result_url=video_url,
        ))
    except Exception as e:
        import traceback
        logger.error("MV 任务异常: %s", e)
        traceback.print_exc()
        task_store.update(task_id, state="failed", error=f"{type(e).__name__}: {e}")

# ═══════════════════════════════════════════════════════════════════════
# Status endpoint
# ═══════════════════════════════════════════════════════════════════════
@router.get("/status/{task_id}")
async def get_status(task_id: str):
    task = task_store.get(task_id)
    if not task:
        return {"task_id": task_id, "state": "unknown", "progress": 0, "audio_url": None, "video_url": None, "error": None}
    return {
        "task_id": task["task_id"],
        "state": task["state"],
        "progress": task["progress"],
        "audio_url": task.get("audio_url"),
        "video_url": task.get("video_url"),
        "ai_provider": task.get("ai_provider"),
        "error": task.get("error"),
    }
