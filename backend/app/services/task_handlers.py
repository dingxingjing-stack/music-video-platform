"""Background task handlers for fire-and-forget endpoints.

These functions are spawned by `asyncio.create_task()` to run predictions
asynchronously while the HTTP response returns immediately.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

from app.services.inference import PredictResult, TaskStatus

logger = logging.getLogger(__name__)


async def run_tts_and_save(
    svc: Any,
    task_id: str,
    audio_bytes: bytes,
    text: str,
    language: str,
    opt_filename: str,
    results_dir: str,
) -> None:
    """Run TTS prediction, save result to results_dir, broadcast completion.

    Replicates the original _run_tts() in main.py before split:
      - On completed+result_url: download result to results_dir, broadcast updated local url.
      - On other terminal status: broadcast result with elapsed_time.
      - On exception: broadcast FAILED with error message.
    """
    start_time = time.time()
    try:
        result = await svc.synthesize(
            task_id=task_id,
            reference_audio=audio_bytes,
            text=text,
            language=language,
            opt_filename=opt_filename,
        )
        elapsed = time.time() - start_time

        if result.status.value == "completed" and result.result_url:
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.get(result.result_url)
                    if resp.status_code == 200:
                        filepath = os.path.join(results_dir, f"{task_id}_{opt_filename}")
                        with open(filepath, "wb") as f:
                            f.write(resp.content)
                        await _report(
                            svc, task_id, TaskStatus.COMPLETED, 100,
                            result.message or "Done!",
                            f"/results/{task_id}_{opt_filename}",
                            None, {**result.metadata, "elapsed_time": round(elapsed, 2)},
                        )
                        return
            except Exception as e:
                logger.warning("Failed to save TTS result: %s", e)
                await _report(
                    svc, task_id, TaskStatus.COMPLETED, 100,
                    "Done! (save failed)",
                    result.result_url, None,
                    {**result.metadata, "elapsed_time": round(elapsed, 2)},
                )
                return

        # Other terminal status — completed/failed without download
        await _report(
            svc, task_id, result.status, result.progress,
            result.message or result.error or "Done!",
            result.result_url, result.error,
            {**result.metadata, "elapsed_time": round(elapsed, 2)},
        )
    except Exception as e:
        elapsed = time.time() - start_time
        logger.exception("TTS background task failed: %s", e)
        await _report(
            svc, task_id, TaskStatus.FAILED, 0,
            "TTS task failed", None, str(e)[:500],
            {"elapsed_time": round(elapsed, 2)},
        )


async def _report(
    svc: Any, task_id: str, status: Any, progress: int,
    message: str, result_url: Any, error: Any, metadata: dict,
) -> None:
    """Helper to broadcast a terminal PredictResult."""
    final = PredictResult(
        task_id=task_id,
        status=status,
        progress=progress,
        message=message,
        result_url=result_url,
        error=error,
        metadata=metadata,
        updated_at=time.time(),
    )
    await svc._report(final)


async def run_musicgen_and_save(
    svc,
    task_id: str,
    prompt: str,
    duration: float,
    temperature: float,
    results_dir: str,
) -> None:
    """Run MusicGen prediction, save result to results_dir, broadcast completion.

    Mirrors original _run_musicgen() in main.py before split.
    """
    start_time = time.time()
    try:
        result = await svc.predict(PredictRequest(
            service_type="music",
            task_id=task_id,
            payload={},
            extra={"prompt": prompt, "duration": duration, "temperature": temperature},
        ))
        elapsed = time.time() - start_time

        if result.status.value == "completed" and result.result_url:
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.get(result.result_url)
                    if resp.status_code == 200:
                        filepath = os.path.join(results_dir, f"{task_id}_music.wav")
                        with open(filepath, "wb") as f:
                            f.write(resp.content)
                        await _report(
                            svc, task_id, TaskStatus.COMPLETED, 100,
                            "Music generated!",
                            f"/results/{task_id}_music.wav",
                            None, {**result.metadata, "elapsed_time": round(elapsed, 2)},
                        )
                        return
            except Exception as e:
                logger.warning("Failed to save music result: %s", e)
                await _report(
                    svc, task_id, TaskStatus.COMPLETED, 100,
                    "Music generated! (save failed)",
                    result.result_url, None,
                    {**result.metadata, "elapsed_time": round(elapsed, 2)},
                )
                return

        await _report(
            svc, task_id, result.status, result.progress,
            result.message or result.error or "Done!",
            result.result_url, result.error,
            {**result.metadata, "elapsed_time": round(elapsed, 2)},
        )
    except Exception as e:
        elapsed = time.time() - start_time
        logger.exception("MusicGen background task failed: %s", e)
        await _report(
            svc, task_id, TaskStatus.FAILED, 0,
            "Music generation failed", None, str(e)[:500],
            {"elapsed_time": round(elapsed, 2)},
        )
