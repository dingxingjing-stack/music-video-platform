"""
Batch Queue — Sequential task execution for workflow paths.

Accepts a list of prompts/inputs and executes them sequentially
via the WorkflowEngine, broadcasting progress for each sub-task
under a single batch task_id.

Usage:
    POST /api/v1/batch/a — Batch Path A (MusicGen)
    POST /api/v1/batch/b — Batch Path B (Hybrid)
    GET  /api/v1/batch/status/{batch_id} — Check batch progress
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from app.services.inference.base import (
    PredictRequest,
    PredictResult,
    TaskStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class BatchItem:
    """A single item in a batch queue."""
    index: int
    task_id: str
    prompt: str
    extra: dict[str, Any] = field(default_factory=dict)
    status: str = "queued"
    result: Optional[PredictResult] = None


@dataclass
class BatchState:
    """Mutable state for a running batch."""
    batch_id: str
    path: str
    total: int
    items: list[BatchItem] = field(default_factory=list)
    completed: int = 0
    failed: int = 0
    current_index: int = -1
    status: str = "queued"
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class BatchQueue:
    """
    Global batch queue manager.

    Supports one running batch at a time. Additional batches
    are queued and executed sequentially.
    """

    def __init__(self) -> None:
        self._running: Optional[BatchState] = None
        self._queue: list[BatchState] = []
        self._states: dict[str, BatchState] = {}
        self._lock = asyncio.Lock()

    @property
    def running(self) -> Optional[BatchState]:
        return self._running

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    def get_state(self, batch_id: str) -> Optional[BatchState]:
        return self._states.get(batch_id)

    async def submit(
        self,
        path: str,
        items: list[dict[str, Any]],
        broadcast,
    ) -> BatchState:
        """Submit a new batch. Items executed sequentially."""
        batch_id = f"batch-{uuid.uuid4().hex[:8]}"
        batch = BatchState(
            batch_id=batch_id,
            path=path,
            total=len(items),
            items=[
                BatchItem(
                    index=i,
                    task_id=f"{batch_id}-item-{i}",
                    prompt=item.get("prompt", ""),
                    extra=item.get("extra", {}),
                )
                for i, item in enumerate(items)
            ],
        )

        async with self._lock:
            if self._running:
                self._queue.append(batch)
                logger.info("Batch %s queued (position %d)", batch_id, len(self._queue))
            else:
                self._running = batch

        self._states[batch_id] = batch
        logger.info("Batch %s submitted: %d items, path=%s", batch_id, len(items), path)
        return batch

    async def _execute_batch(
        self,
        batch: BatchState,
        run_fn,
        broadcast,
    ) -> None:
        """Execute batch items sequentially."""
        batch.status = "running"
        batch.updated_at = time.time()

        for item in batch.items:
            item.status = "running"
            batch.current_index = item.index
            batch.updated_at = time.time()

            # Broadcast batch progress
            await broadcast(
                batch.batch_id,
                PredictResult(
                    task_id=batch.batch_id,
                    status=TaskStatus.RUNNING,
                    progress=int((item.index / batch.total) * 100),
                    message=f"Processing {item.index + 1}/{batch.total}: {item.prompt[:40]}",
                    metadata={
                        "batch_id": batch.batch_id,
                        "path": batch.path,
                        "batch_total": batch.total,
                        "batch_completed": batch.completed,
                        "batch_failed": batch.failed,
                        "current_item": {
                            "index": item.index,
                            "task_id": item.task_id,
                            "prompt": item.prompt,
                        },
                    },
                    updated_at=time.time(),
                ),
            )

            # Execute the individual task
            try:
                result = await run_fn(item.task_id, item.prompt, **item.extra)
                item.status = result.status.value if result else "failed"
                item.result = result

                if result and result.status == TaskStatus.COMPLETED:
                    batch.completed += 1
                else:
                    batch.failed += 1

            except Exception as exc:
                logger.error("Batch item %d failed: %s", item.index, exc)
                item.status = "failed"
                batch.failed += 1

            batch.updated_at = time.time()

        # Batch complete
        batch.status = "completed" if batch.failed == 0 else "partial"
        if batch.failed > 0:
            batch.status = "partial"
        batch.updated_at = time.time()

        # Final broadcast
        await broadcast(
            batch.batch_id,
            PredictResult(
                task_id=batch.batch_id,
                status=TaskStatus.COMPLETED if batch.failed == 0 else TaskStatus.FAILED,
                progress=100,
                message=f"Batch complete: {batch.completed} succeeded, {batch.failed} failed",
                metadata={
                    "batch_id": batch.batch_id,
                    "path": batch.path,
                    "batch_total": batch.total,
                    "batch_completed": batch.completed,
                    "batch_failed": batch.failed,
                    "items": [
                        {
                            "index": it.index,
                            "task_id": it.task_id,
                            "prompt": it.prompt,
                            "status": it.status,
                        }
                        for it in batch.items
                    ],
                },
                updated_at=time.time(),
            ),
        )

        # Move to running = None, check queue
        async with self._lock:
            if self._running is batch:
                self._running = None
                if self._queue:
                    next_batch = self._queue.pop(0)
                    self._running = next_batch
                    asyncio.create_task(
                        self._execute_batch(next_batch, run_fn, broadcast)
                    )
                    logger.info("Started next batch from queue: %s", next_batch.batch_id)

    async def dequeue_next(self) -> None:
        """Manually start the next batch from queue (called after current finishes)."""
        async with self._lock:
            if not self._running and self._queue:
                self._running = self._queue.pop(0)
                logger.info("Dequeuing next batch: %s", self._running.batch_id)


# Global singleton
batch_queue = BatchQueue()
