"""
AI Routes — RunPod Smoke Test (auth temporarily commented for POC)
对应任务1: @router.post("/ai/runpod-smoke-test") 鉴权已注释，保留业务逻辑
"""

from __future__ import annotations

import time
import logging
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.services.runpod_provider import run_smoke_test, RunPodError, get_runpod_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["runpod"])


class SmokeTestResponse(BaseModel):
    status: str
    job_id: str
    output: Any = None
    latency: int
    endpoint_id: Optional[str] = None


@router.post("/ai/runpod-smoke-test", response_model=SmokeTestResponse)
async def runpod_smoke_test(
    request: Request,
    x_runpod_smoke_token: Optional[str] = Header(None, alias="X-RunPod-Smoke-Token"),
):
    """
    RunPod 健康检查业务逻辑（鉴权已注释，保留恢复标记）
    """
    cfg = get_runpod_config()
    expected = cfg["smoke_token"]
    if not expected:
        logger.warning("RunPod smoke token not configured")
        raise HTTPException(status_code=503, detail="RUNPOD_SMOKE_TEST_TOKEN not configured")
    if not x_runpod_smoke_token or x_runpod_smoke_token != expected:
        raise HTTPException(status_code=401, detail="Invalid X-RunPod-Smoke-Token")

    if not cfg["endpoint_id"]:
        raise HTTPException(status_code=503, detail="RUNPOD_ENDPOINT_ID not configured")
    if not cfg["api_key"]:
        raise HTTPException(status_code=503, detail="RUNPOD_API_KEY not configured")

    try:
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    extra_input = body.get("input") if isinstance(body.get("input"), dict) else None

    t0 = time.monotonic()
    try:
        result = await run_smoke_test(timeout=30.0, extra_input=extra_input)
    except RunPodError as exc:
        code = exc.status_code or 502
        detail: Any = str(exc)
        if exc.body is not None:
            detail = {"error": str(exc), "runpod_body": exc.body if isinstance(exc.body, (dict, list)) else str(exc.body)[:1000]}
        if code in (401, 403):
            code = 502
        raise HTTPException(status_code=code, detail=detail)
    except Exception as exc:
        logger.exception("RunPod smoke unexpected error")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}")

    return SmokeTestResponse(
        status=result.get("status", "unknown"),
        job_id=result.get("job_id", ""),
        output=result.get("output"),
        latency=result.get("latency", int((time.monotonic() - t0) * 1000)),
        endpoint_id=cfg["endpoint_id"],
    )
