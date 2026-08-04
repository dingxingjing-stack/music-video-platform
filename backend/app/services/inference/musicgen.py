"""
MusicGen Inference Service

Handles music generation via Meta's MusicGen deployed on a Hugging Face Space.

API Assumptions:
  - Input 1: prompt (string)
  - Input 2: duration (float, default 10s)
  - Input 3: temperature (float, default 0.8)
  - Input 4: top_k (int, default 250)
  - Input 5: top_p (float, default 0.0)
  - Output: generated audio file (WAV)

  POST /api/predict (JSON, no files):
    {"session_hash": "...", "event_data": [{"data": [...]}], "fn_index": 0}

  NOTE: MusicGen-Large generates 10s clips in ~60-120s on T4 GPU.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from .base import (
    BaseInferenceService,
    BroadcastCallback,
    PredictRequest,
    PredictResult,
    RetryConfig,
    TaskStatus,
)
from .gradio_mixins import GradioSpaceMixin

logger = logging.getLogger(__name__)


class MusicGenService(GradioSpaceMixin, BaseInferenceService):
    """Music generation service backed by MusicGen on HF Spaces."""

    SERVICE_TYPE = "music"

    DEFAULT_DURATION = 10.0
    DEFAULT_TEMPERATURE = 0.8
    DEFAULT_TOP_K = 250
    DEFAULT_TOP_P = 0.0

    def __init__(
        self,
        space_url: str,
        api_token: Optional[str] = None,
        fn_index: int = 0,
        retry_config: Optional[RetryConfig] = None,
        broadcast: Optional[BroadcastCallback] = None,
        http_timeout: float = 900.0,
    ):
        super().__init__(
            space_url=space_url,
            api_token=api_token,
            retry_config=retry_config,
            broadcast=broadcast,
            http_timeout=http_timeout,
        )
        self.fn_index = fn_index

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    def _build_payload(
        self,
        prompt: str,
        *,
        duration: float = DEFAULT_DURATION,
        temperature: float = DEFAULT_TEMPERATURE,
        top_k: int = DEFAULT_TOP_K,
        top_p: float = DEFAULT_TOP_P,
    ) -> dict[str, Any]:
        """Build the Gradio prediction payload (text-only, no files)."""
        return {
            "data": [
                prompt,
                min(duration, 60.0),
                temperature,
                top_k,
                top_p,
            ]
        }

    async def _do_submit(
        self,
        task_id: str,
        payload: dict[str, Any],
    ) -> Optional[str]:
        """Submit to Gradio Space via JSON (no file upload)."""
        enriched = {
            "session_hash": self._session_hash,
            "event_data": [payload],
            "fn_index": self.fn_index,
            "batch": False,
        }

        resp = await self._submit_gradio_prediction(
            event_url=f"{self.api_base}/api/predict",
            payload=enriched,
            files=None,
        )

        if resp.get("_sleeping") or resp.get("_error"):
            return None
        return resp.get("event_url")

    def _parse_response(self, event_data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Parse Gradio event stream; return output dict on terminal events."""
        if event_data.get("type") != "process_completed":
            return None

        output_raw = event_data.get("output") if "output" in event_data else event_data.get("data", [])
        if isinstance(output_raw, list) and len(output_raw) > 0:
            first = output_raw[0]
        elif isinstance(output_raw, dict):
            first = output_raw
        else:
            return None

        if isinstance(first, dict):
            file_info = first.get("file") or first.get("url")
            if file_info:
                url = file_info.get("url") if isinstance(file_info, dict) else str(file_info)
                if url and "/" in url:
                    url = f"{self.api_base}{url}"
                return {"url": url, "filename": first.get("name", "output.wav")}
        return None

    # ------------------------------------------------------------------
    # Override _poll_events for music-specific tuning
    # ------------------------------------------------------------------

    async def _poll_events(
        self,
        event_url: str,
        task_id: str,
        *,
        remaining: float,
        poll_interval: float = 8.0,
    ) -> PredictResult:
        """Poll with slower interval suited for long music inference."""
        deadline = time.monotonic() + remaining
        poll_count = 0

        while time.monotonic() < deadline:
            poll_count += 1
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(event_url)

                if resp.status_code == 200:
                    data = resp.json() if resp.text else {}
                    events = data.get("events", [])

                    for event in events:
                        output = self._parse_response(event)
                        if output is not None:
                            return PredictResult(
                                task_id=task_id,
                                status=TaskStatus.COMPLETED,
                                progress=100,
                                message="Music generated!",
                                result_url=output.get("url"),
                                metadata=output,
                                updated_at=time.time(),
                            )

                    estimated = min(poll_count * 5, 90)
                    return PredictResult(
                        task_id=task_id,
                        status=TaskStatus.RUNNING,
                        progress=estimated,
                        message="Generating music...",
                        updated_at=time.time(),
                    )

                await asyncio.sleep(poll_interval)

            except (httpx.ConnectError, httpx.ReadTimeout):
                await asyncio.sleep(poll_interval * 2)
                continue
            except Exception as exc:
                logger.warning("MusicGen poll error: %s", exc)
                await asyncio.sleep(poll_interval)
                continue

        return PredictResult(
            task_id=task_id,
            status=TaskStatus.FAILED,
            progress=0,
            error=f"Music generation timed out after {remaining:.0f}s",
            updated_at=time.time(),
        )

    # ------------------------------------------------------------------
    # Unified contract: predict() — builds PredictRequest internally
    # ------------------------------------------------------------------

    async def predict(self, request: PredictRequest) -> PredictResult:
        """
        Unified entry-point.

        Extracts domain parameters from ``request.extra``, builds the
        internal payload, then delegates to the base class ``predict()``.
        """
        prompt = request.extra.get("prompt")
        if not prompt:
            return PredictResult(
                task_id=request.task_id,
                status=TaskStatus.FAILED,
                progress=0,
                error="Missing 'prompt' in PredictRequest.extra",
            )

        payload = self._build_payload(
            prompt=prompt,
            duration=request.extra.get("duration", self.DEFAULT_DURATION),
            temperature=request.extra.get("temperature", self.DEFAULT_TEMPERATURE),
            top_k=request.extra.get("top_k", self.DEFAULT_TOP_K),
            top_p=request.extra.get("top_p", self.DEFAULT_TOP_P),
        )

        # Delegate to base class predict() for cold-start retry + polling
        return await super().predict(PredictRequest(
            service_type=request.service_type,
            task_id=request.task_id,
            payload=payload,
            extra=request.extra,
        ))

    # ------------------------------------------------------------------
    # Convenience method (still available for direct use)
    # ------------------------------------------------------------------

    async def generate(
        self,
        task_id: str,
        prompt: str,
        *,
        duration: float = DEFAULT_DURATION,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> PredictResult:
        """Direct convenience method — bypasses PredictRequest."""
        payload = self._build_payload(
            prompt=prompt,
            duration=duration,
            temperature=temperature,
        )
        return await super().predict(PredictRequest(
            service_type="music",
            task_id=task_id,
            payload=payload,
            extra={},
        ))
