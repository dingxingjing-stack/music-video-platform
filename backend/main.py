"""
Inference Service Application Entry Point

FastAPI application that exposes the AI inference services via REST API.
Supports TTS (GPT-SoVITS), Music Generation (MusicGen), Video Generation (CogVideoX),
and a Mock service for WebSocket progress broadcast testing.

Usage:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
import uuid
from datetime import datetime
from typing import Any, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles

# Load .env file if present
load_dotenv()

# TTS backend mode: "real" uses GPT-SoVITS HF Space, "mock" uses simulated TTS
TTS_BACKEND_MODE = os.getenv("TTS_BACKEND_MODE", "mock").lower()
# Workflow mode: "mock" uses simulated services, "real" uses HF Spaces
WORKFLOW_MODE = os.getenv("WORKFLOW_MODE", "mock").lower()

from app.services.inference import (
    InferenceServiceFactory,
    PredictRequest,
    PredictResult,
    TaskStatus,
)
from app.services.inference.gpt_sovits import GPTSovitsService
from app.services.inference.factory import _SERVICE_REGISTRY, _ALIASES
from app.services.inference.mock import MockInferenceService
from app.services.workflow import WorkflowEngine
from app.services.batch_queue import batch_queue, BatchState
from app.websocket_manager import ConnectionManager, manager

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Factory initialization
# ---------------------------------------------------------------------------

# Read optional config from environment
# Env var prefixes must match _SERVICE_REGISTRY keys: GPT_SOVITS, MUSICGEN, COGVIDEOX
_CONFIG_ENV_PREFIXES = {
    "tts": "GPT_SOVITS",
    "music": "MUSICGEN",
    "video": "COGVIDEOX",
    "demucs": "DEMUCS",
}

_config: dict[str, Any] = {}
for service_type, prefix in _CONFIG_ENV_PREFIXES.items():
    url = os.getenv(f"{prefix}_SPACE_URL")
    token = os.getenv(f"{prefix}_API_TOKEN")
    timeout = os.getenv(f"{prefix}_HTTP_TIMEOUT")
    fn_index = os.getenv(f"{prefix}_FN_INDEX")

    svc_cfg: dict[str, Any] = {}
    if url:
        svc_cfg["space_url"] = url
    if token:
        svc_cfg["api_token"] = token
    if timeout:
        svc_cfg["http_timeout"] = float(timeout)
    if fn_index is not None:
        svc_cfg["fn_index"] = int(fn_index)

    if svc_cfg:
        _config[service_type] = svc_cfg

factory = InferenceServiceFactory(_config)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Inference Service API",
    description="AI-powered TTS, Music, and Video generation via HF Spaces",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Serve generated audio files
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
os.makedirs(RESULTS_DIR, exist_ok=True)
app.mount("/results", StaticFiles(directory=RESULTS_DIR), name="results")


# ---------------------------------------------------------------------------
# WebSocket broadcast callback
# ---------------------------------------------------------------------------

async def _websocket_broadcast(task_id: str, result: PredictResult) -> None:
    """
    Broadcast callback wired into BaseInferenceService._report().

    Pushes every progress update to subscribed WebSocket clients.
    """
    await manager.broadcast(task_id, result)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health", tags=["operations"])
async def health_check():
    """Check if the inference service is running and all backends are reachable."""
    services_health: dict[str, dict[str, Any]] = {}

    for service_type in ("tts", "music", "video"):
        try:
            svc = factory.create(service_type, cache=False)
            healthy, message = await svc.health_check()
            services_health[service_type] = {"healthy": healthy, "message": message}
        except Exception as exc:
            services_health[service_type] = {"healthy": False, "message": str(exc)[:200]}

    all_healthy = all(s.get("healthy") for s in services_health.values())

    return {
        "status": "ok" if all_healthy else "degraded",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "services": services_health,
    }


# ---------------------------------------------------------------------------
# Predict endpoints
# ---------------------------------------------------------------------------


@app.post("/api/v1/predict/{service_type}", tags=["predictions"])
async def predict(
    service_type: str,
    request: Request,
):
    """
    Submit a prediction request to an inference service.

    Args:
        service_type: One of "tts", "music", "video", or "mock".

    Body (Mock example):
        {
            "task_id": "abc123",
            "duration": 10.0,
            "tick_interval": 1.0
        }

    Body (TTS example):
        {
            "text": "Hello world",
            "reference_audio": "<base64 encoded wav bytes>",
            "language": "zh"
        }

    Returns:
        PredictResult serialized as JSON.
    """
    canonical = _ALIASES.get(service_type.lower(), service_type.lower())

    if canonical not in _SERVICE_REGISTRY:
        # Check if it's the special "mock" type
        if service_type.lower() != "mock":
            available = ", ".join(_SERVICE_REGISTRY.keys())
            raise HTTPException(
                status_code=400,
                detail=f"Unknown service type '{service_type}'. Available: {available}",
            )

    # Parse request body
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid JSON body")

    # Build PredictRequest
    task_id = body.get("task_id") or str(uuid.uuid4())[:8]
    payload = body.get("payload", {})

    pred_request = PredictRequest(
        service_type=canonical,
        task_id=task_id,
        payload=payload,
        extra=body,  # forward all fields as extra
    )

    # Dispatch: mock → real service
    if service_type.lower() == "mock":
        duration = float(body.get("duration", 10.0))
        tick_interval = float(body.get("tick_interval", 1.0))

        # Allow tests to inject a broadcast collector via app.state
        test_collector = getattr(request.app.state, "broadcast_collector", None)

        if test_collector is not None:
            async def _cb(tid: str, result: PredictResult) -> None:
                await test_collector(tid, result)
        else:
            _cb = _websocket_broadcast

        svc = MockInferenceService(
            service_type="mock",
            duration=duration,
            tick_interval=tick_interval,
            broadcast=_cb,
        )

        pred_request = PredictRequest(
            service_type="mock",
            task_id=task_id,
            payload=payload,
            extra=body,
        )
    else:
        # Create service and run prediction — wire broadcast callback
        try:
            svc = factory.create(
                canonical,
                broadcast=_websocket_broadcast,
            )
        except Exception as exc:
            logger.error("Failed to create service '%s': %s", canonical, exc)
            raise HTTPException(status_code=503, detail=f"Service unavailable: {exc}")

    try:
        result = await svc.predict(pred_request)
    except Exception as exc:
        logger.exception("Prediction failed for task %s", task_id)
        raise HTTPException(
            status_code=500,
            detail=f"Prediction error: {exc}",
        )

    return JSONResponse(
        content=result.to_dict(),
        status_code=200 if result.status != TaskStatus.FAILED else 200,
    )


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@app.websocket("/ws/progress/{task_id}")
async def websocket_progress(websocket: WebSocket, task_id: str):
    """
    WebSocket endpoint for real-time task progress updates.

    Connect::
        ws = new WebSocket("ws://localhost:8000/ws/progress/{task_id}")

    Each message is a JSON-serialised PredictResult::
        {
            "task_id": "...",
            "status": "running",
            "progress": 45,
            "message": "Inference in progress... (45%)",
            "metadata": {...},
            "updated_at": 1719580000.0
        }

    The connection stays open until the task completes (terminal status)
    or the client disconnects.
    """
    await websocket.accept()
    await manager.connect(task_id, websocket)
    try:
        # Keep the connection alive.  All progress messages are pushed
        # via the broadcast callback — we just need to keep the WS open.
        # Periodically call receive_text() with a timeout so the event
        # loop is not starved by blocking indefinitely.  The timeout
        # ensures background tasks (mock predictions, broadcasts) can
        # still run while we wait for client heartbeats.
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Periodic yield — event loop can now process broadcasts
                continue
    except Exception:
        logger.info("WebSocket disconnected: task_id=%s", task_id)
    finally:
        await manager.disconnect(task_id, websocket)


# ---------------------------------------------------------------------------
# Mock test endpoint — fire-and-forget a simulated task
# ---------------------------------------------------------------------------


@app.post("/api/v1/mock/run", tags=["mock"])
async def mock_run(request: Request):
    """
    Start a simulated inference task in the background and return the task_id.

    Connect to ``/ws/progress/{task_id}`` to receive real-time progress updates.

    Body::
        {
            "duration": 10.0,
            "tick_interval": 1.0
        }

    Returns::
        {
            "task_id": "abc123",
            "status": "started",
            "websocket": "/ws/progress/abc123"
        }
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    task_id = body.get("task_id") or str(uuid.uuid4())[:8]
    duration = float(body.get("duration", 10.0))
    tick_interval = float(body.get("tick_interval", 1.0))

    svc = MockInferenceService(
        service_type="mock",
        duration=duration,
        tick_interval=tick_interval,
        broadcast=_websocket_broadcast,
    )

    # Run predict in background; it will broadcast progress to WebSocket clients
    asyncio.create_task(svc.predict(PredictRequest(
        service_type="mock",
        task_id=task_id,
        payload={},
        extra=body,
    )))

    return {
        "task_id": task_id,
        "status": "started",
        "websocket": f"/ws/progress/{task_id}",
        "duration": duration,
    }


# ---------------------------------------------------------------------------
# TTS fire-and-forget endpoint
# ---------------------------------------------------------------------------


@app.post("/api/v1/tts/run", tags=["tts"])
async def tts_run(request: Request):
    """
    Start a TTS synthesis task in the background and return the task_id.

    Connect to ``/ws/progress/{task_id}`` to receive real-time progress updates.

    Body::
        {
            "text": "你好世界",
            "language": "zh",
            "reference_audio": "<base64-encoded-wav-bytes>",
            "opt_filename": "output.wav"
        }

    Returns::
        {
            "task_id": "abc123",
            "status": "started",
            "websocket": "/ws/progress/abc123"
        }
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    task_id = body.get("task_id") or str(uuid.uuid4())[:8]
    text = body.get("text", "")
    language = body.get("language", "zh")
    reference_audio_b64 = body.get("reference_audio", "")
    opt_filename = body.get("opt_filename", "output.wav")

    if not text:
        raise HTTPException(status_code=422, detail="'text' is required")

    # Choose TTS backend based on environment
    if TTS_BACKEND_MODE == "mock":
        # Mock TTS backend — no audio required
        logger.info("Using mock TTS backend (TTS_BACKEND_MODE=%s)", TTS_BACKEND_MODE)
        svc = MockInferenceService(
            service_type="tts-mock",
            duration=float(body.get("duration", 10.0)),
            tick_interval=float(body.get("tick_interval", 1.0)),
            broadcast=_websocket_broadcast,
        )
        asyncio.create_task(svc.predict(PredictRequest(
            service_type="tts-mock",
            task_id=task_id,
            payload={},
            extra=body,
        )))
    else:
        # Real GPT-SoVITS backend — audio required
        if not reference_audio_b64:
            raise HTTPException(status_code=422, detail="'reference_audio' (base64) is required")

        # Decode base64 audio
        try:
            audio_bytes = base64.b64decode(reference_audio_b64)
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid base64 in 'reference_audio'")

        try:
            svc = GPTSovitsService(
                space_url=factory._config.get("tts", {}).get("space_url", "https://huggingface.co/spaces/sec-ai/GPT-SoVITS"),
                api_token=factory._config.get("tts", {}).get("api_token"),
                fn_index=factory._config.get("tts", {}).get("fn_index", 0),
                http_timeout=factory._config.get("tts", {}).get("http_timeout", 600.0),
                broadcast=_websocket_broadcast,
            )

            # Run predict in background; it will broadcast progress to WebSocket clients
            asyncio.create_task(_run_tts(svc, task_id, audio_bytes, text, language, opt_filename))
        except Exception as exc:
            logger.error("Failed to create GPTSovitsService: %s", exc)
            raise HTTPException(
                status_code=503,
                detail=f"TTS service unavailable (try TTS_BACKEND_MODE=mock): {exc}",
            )

    return {
        "task_id": task_id,
        "status": "started",
        "websocket": f"/ws/progress/{task_id}",
    }


async def _run_tts(
    svc: "GPTSovitsService",
    task_id: str,
    audio_bytes: bytes,
    text: str,
    language: str,
    opt_filename: str,
) -> None:
    """Background task: run TTS prediction and save result to results/."""
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

        # Save generated audio file if completed
        if result.status.value == "completed" and result.result_url:
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.get(result.result_url)
                    if resp.status_code == 200:
                        filepath = os.path.join(RESULTS_DIR, f"{task_id}_{opt_filename}")
                        with open(filepath, "wb") as f:
                            f.write(resp.content)
                        # Update result_url to local path
                        local_url = f"/results/{task_id}_{opt_filename}"
                        final = PredictResult(
                            task_id=task_id,
                            status=TaskStatus.COMPLETED,
                            progress=100,
                            message="Done!",
                            result_url=local_url,
                            metadata={
                                **result.metadata,
                                "elapsed_time": round(elapsed, 2),
                            },
                            updated_at=time.time(),
                        )
                        await svc._report(final)
            except Exception as e:
                logger.warning("Failed to save TTS result: %s", e)
                # Still report with elapsed time even if save fails
                final = PredictResult(
                    task_id=task_id,
                    status=TaskStatus.COMPLETED,
                    progress=100,
                    message="Done! (save failed)",
                    result_url=result.result_url,
                    metadata={
                        **result.metadata,
                        "elapsed_time": round(elapsed, 2),
                    },
                    updated_at=time.time(),
                )
                await svc._report(final)
        else:
            # Report final status (completed or failed) with elapsed time
            final = PredictResult(
                task_id=task_id,
                status=result.status,
                progress=result.progress,
                message=result.message or result.error or "Done!",
                result_url=result.result_url,
                error=result.error,
                metadata={
                    **result.metadata,
                    "elapsed_time": round(elapsed, 2),
                },
                updated_at=time.time(),
            )
            await svc._report(final)
    except Exception as e:
        elapsed = time.time() - start_time
        logger.exception("TTS background task failed: %s", e)
        failed = PredictResult(
            task_id=task_id,
            status=TaskStatus.FAILED,
            progress=0,
            message="TTS task failed",
            error=str(e)[:500],
            metadata={"elapsed_time": round(elapsed, 2)},
            updated_at=time.time(),
        )
        await svc._report(failed)


# ---------------------------------------------------------------------------
# MusicGen fire-and-forget endpoint
# ---------------------------------------------------------------------------


@app.post("/api/v1/music/run", tags=["music"])
async def music_run(request: Request):
    """
    Start a MusicGen music generation task in the background.

    Body::
        {
            "task_id": "abc123",
            "prompt": "upbeat electronic dance music with synth lead",
            "duration": 10.0,
            "temperature": 0.8
        }

    Returns::
        {
            "task_id": "abc123",
            "status": "started",
            "websocket": "/ws/progress/abc123"
        }
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    task_id = body.get("task_id") or str(uuid.uuid4())[:8]
    prompt = body.get("prompt", "")
    duration = float(body.get("duration", 10.0))
    temperature = float(body.get("temperature", 0.8))

    if not prompt:
        raise HTTPException(status_code=422, detail="'prompt' is required")

    # Use mock if real MusicGen is unavailable
    if WORKFLOW_MODE == "mock":
        svc = MockInferenceService(
            service_type="music-mock",
            duration=duration,
            tick_interval=0.5,
            broadcast=_websocket_broadcast,
        )
        asyncio.create_task(svc.predict(PredictRequest(
            service_type="music",
            task_id=task_id,
            payload={},
            extra={"prompt": prompt, "duration": duration},
        )))
    else:
        try:
            svc = factory.create("music", broadcast=_websocket_broadcast)
        except Exception as exc:
            logger.error("Failed to create MusicGenService: %s", exc)
            raise HTTPException(
                status_code=503,
                detail=f"Music service unavailable: {exc}",
            )

        asyncio.create_task(_run_musicgen(svc, task_id, prompt, duration, temperature))

    return {
        "task_id": task_id,
        "status": "started",
        "websocket": f"/ws/progress/{task_id}",
    }


async def _run_musicgen(
    svc,
    task_id: str,
    prompt: str,
    duration: float,
    temperature: float,
) -> None:
    """Background task: run MusicGen prediction and save result."""
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
                        filepath = os.path.join(RESULTS_DIR, f"{task_id}_music.wav")
                        with open(filepath, "wb") as f:
                            f.write(resp.content)
                        local_url = f"/results/{task_id}_music.wav"
                        final = PredictResult(
                            task_id=task_id,
                            status=TaskStatus.COMPLETED,
                            progress=100,
                            message="Music generated!",
                            result_url=local_url,
                            metadata={
                                **result.metadata,
                                "elapsed_time": round(elapsed, 2),
                            },
                            updated_at=time.time(),
                        )
                        await svc._report(final)
            except Exception as e:
                logger.warning("Failed to save music result: %s", e)
                final = PredictResult(
                    task_id=task_id,
                    status=TaskStatus.COMPLETED,
                    progress=100,
                    message="Music generated! (save failed)",
                    result_url=result.result_url,
                    metadata={
                        **result.metadata,
                        "elapsed_time": round(elapsed, 2),
                    },
                    updated_at=time.time(),
                )
                await svc._report(final)
        else:
            final = PredictResult(
                task_id=task_id,
                status=result.status,
                progress=result.progress,
                message=result.message or result.error or "Done!",
                result_url=result.result_url,
                error=result.error,
                metadata={
                    **result.metadata,
                    "elapsed_time": round(elapsed, 2),
                },
                updated_at=time.time(),
            )
            await svc._report(final)
    except Exception as e:
        elapsed = time.time() - start_time
        logger.exception("MusicGen background task failed: %s", e)
        failed = PredictResult(
            task_id=task_id,
            status=TaskStatus.FAILED,
            progress=0,
            message="Music generation failed",
            error=str(e)[:500],
            metadata={"elapsed_time": round(elapsed, 2)},
            updated_at=time.time(),
        )
        await svc._report(failed)


# ---------------------------------------------------------------------------
# Batch endpoints — Sequential multi-prompt generation
# ---------------------------------------------------------------------------


@app.post("/api/v1/batch/a", tags=["batch"])
async def batch_path_a(request: Request):
    """
    Batch generate music for multiple prompts sequentially.

    Body::
        {
            "prompts": [
                {"prompt": "upbeat electronic", "duration": 10},
                {"prompt": "calm piano", "duration": 15}
            ],
            "duration": 10,
            "temperature": 0.8
        }

    Returns a batch_id. Connect to WS to track progress.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    prompts = body.get("prompts", [])
    if not prompts:
        raise HTTPException(status_code=422, detail="'prompts' array is required")

    duration = float(body.get("duration", 10.0))
    temperature = float(body.get("temperature", 0.8))

    engine = _get_workflow_engine()

    batch = await batch_queue.submit(
        path="a",
        items=[
            {
                "prompt": p.get("prompt", ""),
                "extra": {
                    "duration": float(p.get("duration", duration)),
                    "temperature": float(p.get("temperature", temperature)),
                },
            }
            for p in prompts
        ],
        broadcast=_websocket_broadcast,
    )

    # Start execution
    async def _run_batch_a(batch_state, run_fn, broadcast):
        for item in batch_state.items:
            item.status = "running"
            batch_state.current_index = item.index
            batch_state.updated_at = time.time()

            # Send batch-level progress message BEFORE each item
            batch_msg = PredictResult(
                task_id=batch_state.batch_id,
                status=TaskStatus.RUNNING,
                progress=int(((item.index + 1) / batch_state.total) * 100),
                message=f"Processing {item.index + 1}/{batch_state.total}: {item.prompt[:40]}",
                metadata={
                    "batch_id": batch_state.batch_id,
                    "path": "a",
                    "batch_total": batch_state.total,
                    "batch_completed": batch_state.completed,
                    "batch_failed": batch_state.failed,
                    "current_item": {
                        "index": item.index,
                        "task_id": item.task_id,
                        "prompt": item.prompt,
                    },
                },
                updated_at=time.time(),
            )
            await broadcast(batch_state.batch_id, batch_msg)

            try:
                result = await engine.run_path_a(
                    item.task_id,  # Use per-item task_id for sub-task
                    item.prompt,
                    duration=item.extra.get("duration", duration),
                    temperature=item.extra.get("temperature", temperature),
                )
                item.status = result.status.value if result else "failed"
                if result and result.status == TaskStatus.COMPLETED:
                    batch_state.completed += 1
                else:
                    batch_state.failed += 1
            except Exception as exc:
                logger.error("Batch item %d failed: %s", item.index, exc)
                item.status = "failed"
                batch_state.failed += 1

            batch_state.updated_at = time.time()

        # Send final batch summary
        batch_state.status = "completed" if batch_state.failed == 0 else "partial"
        batch_state.updated_at = time.time()

        final_msg = PredictResult(
            task_id=batch_state.batch_id,
            status=TaskStatus.COMPLETED if batch_state.failed == 0 else TaskStatus.FAILED,
            progress=100,
            message=f"Batch complete: {batch_state.completed} succeeded, {batch_state.failed} failed",
            metadata={
                "batch_id": batch_state.batch_id,
                "path": "a",
                "batch_total": batch_state.total,
                "batch_completed": batch_state.completed,
                "batch_failed": batch_state.failed,
                "items": [
                    {
                        "index": it.index,
                        "task_id": it.task_id,
                        "prompt": it.prompt,
                        "status": it.status,
                    }
                    for it in batch_state.items
                ],
            },
            updated_at=time.time(),
        )
        await broadcast(batch_state.batch_id, final_msg)

        async with batch_queue._lock:
            if batch_queue._running is batch_state:
                batch_queue._running = None
                if batch_queue._queue:
                    nb = batch_queue._queue.pop(0)
                    batch_queue._running = nb
                    asyncio.create_task(_run_batch_a(nb, run_fn, broadcast))

    asyncio.create_task(_run_batch_a(batch, lambda *a, **k: None, _websocket_broadcast))

    return {
        "batch_id": batch.batch_id,
        "path": "a",
        "total": batch.total,
        "status": batch.status,
        "websocket": f"/ws/progress/{batch.batch_id}",
    }


@app.post("/api/v1/batch/b", tags=["batch"])
async def batch_path_b(request: Request):
    """
    Batch generate hybrid tracks for multiple prompt+TTS pairs.

    Body::
        {
            "items": [
                {
                    "prompt": "chill lofi beat",
                    "tts_text": "Hello world",
                    "duration": 10
                }
            ]
        }
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    items = body.get("items", [])
    if not items:
        raise HTTPException(status_code=422, detail="'items' array is required")

    engine = _get_workflow_engine()

    batch = await batch_queue.submit(
        path="b",
        items=[
            {
                "prompt": item.get("prompt", ""),
                "extra": {
                    "tts_text": item.get("tts_text", "Hello world"),
                    "duration": float(item.get("duration", 10.0)),
                    "tts_language": item.get("tts_language", "zh"),
                    "reference_audio_b64": item.get("reference_audio"),
                },
            }
            for item in items
        ],
        broadcast=_websocket_broadcast,
    )

    async def _run_batch_b(batch_state, run_fn, broadcast):
        for item in batch_state.items:
            item.status = "running"
            batch_state.current_index = item.index
            batch_state.updated_at = time.time()

            # Send batch-level progress message BEFORE each item
            batch_msg = PredictResult(
                task_id=batch_state.batch_id,
                status=TaskStatus.RUNNING,
                progress=int(((item.index + 1) / batch_state.total) * 100),
                message=f"Processing {item.index + 1}/{batch_state.total}: {item.prompt[:40]}",
                metadata={
                    "batch_id": batch_state.batch_id,
                    "path": "b",
                    "batch_total": batch_state.total,
                    "batch_completed": batch_state.completed,
                    "batch_failed": batch_state.failed,
                    "current_item": {
                        "index": item.index,
                        "task_id": item.task_id,
                        "prompt": item.prompt,
                    },
                },
                updated_at=time.time(),
            )
            await broadcast(batch_state.batch_id, batch_msg)

            try:
                result = await engine.run_path_b(
                    item.task_id,
                    item.prompt,
                    item.extra.get("tts_text", "Hello world"),
                    duration=item.extra.get("duration", 10.0),
                    tts_language=item.extra.get("tts_language", "zh"),
                    reference_audio_b64=item.extra.get("reference_audio_b64"),
                )
                item.status = result.status.value if result else "failed"
                if result and result.status == TaskStatus.COMPLETED:
                    batch_state.completed += 1
                else:
                    batch_state.failed += 1
            except Exception as exc:
                logger.error("Batch item %d failed: %s", item.index, exc)
                item.status = "failed"
                batch_state.failed += 1

            batch_state.updated_at = time.time()

        batch_state.status = "completed" if batch_state.failed == 0 else "partial"
        batch_state.updated_at = time.time()

        await broadcast(
            batch_state.batch_id,
            PredictResult(
                task_id=batch_state.batch_id,
                status=TaskStatus.COMPLETED if batch_state.failed == 0 else TaskStatus.FAILED,
                progress=100,
                message=f"Batch complete: {batch_state.completed} succeeded, {batch_state.failed} failed",
                metadata={
                    "batch_id": batch_state.batch_id,
                    "path": "b",
                    "batch_total": batch_state.total,
                    "batch_completed": batch_state.completed,
                    "batch_failed": batch_state.failed,
                    "items": [
                        {
                            "index": it.index,
                            "task_id": it.task_id,
                            "prompt": it.prompt,
                            "status": it.status,
                        }
                        for it in batch_state.items
                    ],
                },
                updated_at=time.time(),
            ),
        )

        async with batch_queue._lock:
            if batch_queue._running is batch_state:
                batch_queue._running = None
                if batch_queue._queue:
                    next_batch = batch_queue._queue.pop(0)
                    batch_queue._running = next_batch
                    asyncio.create_task(batch_queue._execute_batch(next_batch, run_fn, broadcast))

    asyncio.create_task(_run_batch_b(batch, lambda *a, **k: None, _websocket_broadcast))

    return {
        "batch_id": batch.batch_id,
        "path": "b",
        "total": batch.total,
        "status": batch.status,
        "websocket": f"/ws/progress/{batch.batch_id}",
    }


@app.get("/api/v1/batch/status/{batch_id}", tags=["batch"])
async def batch_status(batch_id: str):
    """Get current status of a batch job."""
    state = batch_queue.get_state(batch_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")

    return {
        "batch_id": state.batch_id,
        "path": state.path,
        "total": state.total,
        "completed": state.completed,
        "failed": state.failed,
        "current_index": state.current_index,
        "status": state.status,
        "error": state.error,
        "created_at": state.created_at,
        "updated_at": state.updated_at,
    }


# ---------------------------------------------------------------------------
# Workflow endpoints — Paths A / B / C
# ---------------------------------------------------------------------------


# Global workflow engine instance (initialized lazily)
_workflow_engine: Optional[WorkflowEngine] = None


def _get_workflow_engine() -> WorkflowEngine:
    """Get or create the global workflow engine."""
    global _workflow_engine
    if _workflow_engine is None:
        _workflow_engine = WorkflowEngine(
            broadcast=_websocket_broadcast,
            musicgen_url=_config.get("music", {}).get("space_url"),
            tts_url=_config.get("tts", {}).get("space_url"),
            demucs_url=_config.get("demucs", {}).get("space_url"),
            musicgen_token=_config.get("music", {}).get("api_token"),
            tts_token=_config.get("tts", {}).get("api_token"),
            demucs_token=_config.get("demucs", {}).get("api_token"),
            use_mock=(WORKFLOW_MODE == "mock"),
        )
    return _workflow_engine


@app.post("/api/v1/workflow/a", tags=["workflows"])
async def workflow_path_a(request: Request):
    """
    Path A: Suno-style — one-click music generation.

    Body::
        {
            "task_id": "abc123",
            "prompt": "upbeat electronic dance music",
            "duration": 10.0,
            "temperature": 0.8
        }

    Returns a task_id. Connect to WS to track progress.
    On completion, metadata.tracks contains the generated music track.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    task_id = body.get("task_id") or str(uuid.uuid4())[:8]
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


@app.post("/api/v1/workflow/b", tags=["workflows"])
async def workflow_path_b(request: Request):
    """
    Path B: Hybrid — MusicGen background + TTS vocals.

    Body::
        {
            "task_id": "abc123",
            "prompt": "chill lofi hip hop beat",
            "tts_text": "今天天气真好",
            "tts_language": "zh",
            "reference_audio": "<base64 wav>",  // optional in mock mode
            "duration": 10.0
        }

    Returns a task_id. On completion, metadata.tracks contains
    two tracks: music bed and vocals.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    task_id = body.get("task_id") or str(uuid.uuid4())[:8]
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


@app.post("/api/v1/workflow/c", tags=["workflows"])
async def workflow_path_c(request: Request):
    """
    Path C: Remix — upload audio → Demucs stem separation.

    Body::
        {
            "task_id": "abc123",
            "audio_base64": "<base64 wav>",
            "stem_count": "4",       // "4" or "6"
            "remove_reverb": false
        }

    Returns a task_id. On completion, metadata.tracks contains
    individual stem tracks (vocals, drums, bass, other).
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    task_id = body.get("task_id") or str(uuid.uuid4())[:8]
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


async def _run_workflow_async(coroutine_fn, *args, **kwargs) -> None:
    """Helper: run a workflow coroutine in background and catch exceptions."""
    logger.info("Workflow task starting: %s(%s, %s)", coroutine_fn.__name__, args, kwargs)
    try:
        await coroutine_fn(*args, **kwargs)
        logger.info("Workflow task completed: %s", coroutine_fn.__name__)
    except Exception as e:
        logger.exception("Workflow task failed: %s", e)


# ---------------------------------------------------------------------------
# Audio trim endpoint
# ---------------------------------------------------------------------------


@app.get("/api/v1/audio/trim", tags=["audio"])
async def trim_audio_endpoint(
    url: str,
    start: float = 0.0,
    end: Optional[float] = None,
    duration: Optional[float] = None,
    fmt: str = "wav",
):
    """
    Trim audio from a URL or local path.

    Args:
        url: Path or URL to the source audio file.
        start: Start time in seconds (default 0).
        end: End time in seconds. Required if duration not provided.
        duration: Duration in seconds. Alternative to `end`.
        fmt: Output format (wav, mp3). Default wav.

    Returns:
        Audio file stream with Content-Disposition: attachment.
    """
    from app.services.audio_trim import trim_audio

    if not url:
        raise HTTPException(status_code=422, detail="'url' is required")

    if end is None and duration is None:
        raise HTTPException(
            status_code=422,
            detail="'end' or 'duration' is required",
        )

    if duration is not None:
        end = start + duration

    if end is None or end <= start:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid range: start={start}, end={end}",
        )

    try:
        audio_bytes, content_type = await trim_audio(url, start, end, fmt)
        filename = f"trimmed_{int(start)}s_{int(end)}s.{fmt}"
        return Response(
            content=audio_bytes,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    except RuntimeError as exc:
        logger.error("Trim failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.exception("Trim error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Task status endpoint
# ---------------------------------------------------------------------------


@app.get("/api/v1/tasks/{task_id}", tags=["predictions"])
async def get_task_status(task_id: str):
    """
    Get current WebSocket subscriber info for a task.

    Note: Real-time status is pushed via WebSocket broadcast.
    This endpoint shows how many clients are currently subscribed.
    """
    return {
        "task_id": task_id,
        "subscribers": manager.subscriber_count,
        "active_tasks": manager.active_tasks,
    }


# ---------------------------------------------------------------------------
# Startup / Shutdown hooks
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def on_startup():
    """Log available services on startup."""
    logger.info("Inference Service API starting up")
    logger.info("Registered service types: %s", list(_SERVICE_REGISTRY.keys()))
    logger.info("OpenAPI docs available at: /docs")
    logger.info("WebSocket progress endpoint: /ws/progress/{task_id}")
    logger.info("Mock test endpoint: POST /api/v1/mock/run")
    logger.info("MusicGen endpoint: POST /api/v1/music/run")
    logger.info("Workflow endpoints: POST /api/v1/workflow/{a|b|c}")
    logger.info("Batch endpoints: POST /api/v1/batch/{a|b}, GET /api/v1/batch/status/{id}")
    logger.info("TTS_BACKEND_MODE=%s WORKFLOW_MODE=%s", TTS_BACKEND_MODE, WORKFLOW_MODE)


@app.on_event("shutdown")
async def on_shutdown():
    """Cleanup resources on shutdown."""
    logger.info("Inference Service API shutting down")
    factory.invalidate()


# ---------------------------------------------------------------------------
# Root endpoint
# ---------------------------------------------------------------------------


@app.get("/", tags=["operations"])
async def root():
    """API root — returns basic info."""
    return {
        "name": "Inference Service API",
        "version": "3.0.0",
        "docs": "/docs",
        "health": "/health",
        "predict": "/api/v1/predict/{tts|music|video|mock}",
        "music_run": "/api/v1/music/run",
        "workflow_a": "/api/v1/workflow/a  (Suno-style: prompt→music)",
        "workflow_b": "/api/v1/workflow/b  (Hybrid: music+TTS)",
        "workflow_c": "/api/v1/workflow/c  (Remix: upload→stems)",
        "websocket": "/ws/progress/{task_id}",
        "mock_run": "/api/v1/mock/run",
    }
