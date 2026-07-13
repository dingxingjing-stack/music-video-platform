"""
Audio Router — Stem export + AI lyrics completion endpoints.

POST /api/v1/audio/stems   — Split audio into stems (vocals/drums/bass/other) → ZIP
POST /api/v1/audio/lyrics  — AI lyrics completion via LLM streaming
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import tempfile
import zipfile
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Models ──────────────────────────────────────────────────────────────────

class StemExportRequest(BaseModel):
    audio_url: str
    track_name: str = "track"


class LyricsCompletionRequest(BaseModel):
    prompt: str
    style: str = "流行"
    language: str = "中文"
    max_tokens: int = 500


# ── Stem Export ──────────────────────────────────────────────────────────────

def _is_ffmpeg_available() -> bool:
    import subprocess
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


async def _split_stems_ffmpeg(audio_path: str, output_dir: str) -> dict[str, str]:
    """
    Split audio into 4 stems using ffmpeg channel filters as a simple fallback.
    Real implementation would use Demucs or Spleeper via Python.
    """
    stems = {}
    # Simple approach: use ffmpeg to extract frequency bands as pseudo-stems
    band_configs = {
        "vocals":   ["-af", "highpass=f=300,lowpass=f=4000"],
        "drums":    ["-af", "lowpass=f=250"],
        "bass":     ["-af", "lowpass=f=120"],
        "melody":   ["-af", "highpass=f=500"],
    }

    for name, af_args in band_configs.items():
        out_path = os.path.join(output_dir, f"{name}.wav")
        cmd = [
            "ffmpeg", "-y", "-i", audio_path,
            *af_args,
            "-c:a", "pcm_s16le",
            out_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode == 0 and os.path.exists(out_path):
            stems[name] = out_path
        else:
            logger.warning("Stem %s extraction failed: %s", name, stderr.decode()[:200])

    return stems


@router.post("/stems")
async def export_stems(req: StemExportRequest):
    """
    Split audio into stems and return ZIP.
    Falls back to a mock ZIP with the original audio if ffmpeg unavailable.
    """
    if not _is_ffmpeg_available():
        logger.warning("ffmpeg not available — returning mock ZIP")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("README.txt", "Stem export requires ffmpeg. Install ffmpeg to enable full stem separation.")
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{req.track_name}_stems.zip"'},
        )

    # Download audio to temp
    tmp_dir = tempfile.mkdtemp(prefix="stems_")
    audio_path = os.path.join(tmp_dir, "input.wav")

    if req.audio_url.startswith(("http://", "https://")):
        async with httpx.AsyncClient() as client:
            resp = await client.get(req.audio_url)
            with open(audio_path, "wb") as f:
                f.write(resp.content)
    else:
        import shutil
        shutil.copy(req.audio_url, audio_path)

    # Split
    stems = await _split_stems_ffmpeg(audio_path, tmp_dir)

    # Package ZIP
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, path in stems.items():
            with open(path, "rb") as f:
                zf.writestr(f"{name}.wav", f.read())
        # Also include original
        with open(audio_path, "rb") as f:
            zf.writestr("original.wav", f.read())
    buf.seek(0)

    # Cleanup
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{req.track_name}_stems.zip"'},
    )


# ── AI Lyrics Completion ──────────────────────────────────────────────────────

@router.post("/lyrics")
async def ai_lyrics_completion(req: LyricsCompletionRequest):
    """
    Generate lyrics completion via LLM factory.
    Returns JSON with completed text.
    """
    try:
        from app.services.inference.llm_factory import llm_factory
        llm = llm_factory

        full_prompt = (
            f"你是一位{req.language}歌词创作大师。请根据以下内容续写歌词，"
            f"风格为{req.style}。只返回歌词，不要解释。\n\n"
            f"已有歌词：\n{req.prompt}\n\n续写："
        )
        messages = [{"role": "user", "content": full_prompt}]
        text = await llm.call(
            messages=messages,
            provider="auto",
            temperature=0.9,
            max_tokens=req.max_tokens,
        )
        return {"lyrics": text, "style": req.style, "language": req.language}
    except Exception as e:
        logger.error("Lyrics completion failed: %s", e)
        # Fallback: simple echo
        return JSONResponse(
            status_code=200,
            content={
                "lyrics": "（AI 续写暂不可用，请稍后重试）",
                "error": str(e),
            },
        )


# ── Lyrics Streaming (SSE) ───────────────────────────────────────────────────

@router.post("/lyrics/stream")
async def ai_lyrics_stream(req: LyricsCompletionRequest):
    """
    Stream lyrics completion via Server-Sent Events.
    """
    import json

    async def generate():
        try:
            from app.services.inference.llm_factory import llm_factory
            llm = llm_factory
            full_prompt = (
                f"你是一位{req.language}歌词创作大师。请根据以下内容续写歌词，"
                f"风格为{req.style}。只返回歌词，不要解释。\n\n"
                f"已有歌词：\n{req.prompt}\n\n续写："
            )
            messages = [{"role": "user", "content": full_prompt}]
            text = await llm.call(
                messages=messages,
                provider="auto",
                temperature=0.9,
                max_tokens=req.max_tokens,
            )
            yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error("Lyrics stream failed: %s", e)
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )