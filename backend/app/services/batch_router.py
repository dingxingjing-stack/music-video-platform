"""Batch endpoints – placeholder implementation (stub).

Provides three endpoints:
  POST /a   – accepts a list of prompts for music generation (no actual processing).
  POST /b   – accepts a list of items each with `prompt` and `tts_text` (no actual processing).
  GET  /status/{task_id} – returns dummy queue/active values (always 0).

The real batch processing logic can be added later by integrating the
`app.services.batch_queue.BatchQueue` class.
"""

import logging, uuid
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# POST /a – music batch (stub)
# ---------------------------------------------------------------------------
@router.post("/a", tags=["batch"])
async def batch_path_a(request: Request):
    """Accept a list of prompts for music generation and return a task ID.

    Body (JSON):
    {
        "prompts": ["prompt 1", "prompt 2", ...],
        "temperature": 0.8,
        "duration": 10
    }
    """
    body = await request.json()
    prompts = body.get("prompts")
    if not prompts or not isinstance(prompts, list):
        raise HTTPException(status_code=422, detail="'prompts' list required")
    task_id = f"batch-{str(uuid.uuid4())[:8]}"
    logger.info("Batch A stub started: %s (prompts=%s)", task_id, len(prompts))
    # In a real implementation we would enqueue jobs here.
    return {"task_id": task_id, "status": "started", "websocket": f"/ws/progress/{task_id}"}

# ---------------------------------------------------------------------------
# POST /b – hybrid batch (stub)
# ---------------------------------------------------------------------------
@router.post("/b", tags=["batch"])
async def batch_path_b(request: Request):
    """Accept a list of items each with a prompt and tts_text.

    Body (JSON):
    {
        "items": [
            {"prompt": "...", "tts_text": "..."},
            {"prompt": "...", "tts_text": "..."}
        ],
        "temperature": 0.8,
        "tts_temperature": 0.7,
        "duration": 10
    }
    """
    body = await request.json()
    items = body.get("items")
    if not items or not isinstance(items, list):
        raise HTTPException(status_code=422, detail="'items' list required")
    task_id = f"batch-{str(uuid.uuid4())[:8]}"
    logger.info("Batch B stub started: %s (items=%s)", task_id, len(items))
    # Real implementation would enqueue each item for sequential processing.
    return {"task_id": task_id, "status": "started", "websocket": f"/ws/progress/{task_id}"}

# ---------------------------------------------------------------------------
# GET /status/{task_id}
# ---------------------------------------------------------------------------
@router.get("/status/{task_id}", tags=["batch"])
async def batch_status(task_id: str):
    """Return dummy status for a batch – always zero queue and zero active.
    This placeholder enables the endpoint to be reachable during early development.
    """
    return {"batch_id": task_id, "queue": 0, "active": 0}
