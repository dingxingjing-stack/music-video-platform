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
from app.services.inference.llm_factory import llm_factory
# Note: WorkflowEngine, batch_queue, RemixService are now loaded via dedicated routers
# from app.services.workflow import WorkflowEngine
# from app.services.batch_queue import batch_queue
# from app.services.inference.remix import RemixService
from app.websocket_manager import ConnectionManager, manager

# ---------- Router imports (moved to dedicated modules) ----------
from app.services.mv_router import router as mv_app
from app.services.workflow_router import router as workflow_app
from app.services.batch_router import router as batch_app
from app.services.user_router import router as user_app
from app.services.audio_router import router as audio_app
from app.middleware.privacy import PrivacyMiddleware

# ---------- Social system router ----------
from app.routers.social import router as social_app

# ---------- Collaboration system router ----------
from app.routers.collaboration import router as collab_app

# ---------- Copyright check router ----------
from app.routers.copyright import router as copyright_app

# ---------- Notification system router ----------
from app.routers.notifications import router as notif_app

# ---------- Messaging system router ----------
from app.routers.messages import router as msg_app

# ---------- Subscription system router ----------
from app.routers.subscription import router as sub_app

# ---------- Asset store router ----------
from app.routers.asset_store import router as store_app

# ---------- Copyright detection router ----------
from app.routers.copyright import router as copyright_app

# ---------- Audio quality test router ----------
from app.routers.audio_quality import router as audio_quality_app

# ---------- UGC submission router ----------
from app.routers.ugc import router as ugc_app

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

# ---------- 合规中间件 ----------
app.add_middleware(PrivacyMiddleware)

# ---------- router 挂载 ----------
# 开发阶段：使用 Gemini 临时方案（免费额度）
# 生产阶段：使用 ai_music (Agnes AI 主力 + Gemini 备用 + Mureka 音频)
from app.routers import ai_music
from app.routers import hf_music
from app.routers import stems_export
from app.routers import community
from app.routers import pitch_correction
from app.routers import chord_track
from app.routers import comping
from app.routers import time_stretch
from app.routers import remix_engine
from app.routers import voice_clone
from app.routers import ai_lyrics
from app.routers import audio_processing
from app.routers import song_continuation
from app.routers import subtitle_recognition
from app.routers import one_click_publish
app.include_router(mv_app,       prefix="/api/v1/mv")
app.include_router(workflow_app, prefix="/api/v1/workflow")
app.include_router(batch_app,    prefix="/api/v1/batch")
app.include_router(hf_music.router, prefix="/api/v1/ai-hf")
app.include_router(ai_music.router)
app.include_router(user_app,    prefix="/api/v1/user")
app.include_router(audio_app,   prefix="/api/v1/audio")
app.include_router(stems_export.router)
app.include_router(community.router)
app.include_router(pitch_correction.router)
app.include_router(chord_track.router)
app.include_router(comping.router)
app.include_router(time_stretch.router)
app.include_router(remix_engine.router)
app.include_router(voice_clone.router, prefix="/api/v1")
app.include_router(ai_lyrics.router)
app.include_router(audio_processing.router, prefix="/api/v1/audio")
app.include_router(song_continuation.router)
app.include_router(subtitle_recognition.router)
app.include_router(one_click_publish.router)
app.include_router(social_app)
app.include_router(collab_app)
app.include_router(copyright_app)
app.include_router(notif_app)
app.include_router(msg_app)
app.include_router(sub_app)
app.include_router(store_app)
app.include_router(copyright_app)
app.include_router(audio_quality_app)
app.include_router(ugc_app)

# ---------- Rhythm analysis router (P0-6 节拍检测) ----------
from app.routers.rhythm_analysis import router as rhythm_app
app.include_router(rhythm_app, prefix="/api/v1/beat")

# ---------- CDN upload router (P0-8 CDN 集成) ----------
from app.routers.cdn_upload import router as cdn_app
app.include_router(cdn_app, prefix="/api/v1/cdn")

# ---------- BG removal router (P1-7 智能抠图) ----------
from app.routers.bg_removal import router as bg_app
app.include_router(bg_app, prefix="/api/v1/bg")

# ---------- Lyrics rhyme AI router (P3-7 歌词押韵) ----------
from app.routers.lyrics_rhyme import router as lyrics_app
app.include_router(lyrics_app, prefix="/api/v1/lyrics")

# ---------- Supabase 认证路由 ----------
from app.routers.auth import router as auth_app
app.include_router(auth_app)

# ---------- Supabase 歌曲管理路由 ----------
from app.routers.songs import router as songs_app
app.include_router(songs_app)


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
            # When *_FORCE_MOCK is set, skip remote probing and report healthy directly
            force_key = f"{service_type.upper()}_FORCE_MOCK"
            mock_key = f"{service_type.upper()}_BACKEND_MODE"
            if os.getenv(force_key, "").strip().lower() == "true" or os.getenv(mock_key, "").strip().lower() == "mock":
                services_health[service_type] = {"healthy": True, "message": f"Mock {service_type} service ready"}
                continue
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
# Service status endpoint — 显示所有外部服务的配置状态
# ---------------------------------------------------------------------------


@app.get("/api/v1/services/status", tags=["operations"])
async def services_status():
    """
    获取所有外部服务的配置和连通性状态。

    用于前端/运维快速排查：哪些服务已配置、哪些正常、哪些降级。
    """
    services = [
            {"name": "agnes", "label": "Agnes AI (主力文本模型)", "env_var": "AGNES_API_KEY",
             "description": "歌词生成、文案优化、MV 概念生成（主力，永久免费无限额度）", "category": "llm"},
            {"name": "gemini", "label": "Gemini AI (备用文本接口)", "env_var": "GEMINI_API_KEY",
             "description": "备用 LLM，当 Agnes 不可用时切换", "category": "llm"},
            {"name": "huggingface", "label": "Hugging Face (音频生成)", "env_var": "HF_TOKEN",
         "description": "MusicGen / ACE-Step / YuE 音乐生成", "category": "audio"},
        {"name": "mureka", "label": "Mureka API (商业级音乐生成)", "env_var": "MUREKA_API_KEY",
         "description": "商业级音乐生成、录取、扒带", "category": "audio"},
        {"name": "nvidia_nvapi", "label": "NVIDIA NVAPI (LLM/音乐生成)", "env_var": "NVIDIA_API_KEY",
         "description": "备用 LLM、音乐生成", "category": "llm"},
        {"name": "supabase", "label": "Supabase (数据库/存储/认证)", "env_var": "SUPABASE_URL",
         "description": "PostgreSQL 数据库、Auth 认证、文件存储", "category": "database"},
        {"name": "cloudflare_r2", "label": "Cloudflare R2 (对象存储)", "env_var": "CLOUDFLARE_R2_ACCOUNT_ID",
         "description": "音频/视频文件存储", "category": "storage"},
        {"name": "resend", "label": "Resend (邮件服务)", "env_var": "RESEND_API_KEY",
         "description": "事务性邮件、验证码、通知", "category": "notification"},
        {"name": "sentry", "label": "Sentry (错误监控)", "env_var": "SENTRY_DSN",
         "description": "异常捕获、性能监控、告警", "category": "monitoring"},
        {"name": "creatomate", "label": "Creatomate (视频渲染)", "env_var": "CREATOMATE_API_KEY",
         "description": "MV 模板渲染、视频合成", "category": "video"},
        {"name": "runwayml", "label": "RunwayML (AI 视频特效)", "env_var": "RUNWAYML_API_KEY",
         "description": "视频生成、背景移除、特效", "category": "video"},
    ]

    results = []
    for svc in services:
        env_value = os.getenv(svc["env_var"], "")
        is_configured = bool(env_value and env_value.strip() and not env_value.startswith("your_"))
        results.append({
            "name": svc["name"], "label": svc["label"], "category": svc["category"],
            "description": svc["description"], "configured": is_configured,
            "env_var": svc["env_var"],
            "status": "configured" if is_configured else "not_configured"
        })

    configured_count = sum(1 for r in results if r["configured"])

    return {
        "total": len(results),
        "configured": configured_count,
        "not_configured": len(results) - configured_count,
        "services": results,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


# ---------------------------------------------------------------------------
    # LLM endpoints — Text generation (prompts, lyrics, MV concepts, etc.)
# ---------------------------------------------------------------------------


from pydantic import BaseModel, Field
from typing import List, Optional, AsyncGenerator
from fastapi.responses import StreamingResponse


class LLMMessage(BaseModel):
    role: str = Field(..., description="Role: system, user, or assistant")
    content: str = Field(..., description="Message content")


class LLMRequest(BaseModel):
    messages: List[LLMMessage] = Field(..., description="Conversation messages")
    provider: str = Field("auto", description="Provider: auto, nvidia, gemini")
    model: Optional[str] = Field(None, description="Specific model name")
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(2048, ge=1, le=8192)
    stream: bool = Field(False, description="Stream response as SSE")


class LLMResponse(BaseModel):
    text: str
    provider: str
    model: str


@app.post("/api/v1/llm/generate", tags=["llm"], response_model=LLMResponse)
async def llm_generate(request: LLMRequest):
    """
    Generate text using LLM (NVIDIA Nemotron / Gemini with auto-fallback).

    Use cases:
      - Expand/improve music prompts
      - Generate lyrics from theme
      - Generate MV concepts from audio analysis
      - Any text-to-text generation
    """
    try:
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        text = await llm_factory.call(
            messages=messages,
            provider=request.provider,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=False,
        )
        return LLMResponse(text=text, provider=request.provider, model=request.model or "auto")
    except Exception as exc:
        logger.exception("LLM generation failed")
        raise HTTPException(status_code=500, detail=f"LLM generation failed: {exc}")


@app.post("/api/v1/llm/stream", tags=["llm"])
async def llm_stream(request: LLMRequest):
    """
    Stream LLM response as Server-Sent Events (SSE).

    Returns: text/event-stream with each chunk as 'data: <text>\n\n'
    """
    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for chunk in llm_factory.call(
                messages=messages,
                provider=request.provider,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=True,
            ):
                yield f"data: {chunk}\n\n"
        except Exception as exc:
            logger.exception("LLM streaming failed")
            yield f"data: [ERROR] {exc}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/v1/llm/health", tags=["llm"])
async def llm_health():
    """Check LLM provider availability."""
    results = {}
    for name, client in llm_factory.clients.items():
        try:
            # Quick health check with a tiny request
            resp = await client.post(
                llm_factory._get_endpoint(name, MODELS[name]["model_default"]),
                json=llm_factory._build_payload(name, [{"role": "user", "content": "hi"}], MODELS[name]["model_default"], 0.1, 10, False),
            )
            results[name] = {"healthy": resp.status_code == 200, "status": resp.status_code}
        except Exception as exc:
            results[name] = {"healthy": False, "error": str(exc)[:200]}
    return {"providers": results}


# Need MODELS dict for health check - import from llm_factory
from app.services.inference.llm_factory import MODELS


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
            asyncio.create_task(run_tts_and_save(
                svc=svc, task_id=task_id, audio_bytes=audio_bytes,
                text=text, language=language, opt_filename=opt_filename,
                results_dir=RESULTS_DIR,
            ))
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


from app.services.task_handlers import run_tts_and_save, run_musicgen_and_save




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

        asyncio.create_task(run_musicgen_and_save(
            svc=svc, task_id=task_id, prompt=prompt,
            duration=duration, temperature=temperature,
            results_dir=RESULTS_DIR,
        ))

    return {
        "task_id": task_id,
        "status": "started",
        "websocket": f"/ws/progress/{task_id}",
    }


# ---------------------------------------------------------------------------
# Batch endpoints — Sequential multi-prompt generation
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
# Copyright Watermark endpoints — fingerprint + blind watermark
# ---------------------------------------------------------------------------


from app.services.watermark import (
    AudioFingerprintService,
    BlindWatermarkService,
    WatermarkPayload,
)


@app.get("/api/v1/watermark/fingerprint", tags=["watermark"])
async def fingerprint_audio(url: str):
    """
    Extract spectral fingerprint from audio URL.
    Returns MFCC hash, chroma hash, spectral stats.
    """
    # Download audio to temp file
    import tempfile as tmpf
    import httpx

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Failed to fetch audio: {resp.status_code}")

        with tmpf.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            tf.write(resp.content)
            tmp_path = tf.name

    try:
        fingerprint = await AudioFingerprintService.extract(tmp_path)
        if fingerprint is None:
            raise HTTPException(status_code=422, detail="Failed to extract fingerprint — audio too short or codec unsupported")
        return fingerprint.to_dict()
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@app.post("/api/v1/watermark/embed", tags=["watermark"])
async def embed_watermark(request: Request):
    """
    Embed a blind watermark into audio.
    Returns a watermarked audio file (base64).

    Body:
        {
            "audio_url": "...",
            "owner_id": "user-123",
            "project_id": "proj-456"
        }
    """
    body = await request.json()

    audio_url = body.get("audio_url", "")
    owner_id = body.get("owner_id", "anonymous")
    project_id = body.get("project_id", "unknown")

    if not audio_url:
        raise HTTPException(status_code=422, detail="audio_url is required")

    # Download source audio
    import tempfile as tmpf
    import httpx

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(audio_url)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Failed to fetch audio: {resp.status_code}")

        with tmpf.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            tf.write(resp.content)
            src_path = tf.name

    out_path = src_path + "_wm.wav"

    try:
        # Get fingerprint first
        fp = await AudioFingerprintService.extract(src_path)

        payload = WatermarkPayload(
            owner_id=owner_id,
            project_id=project_id,
            timestamp=str(int(time.time())),
            rights="all_rights_reserved",
            signature=fp.composite_id if fp else "",
        )

        ok = await BlindWatermarkService.embed(src_path, payload, out_path)

        if not ok:
            raise HTTPException(status_code=500, detail="Blind watermark embed failed")

        # Read result as base64
        with open(out_path, "rb") as f:
            result_bytes = f.read()

        import base64
        b64 = base64.b64encode(result_bytes).decode()

        return {
            "fingerprint": fp.to_dict() if fp else None,
            "watermark": payload.to_dict(),
            "watermarked": True,
            "content_type": "audio/wav",
            "data": f"data:audio/wav;base64,{b64}",
            "composite_id": fp.composite_id if fp else None,
        }
    finally:
        for path in (src_path, out_path):
            try:
                os.unlink(path)
            except Exception:
                pass


@app.post("/api/v1/watermark/extract", tags=["watermark"])
async def extract_watermark(request: Request):
    """
    Extract and decode a blind watermark from audio.
    Returns the WatermarkPayload if found.

    Body:
        {
            "audio_url": "..."
        }
    """
    body = await request.json()
    audio_url = body.get("audio_url", "")

    if not audio_url:
        raise HTTPException(status_code=422, detail="audio_url is required")

    import tempfile as tmpf
    import httpx

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(audio_url)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Failed to fetch audio: {resp.status_code}")

        with tmpf.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            tf.write(resp.content)
            tmp_path = tf.name

    try:
        payload = await BlindWatermarkService.extract(tmp_path)
        if payload is None:
            return {"found": False, "message": "No watermark detected"}

        return {
            "found": True,
            "watermark": payload.to_dict(),
        }
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@app.post("/api/v1/watermark/apply", tags=["watermark"])
async def watermark_apply(request: Request):
    """
    Combined fingerprint + embed in one call.
    """
    body = await request.json()

    audio_url = body.get("audio_url", "")
    owner_id = body.get("owner_id", "anonymous")
    project_id = body.get("project_id", "unknown")

    if not audio_url:
        raise HTTPException(status_code=422, detail="audio_url is required")

    from app.services.watermark import fingerprint_and_watermark

    import tempfile as tmpf
    import httpx

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(audio_url)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Failed to fetch audio: {resp.status_code}")

        with tmpf.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            tf.write(resp.content)
            tmp_path = tf.name

    try:
        result = await fingerprint_and_watermark(tmp_path, owner_id, project_id)

        if result.get("watermarked"):
            with open(result["watermarked_path"], "rb") as f:
                import base64
                b64 = base64.b64encode(f.read()).decode()
            result["data"] = f"data:audio/wav;base64,{b64}"

        return result
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        if result.get("watermarked_path"):
            try:
                os.unlink(result["watermarked_path"])
            except Exception:
                pass


# ---------------------------------------------------------------------------
# AI Lyrics generation endpoint
# ---------------------------------------------------------------------------


@app.post("/api/v1/lyrics/generate", tags=["lyrics"])
async def generate_lyrics(request: Request):
    """Generate structured lyrics via LLM. Body: prompt, style, language, line_count."""
    body = await request.json()
    prompt = body.get("prompt", "")
    style = body.get("style", "pop")
    language = body.get("language", "zh")
    line_count = int(body.get("line_count", 24))

    if not prompt:
        raise HTTPException(status_code=422, detail="'prompt' is required")

    system_prompt = (
        f"You are a lyricist. Write lyrics as JSON. Language: {language}. Style: {style}. "
        "Return ONLY: {\"lines\":[{\"time\":<seconds>,\"text\":\"...\"}]}. "
        "Make time values evenly spaced across ~3-4 minutes. Include [Verse], [Chorus] markers."
    )
    user_prompt = f"Write a {style} song about: {prompt}. ~{line_count} lines. Language: {language}."
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        raw = await llm_factory.call(messages=messages, temperature=0.8, max_tokens=2048)
        return _parse_lyric_response(raw, style, language)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"LLM unavailable: {e}")
    except Exception as e:
        logger.exception("Lyrics generation failed")
        raise HTTPException(status_code=500, detail=str(e))


def _parse_lyric_response(raw: str, style: str, language: str) -> dict:
    import json as _json, re
    cleaned = raw.strip()
    cleaned = re.sub(r'^```(?:json)?\s*\n', '', cleaned)
    cleaned = re.sub(r'\n```\s*$', '', cleaned)
    try:
        parsed = _json.loads(cleaned)
        if isinstance(parsed, dict) and "lines" in parsed:
            return {"lyric_lines": parsed["lines"], "metadata": {"style": style, "language": language, "generated_by": "llm"}, "raw_lrc": _lines_to_lrc(parsed["lines"])}
    except (_json.JSONDecodeError, KeyError):
        pass
    # Fallback plain text
    lyric_lines: list[dict] = []
    for i, line in enumerate(raw.strip().split("\n")):
        line = line.strip()
        if not line: continue
        m = re.match(r'\[(\d{2}):(\d{2})(?:\.(\d+))?\]\s*(.+)', line)
        if m:
            t = int(m.group(1))*60 + int(m.group(2)) + (int(m.group(3).ljust(3,"0")[:3])/1000 if m.group(3) else 0)
            lyric_lines.append({"time": t, "text": m.group(4).strip()})
        elif re.match(r'\[[A-Za-z ]+\]', line):
            lyric_lines.append({"time": None, "text": line})
        else:
            lyric_lines.append({"time": i * 5.0, "text": line})
    return {"lyric_lines": lyric_lines, "metadata": {"style": style, "language": language, "generated_by": "llm", "parsed_from": "text"}, "raw_lrc": _lines_to_lrc(lyric_lines)}


def _lines_to_lrc(lines: list[dict]) -> str:
    parts: list[str] = []
    for line in lines:
        t = line.get("time")
        text = line.get("text", "")
        if t is not None:
            m = int(t // 60); s = int(t % 60); ms = int((t - int(t)) * 100)
            parts.append(f"[{m:02d}:{s:02d}.{ms:02d}]{text}")
        else:
            parts.append(text)
    return "\n".join(parts)
async def mix_render(request: Request):
    """
    Render a multi-track stereo mix with per-track volume, pan, 3-band EQ,
    mute/solo, and reverb send. Runs via ffmpeg filter complex.

    Body::
        {
            "tracks": [
                {"url": "/results/...", "volume": -6.0, "pan": 0.0,
                 "eq": {"low": 2, "mid": 0, "high": -3},
                 "solo": false, "mute": false, "reverb_send": 0.3}
            ],
            "master_volume": 0.0,
            "output_format": "wav"
        }

    Returns task_id. WS /ws/progress/{task_id} streams rendering progress.
    On completion, result_url contains the mixed output file.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    tracks = body.get("tracks", [])
    if not tracks or not isinstance(tracks, list):
        raise HTTPException(status_code=422, detail="'tracks' array is required")

    task_id = f"mix-{str(uuid.uuid4())[:8]}"
    output_format = body.get("output_format", "wav")
    master_volume = float(body.get("master_volume", 0.0))

    async def _bg_mix(tid: str, trks: list, _fmt: str, _master: float) -> None:
        try:
            from app.services.mix_engine import render_mix

            await _websocket_broadcast(
                tid,
                PredictResult(
                    task_id=tid, status=TaskStatus.PENDING, progress=0,
                    message="Preparing mix...",
                ),
            )

            await _websocket_broadcast(
                tid,
                PredictResult(
                    task_id=tid, status=TaskStatus.RUNNING, progress=30,
                    message="Rendering mix with ffmpeg...",
                ),
            )

            start = time.time()
            result_path = await render_mix(
                tid, trks, RESULTS_DIR,
                output_format=_fmt,
                master_volume=_master,
            )
            elapsed = time.time() - start

            await _websocket_broadcast(
                tid,
                PredictResult(
                    task_id=tid, status=TaskStatus.COMPLETED, progress=100,
                    message="Mix exported!",
                    result_url=result_path,
                    metadata={
                        "tracks_count": len(trks),
                        "master_volume": _master,
                        "output_format": _fmt,
                        "elapsed_time": round(elapsed, 2),
                    },
                    updated_at=time.time(),
                ),
            )
        except Exception as exc:
            logger.exception("Mix render failed: %s", exc)
            await _websocket_broadcast(
                tid,
                PredictResult(
                    task_id=tid, status=TaskStatus.FAILED, progress=0,
                    error=str(exc)[:300],
                    error_code="MIX_RENDER_FAILED",
                    retryable=False,
                    updated_at=time.time(),
                ),
            )

    asyncio.create_task(_bg_mix(task_id, tracks, output_format, master_volume))

    return {
        "task_id": task_id,
        "status": "started",
        "websocket": f"/ws/progress/{task_id}",
    }


# ---------------------------------------------------------------------------
# MV helper utilities (used by mv_render and mv_detect_beats)
# ---------------------------------------------------------------------------


def _find_ffmpeg() -> str:
    import shutil
    local = os.path.join(os.path.dirname(__file__), "..", "..", "bin", "ffmpeg.exe")
    local = os.path.abspath(local)
    if os.path.exists(local):
        return local
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise RuntimeError("ffmpeg not found. Install ffmpeg or place ffmpeg.exe in bin/")


def _ffmpeg_run(cmd: list[str]) -> None:
    import subprocess
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    except subprocess.CalledProcessError as exc:
        logger.error("ffmpeg failed: %s", exc.stderr.decode(errors="replace")[:300])
        raise RuntimeError(f"ffmpeg encoding failed: {exc}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("ffmpeg encoding timed out (120s)")


def _resolve_audio_path(url: str) -> str:
    import tempfile
    if url.startswith("/results/"):
        local = os.path.join(RESULTS_DIR, os.path.basename(url))
        if os.path.exists(local):
            return local
    return url


# ---------------------------------------------------------------------------
# Remix endpoint — pitch shifting, tempo adjustment, timbre transformation
# ---------------------------------------------------------------------------


@app.post("/api/v1/remix/process", tags=["remix"])
async def remix_process(request: Request):
    """
    Submit an audio remix task (pitch shift, tempo adjustment, timbre EQ).

    Body::
        {
            "source_track_id": "track-123",
            "source_url": "/results/...",
            "pitchShift": 0,
            "tempoMultiplier": 1.0,
            "timbreTransform": "warm"
        }

    Returns a task_id. Connect to WS /ws/progress/{task_id} for progress.
    On completion, result_url contains the remixed audio.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    source_url = body.get("source_url", "")
    if not source_url:
        raise HTTPException(status_code=422, detail="'source_url' is required")

    task_id = body.get("source_track_id") or str(uuid.uuid4())[:8]
    if not task_id.startswith("remix-"):
        task_id = f"remix-{task_id}"

    local_url = source_url
    if source_url.startswith("/results/"):
        local_url = source_url

    svc = RemixService(
        results_dir=RESULTS_DIR,
        broadcast=_websocket_broadcast,
    )

    asyncio.create_task(
        svc.predict(PredictRequest(
            service_type="remix",
            task_id=task_id,
            payload={},
            extra={
                "source_track_id": body.get("source_track_id", ""),
                "source_url": local_url,
                "pitchShift": body.get("pitchShift", 0),
                "tempoMultiplier": body.get("tempoMultiplier", 1.0),
                "timbreTransform": body.get("timbreTransform", "warm"),
            },
        ))
    )

    return {
        "task_id": task_id,
        "status": "started",
        "websocket": f"/ws/progress/{task_id}",
    }


# ---------------------------------------------------------------------------
# MV Generator endpoints — beat detection + video rendering
# ---------------------------------------------------------------------------


# MV endpoints moved to app/services/mv_router.py

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
        "workflow_d": "/api/v1/workflow/d  (MIDI: project→audio)",
        "remix_process": "/api/v1/remix/process",
        "lyrics_generate": "/api/v1/lyrics/generate",
        "watermark_fingerprint": "/api/v1/watermark/fingerprint",
        "watermark_embed": "/api/v1/watermark/embed",
        "watermark_extract": "/api/v1/watermark/extract",
        "websocket": "/ws/progress/{task_id}",
        "mock_run": "/api/v1/mock/run",
    }

