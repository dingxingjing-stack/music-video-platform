"""声音克隆异步任务编排 — 将 /voice/clone 接入 task_store + WS + CDN。

流程（对齐 ai_music._run_generation 语义，但不触碰 ai_limits.py）：
  pending -> processing(下载参考音频 + ASR 转写) -> generating(GPT-SoVITS Modal)
  -> uploading(R2) -> completed | failed

ASR 转写（Phase 3，faster-whisper / CPU int8，Web 容器执行，不新增 Modal GPU）：
  - 参考音频先做大小 / 格式 / 时长校验，超标直接 failed。
  - prompt_text / prompt_language 未显式提供时自动转写，结果写回
    VoiceSample.prompt_text / prompt_language（后续克隆复用，避免重复转写）。
  - ASR 失败 / 超时 / 空转写 -> failed，不伪造 prompt_text，不调用 GPT-SoVITS。

额度/锁语义映射：
  - reserve 时机：/voice/upload 已占用当月克隆配额（voice_clone_service 现有逻辑，
    保持 /upload 返回协议不变）。克隆任务本身不重复占用。
  - completed：任务 completed，配额保留。
  - failed（QueueFullError / timeout / 其它异常）：任务 failed + 释放用户锁；
    用户可对同一 voice_id 重新提交克隆（retry 不重复扣额度，参照 ai_music
    retry-stems 语义）。不调用 ai_limits.refund_generation —— 那是音乐生成专属，
    且本文件禁止修改 ai_limits.py。
  - 每用户同时仅 1 个克隆任务（task_store 锁），单任务超时由 task_store
    TASK_TIMEOUT / asyncio.wait_for 双层兜底。

参考音频统一走 /root/data/refs/{voice_id}（与 generated 输出隔离），跨容器
可见性依赖 Modal Volume 显式 commit() 时序（见 tts_client.upload_ref_audio）。
"""

import asyncio
import logging
import os
import tempfile
import time

import httpx

from app.services import task_store
from app.services.ace_step_client import QueueFullError
from app.services.asr_client import (
    TranscriptionError,
    transcribe_ref_audio,
    validate_ref_audio,
)
from app.services.cdn_uploader import cdn_uploader
from app.services.inference.base import PredictResult, TaskStatus
from app.services.tts_client import (
    download_generated,
    synthesize_cloned,
    upload_ref_audio,
)
from app.services.voice_clone_service import voice_clone_service
from app.websocket_manager import manager

logger = logging.getLogger(__name__)

# 单任务最大时长（与 task_store.TASK_TIMEOUT 一致，双保险）
VOICE_CLONE_MAX_SECONDS = float(os.getenv("TASK_TIMEOUT", "600"))


async def _broadcast(task_id: str, status: TaskStatus, progress: int, message: str, **metadata) -> None:
    """向 /ws/progress/{task_id} 订阅者广播克隆进度。"""
    result = PredictResult(
        task_id=task_id,
        status=status,
        progress=progress,
        message=message,
        metadata=metadata,
        updated_at=time.time(),
    )
    await manager.broadcast(task_id, result)


async def _fetch_ref_audio(audio_url: str) -> bytes | None:
    """下载参考音频 URL 到内存。失败返回 None（由业务层降级）。"""
    if not audio_url:
        return None
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(audio_url)
            if resp.status_code != 200 or not resp.content:
                logger.warning("参考音频下载失败: HTTP %s", resp.status_code)
                return None
            return resp.content
    except Exception as exc:  # noqa: BLE001 - 网络/超时统一降级
        logger.warning("参考音频下载异常: %s", exc)
        return None


async def _resolve_transcript(
    voice_id: str,
    audio_bytes: bytes,
    request_text: str,
    request_language: str,
) -> tuple[str, str]:
    """解析参考音频转写（prompt_text / prompt_language）。

    优先级：调用方显式提供 > 音色已存转写 > ASR 自动转写。
    ASR 失败 / 超时 / 空转写抛 TranscriptionError，调用方必须把任务标记 failed，
    禁止伪造 prompt_text，禁止继续调用 GPT-SoVITS。
    """
    if request_text and request_language:
        return request_text, request_language

    voice = voice_clone_service.find_voice(voice_id)
    if voice and voice.prompt_text:
        logger.info("复用音色 %s 已存转写，跳过 ASR", voice_id)
        return voice.prompt_text, voice.prompt_language or "auto"

    result = await transcribe_ref_audio(audio_bytes)
    prompt_text = request_text or result["prompt_text"]
    prompt_language = request_language or result["prompt_language"]
    voice_clone_service.record_transcript(
        voice_id,
        result["prompt_text"],
        result["prompt_language"],
        result["detected_language"],
    )
    return prompt_text, prompt_language


async def run_voice_clone(
    task_id: str,
    voice_id: str,
    text: str,
    audio_url: str,
    language: str = "zh",
    prompt_text: str = "",
    prompt_language: str = "",
    speed: float = 1.0,
) -> None:
    """后台执行声音克隆：参考音频 -> ASR 转写 -> Modal GPT-SoVITS -> R2 -> WS 广播。

    安全约束（Phase 3）：
      - 参考音频先做大小 / 格式 / 时长校验，超标直接 failed。
      - ASR 失败 / 超时 / 空转写 -> failed，不伪造 prompt_text，不调用 GPT-SoVITS。
      - 参考音频统一命名 refs/{voice_id}.wav（与 generated 隔离），不上传 CDN。
    """
    try:
        # 参考音频统一命名 refs/{voice_id}.wav（与 generated 隔离）
        task_store.update(task_id, state="processing", progress=10)
        await _broadcast(task_id, TaskStatus.LOADING, 10, "正在获取参考音频...", voice_id=voice_id)

        audio_bytes = await _fetch_ref_audio(audio_url)
        if not audio_bytes:
            raise RuntimeError("参考音频下载失败（URL 不可访问或为空）")

        try:
            validate_ref_audio(audio_bytes)
        except TranscriptionError as exc:
            raise RuntimeError(str(exc)) from exc

        task_store.update(task_id, state="processing", progress=30)
        await _broadcast(task_id, TaskStatus.LOADING, 30, "正在识别参考音频...", voice_id=voice_id)

        prompt_text, prompt_language = await _resolve_transcript(
            voice_id, audio_bytes, prompt_text, prompt_language,
        )

        task_store.update(task_id, state="processing", progress=35, prompt_text=prompt_text, prompt_language=prompt_language)
        await _broadcast(task_id, TaskStatus.LOADING, 35, "参考音频识别完成，上传参考音频...", voice_id=voice_id)

        ref_name = await upload_ref_audio(voice_id, audio_bytes)
        if not ref_name:
            raise RuntimeError("参考音频上传到共享卷失败")

        task_store.update(task_id, state="generating", progress=40)
        await _broadcast(task_id, TaskStatus.LOADING, 40, "GPT-SoVITS 推理中...", voice_id=voice_id)

        volume_result = await synthesize_cloned(
            ref_filename_in_volume=ref_name,
            text=text,
            language=language,
            prompt_text=prompt_text,
            prompt_language=prompt_language,
            speed=speed,
            out_stem=f"voice_{voice_id}",
        )
        if not volume_result:
            raise RuntimeError("GPT-SoVITS 克隆合成失败（请稍后重试）")

        task_store.update(task_id, state="uploading", progress=80, volume_files=volume_result)
        await _broadcast(task_id, TaskStatus.RUNNING, 80, "正在上传生成音频...", voice_id=voice_id)

        wav_name = volume_result.get("wav")
        if not wav_name:
            raise RuntimeError("GPT-SoVITS 未返回生成音频文件名")

        tmp_dir = tempfile.mkdtemp(prefix="voice_clone_")
        local_path = await download_generated(wav_name, tmp_dir)
        if not local_path:
            raise RuntimeError("生成音频从共享卷取回失败")

        manifest = await cdn_uploader.upload_music_package(task_id, {"wav": local_path})
        if not manifest or not manifest.get("wav"):
            raise RuntimeError("生成音频上传 R2 失败")

        task_store.update(
            task_id,
            state="completed",
            progress=100,
            download=manifest,
            audio_url=_sign_playback(task_id, manifest),
        )
        await _broadcast(
            task_id, TaskStatus.COMPLETED, 100,
            "声音克隆完成！", voice_id=voice_id,
            audio_url=task_store.get(task_id).get("audio_url"),
        )
    except QueueFullError as e:
        task_store.update(task_id, state="failed", error=str(e))
        await _broadcast(task_id, TaskStatus.FAILED, 0, str(e), voice_id=voice_id)
    except TimeoutError:
        task_store.update(task_id, state="failed", error="克隆超时，请稍后重试")
        await _broadcast(task_id, TaskStatus.FAILED, 0, "克隆超时，请稍后重试", voice_id=voice_id)
    except Exception as e:
        logger.exception("声音克隆任务失败")
        task_store.update(task_id, state="failed", error=f"{type(e).__name__}: {e}")
        await _broadcast(task_id, TaskStatus.FAILED, 0, str(e)[:300], voice_id=voice_id)
    finally:
        task_store.release_lock_for_task(task_id)


def _sign_playback(task_id: str, manifest: dict) -> str | None:
    """为克隆结果签发短期预签名播放 URL（仅 backend 侧可生成，10 分钟）。"""
    key = manifest.get("wav")
    if not key:
        return None
    try:
        return cdn_uploader.get_presigned_download_url(key, expires_in=600)
    except Exception:  # noqa: BLE001
        return None


async def run_voice_clone_with_timeout(
    task_id: str,
    voice_id: str,
    text: str,
    audio_url: str,
    language: str = "zh",
    prompt_text: str = "",
    prompt_language: str = "",
    speed: float = 1.0,
) -> None:
    """包一层超时（与 ai_music._run_with_timeout 同语义），超时标记 failed 并释放锁。"""
    try:
        await asyncio.wait_for(
            run_voice_clone(
                task_id=task_id,
                voice_id=voice_id,
                text=text,
                audio_url=audio_url,
                language=language,
                prompt_text=prompt_text,
                prompt_language=prompt_language,
                speed=speed,
            ),
            timeout=VOICE_CLONE_MAX_SECONDS,
        )
    except TimeoutError:
        task_store.update(task_id, state="failed", error="克隆超时，请稍后重试")
        await _broadcast(task_id, TaskStatus.FAILED, 0, "克隆超时，请稍后重试", voice_id=voice_id)
        task_store.release_lock_for_task(task_id)
