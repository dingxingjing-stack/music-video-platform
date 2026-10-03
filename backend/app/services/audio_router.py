"""
Audio Router — Stem export + AI lyrics completion endpoints.

POST /api/v1/audio/stems   — Split audio into stems (vocals/drums/bass/other) → ZIP
POST /api/v1/audio/lyrics  — AI lyrics completion (A-17: 音潮主链，llm_factory 已移除)
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

    import subprocess as _subprocess

    for name, af_args in band_configs.items():
        out_path = os.path.join(output_dir, f"{name}.wav")
        cmd = [
            "ffmpeg", "-y", "-i", audio_path,
            *af_args,
            "-c:a", "pcm_s16le",
            out_path,
        ]
        # 用 asyncio.to_thread 跑同步 subprocess.run，避免 asyncio.create_subprocess_exec
        # 在非"子进程能力"的 event loop（如 TestClient 的 anyio 线程 loop / Windows）上抛
        # NotImplementedError（BaseEventLoop._make_subprocess_transport 需要平台专属 loop）。
        # 生产/开发行为不变：仍真实调用 ffmpeg，返回相同的 {name: path} 映射。
        proc = await asyncio.to_thread(
            lambda c=cmd: _subprocess.run(c, capture_output=True, timeout=60)
        )
        if proc.returncode == 0 and os.path.exists(out_path):
            stems[name] = out_path
        else:
            stderr_text = (proc.stderr or b"").decode(errors="replace")[:200]
            logger.warning("Stem %s extraction failed: %s", name, stderr_text)

    return stems


@router.post("/stems")
async def export_stems(req: StemExportRequest):
    """
    Split audio into stems and return ZIP.
    Falls back to a mock ZIP with the original audio if ffmpeg unavailable.
    """
    # Production environment:禁止使用伪分轨（频段滤波）作为真实 stem 返回
    if os.getenv("ENVIRONMENT", "development").lower() == "production":
        logger.warning("Production environment: Stem separation via ffmpeg pseudo-stems disabled")
        return StreamingResponse(
            io.BytesIO(b""),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{req.track_name}_stems.zip"'},
            status_code=503,  # Service Unavailable - no real stem provider in production
        )

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
#
# P4-B2 Phase A-17（2026-10-02 裁定）：「歌词继续写」主链 = 音潮 Lyrics。
# Agnes / Gemini / NVIDIA（llm_factory）已从本功能调用链移除。
#
# 语义甄别（§十三 CURRENT CODE PATH）：
# - 本端点是「已有歌词片段的文本续写」（前端 AILyricsCompletion），不是
#   「对已有歌曲继续生成音乐」（后者 = /music/continue，路由已停止注册），
#   也不是「AI 写词」（/api/v1/lyrics/generate，lyric_service，语义独立不动）。
# - 音潮歌词官方 API 仅有一种（POST /api/v1/lyric/generate，按主题/描述生成）；
#   续写 = 把「已有片段 + 续写指令」整体作为 prompt 传入，属官方 API 正常用法。
# - fallback：复用 lyrics_engine 双供应商编排（音潮主 → 天谱乐 Lyric v1 备，
#   45s hard deadline），fallback 行为明确且不引入任何 llm_factory 供应商。
# - 本功能保持免费（零 Credits 交互，与 lyrics_engine 约束一致）。

_LYRICS_COMPLETION_PROMPT_MAX = 2000  # 与 AI 写词端点（lyric_service >2000→400）同口径


def _build_completion_prompt(fragment: str, style: str, language: str) -> str:
    """把已有片段包装成续写 prompt（供应商 prompt 为自由文本，官方字段仅此一个）。"""
    return (
        f"请续写以下歌词片段。风格：{style}；语言：{language}。"
        f"只输出续写的新歌词段落，不要重复已有片段，不要任何解释。\n\n"
        f"已有歌词：\n{fragment}"
    )


async def _generate_lyrics_completion(prompt: str, style: str, language: str) -> dict:
    """歌词继续写统一实现（/lyrics 与 /lyrics/stream 共用）。

    返回 {"lyrics": str, "provider": str} 或 {"error": str}（脱敏）。
    """
    from app.services.lyrics_engine import lyrics_engine

    result = await lyrics_engine.generate(
        _build_completion_prompt(prompt, style, language)
    )
    if result.status == "succeeded" and result.lyric.strip():
        return {"lyrics": result.lyric, "provider": result.provider}
    # 失败：明确错误文案（与既有前端契约一致：HTTP 200 + lyrics 兜底文案）
    return {"error": result.error or "歌词续写失败，请稍后重试"}


@router.post("/lyrics")
async def ai_lyrics_completion(req: LyricsCompletionRequest):
    """
    歌词继续写（AI lyrics completion）。
    主链 = 音潮 Lyrics（lyrics_engine 编排，音潮 → 天谱乐备）。
    返回 JSON：{"lyrics": <续写文本>} 或 {"lyrics": <兜底文案>, "error": <原因>}。
    """
    fragment = req.prompt.strip()
    if not fragment:
        return JSONResponse(status_code=400, content={"error": "已有歌词片段不能为空"})
    if len(fragment) > _LYRICS_COMPLETION_PROMPT_MAX:
        return JSONResponse(
            status_code=400,
            content={"error": f"已有歌词片段过长（>{_LYRICS_COMPLETION_PROMPT_MAX} 字符）"},
        )
    try:
        out = await _generate_lyrics_completion(fragment, req.style, req.language)
    except Exception as e:  # noqa: BLE001 — 引擎永不抛出，此为兜底防线
        logger.error("Lyrics completion failed: %s", e)
        out = {"error": "AI 续写暂不可用，请稍后重试"}
    if "error" in out:
        return {"lyrics": "（AI 续写暂不可用，请稍后重试）", "error": out["error"],
                "style": req.style, "language": req.language}
    return {"lyrics": out["lyrics"], "provider": out.get("provider", ""),
            "style": req.style, "language": req.language}


# ── Lyrics Streaming (SSE) ───────────────────────────────────────────────────

@router.post("/lyrics/stream")
async def ai_lyrics_stream(req: LyricsCompletionRequest):
    """
    歌词继续写（SSE 形态，A-17 已切音潮主链；结果一次性下发，与既有前端契约一致）。
    """
    import json

    async def generate():
        try:
            fragment = req.prompt.strip()
            if not fragment or len(fragment) > _LYRICS_COMPLETION_PROMPT_MAX:
                yield f"data: {json.dumps({'error': '已有歌词片段为空或过长'}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return
            out = await _generate_lyrics_completion(fragment, req.style, req.language)
            if "error" in out:
                yield f"data: {json.dumps({'error': out['error']}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'text': out['lyrics']}, ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error("Lyrics stream failed: %s", e)
            yield f"data: {json.dumps({'error': 'AI 续写暂不可用，请稍后重试'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )