"""
Mock Inference Service — simulates a real inference task with progressive
status updates for WebSocket broadcast testing.

Emulates a realistic lifecycle:
  PENDING → LOADING → RUNNING (0%→95%) → COMPLETED (100%)

Each progress tick is broadcast via the injected callback so the
WebSocket client on the frontend receives real-time updates.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

from .base import (
    BaseInferenceService,
    PredictRequest,
    PredictResult,
    RetryConfig,
    TaskStatus,
)

logger = logging.getLogger(__name__)


class MockInferenceService(BaseInferenceService):
    """
    Simulated inference service for frontend WebSocket testing.

    Usage::

        from app.services.inference.mock import MockInferenceService

        svc = MockInferenceService(
            service_type="tts",       # cosmetic: shown in result metadata
            duration=10.0,            # total simulated time (seconds)
            tick_interval=1.0,        # progress update interval
        )
        result = await svc.predict(PredictRequest(...))
    """

    def __init__(
        self,
        service_type: str = "mock",
        *,
        duration: float = 10.0,
        tick_interval: float = 1.0,
        space_url: str = "http://localhost:9999/mock",
        api_token: Optional[str] = None,
        retry_config: Optional[RetryConfig] = None,
        broadcast: Optional[Callable[..., Any]] = None,
        http_timeout: float = 600.0,
    ) -> None:
        super().__init__(
            space_url=space_url,
            api_token=api_token,
            retry_config=retry_config or RetryConfig(
                max_cold_start_retries=0,  # skip cold-start
                max_network_retries=0,     # skip network retry
            ),
            broadcast=broadcast,
            http_timeout=http_timeout,
        )
        self.service_type = service_type
        self.duration = duration
        self.tick_interval = tick_interval

    # ------------------------------------------------------------------
    # Abstract method stubs (not used — predict() is overridden)
    # ------------------------------------------------------------------

    def _build_payload(self, **kwargs) -> dict[str, Any]:
        return {}

    async def _do_submit(
        self,
        task_id: str,
        payload: dict[str, Any],
    ) -> Optional[str]:
        return None

    def _parse_response(self, event_data: dict[str, Any]) -> Optional[dict[str, Any]]:
        return None

    # ------------------------------------------------------------------
    # Simulated predict lifecycle
    # ------------------------------------------------------------------

    async def predict(self, request: PredictRequest) -> PredictResult:
        """
        Simulate a real inference task with progressive WebSocket broadcasts.

        Timeline:
          t=0     PENDING    (0%)   — "Task queued"
          t=tick  LOADING    (10%)  — "Model loading..."
          t=2tick RUNNING    (20%)  — "Inference in progress..."
          ...     RUNNING    (20%→95%)
          t=end   COMPLETED  (100%) — "Done!"
        """
        task_id = request.task_id
        total_ticks = max(1, int(self.duration / self.tick_interval))
        progress_per_tick = 95 // total_ticks  # cap at 95% during RUNNING

        # ── Phase 0: Pending ──────────────────────────────────────
        result = PredictResult(
            task_id=task_id,
            status=TaskStatus.PENDING,
            progress=0,
            message="Task queued",
            metadata={"service_type": self.service_type, "simulated": True},
        )
        await self._report(result)
        await asyncio.sleep(self.tick_interval)

        # ── Phase 1: Loading (cold-start simulation) ─────────────
        result = PredictResult(
            task_id=task_id,
            status=TaskStatus.LOADING,
            progress=10,
            message="Model loading into VRAM...",
            metadata={"service_type": self.service_type, "simulated": True},
        )
        await self._report(result)
        await asyncio.sleep(self.tick_interval)

        # ── Phase 2: Running — progressive progress ──────────────
        for i in range(total_ticks):
            prog = min(20 + i * progress_per_tick, 95)
            result = PredictResult(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                progress=prog,
                message=f"Inference in progress... ({prog}%)",
                metadata={
                    "service_type": self.service_type,
                    "simulated": True,
                    "tick": i + 1,
                    "total_ticks": total_ticks,
                },
            )
            await self._report(result)
            await asyncio.sleep(self.tick_interval)

        # ── Phase 3: Completed ───────────────────────────────────
        result = PredictResult(
            task_id=task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message="Done!",
            result_url=f"http://localhost:8000/results/{task_id}/output",
            metadata={
                "service_type": self.service_type,
                "simulated": True,
                "total_duration": self.duration,
            },
        )
        await self._report(result)
        return result
