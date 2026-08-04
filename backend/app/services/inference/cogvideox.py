"""
CogVideoX Inference Service

Handles text-to-video generation via CogVideoX-2B on HF Spaces.

API Assumptions:
  - Input 1: prompt (string)
  - Input 2: num_steps (int, default 50)
  - Input 3: guidance_scale (float, default 6.0)
  - Input 4: video_length (int, default 49 frames ≈ 7s)
  - Input 5: negative_prompt (string, optional)
  - Output: generated video file (MP4)

  POST /api/predict (JSON, no files)
  Response: {"event_url": "..."}
  Event stream "process_completed" → {"file": "/path/to/output.mp4"}

  CRITICAL: CogVideoX-2B on T4: 6s video ≈ 120-180s inference.
"""

from __future__ import annotations

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


class CogVideoXService(GradioSpaceMixin, BaseInferenceService):
    """Video generation service backed by CogVideoX on HF Spaces."""

    SERVICE_TYPE = "video"

    DEFAULT_NUM_STEPS = 50
    DEFAULT_GUIDANCE_SCALE = 6.0
    DEFAULT_VIDEO_LENGTH = 49
    DEFAULT_NEGATIVE_PROMPT = "low quality, blurry, distorted, watermark, text"

    def __init__(
        self,
        space_url: str,
        api_token: Optional[str] = None,
        fn_index: int = 0,
        retry_config: Optional[RetryConfig] = None,
        broadcast: Optional[BroadcastCallback] = None,
        http_timeout: float = 1200.0,
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
        num_steps: int = DEFAULT_NUM_STEPS,
        guidance_scale: float = DEFAULT_GUIDANCE_SCALE,
        video_length: int = DEFAULT_VIDEO_LENGTH,
        negative_prompt: Optional[str] = None,
    ) -> dict[str, Any]:
        """Build the Gradio prediction payload (text-only, no files)."""
        return {
            "data": [
                prompt,
                min(num_steps, 50),
                guidance_scale,
                min(video_length, 161),
                negative_prompt or self.DEFAULT_NEGATIVE_PROMPT,
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
                return {"url": url, "filename": first.get("name", "output.mp4")}
        return None

    # ------------------------------------------------------------------
    # Override _poll_events for video-specific tuning
    # ------------------------------------------------------------------

    async def _poll_events(
        self,
        event_url: str,
        task_id: str,
        *,
        remaining: float,
        poll_interval: float = 10.0,
    ) -> PredictResult:
        """Poll with slower interval suited for very long video inference."""
        deadline = time.monotonic() + remaining
        poll_count = 0

        while time.monotonic() < deadline:
            poll_count += 1
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
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
                                message="Video generated!",
                                result_url=output.get("url"),
                                metadata=output,
                                updated_at=time.time(),
                            )

                    estimated = min(poll_count * 4, 85)
                    return PredictResult(
                        task_id=task_id,
                        status=TaskStatus.RUNNING,
                        progress=estimated,
                        message="Generating video (this may take several minutes)...",
                        updated_at=time.time(),
                    )

                import asyncio
                await asyncio.sleep(poll_interval)

            except (httpx.ConnectError, httpx.ReadTimeout):
                import asyncio
                await asyncio.sleep(poll_interval * 3)
                continue
            except Exception as exc:
                logger.warning("CogVideoX poll error: %s", exc)
                import asyncio
                await asyncio.sleep(poll_interval)
                continue

        return PredictResult(
            task_id=task_id,
            status=TaskStatus.FAILED,
            progress=0,
            error=f"Video generation timed out after {remaining:.0f}s",
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
            num_steps=request.extra.get("num_steps", self.DEFAULT_NUM_STEPS),
            guidance_scale=request.extra.get("guidance_scale", self.DEFAULT_GUIDANCE_SCALE),
            video_length=request.extra.get("video_length", self.DEFAULT_VIDEO_LENGTH),
            negative_prompt=request.extra.get("negative_prompt"),
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
        num_steps: int = DEFAULT_NUM_STEPS,
        guidance_scale: float = DEFAULT_GUIDANCE_SCALE,
        video_length: int = DEFAULT_VIDEO_LENGTH,
    ) -> PredictResult:
        """Direct convenience method — bypasses PredictRequest."""
        payload = self._build_payload(
            prompt=prompt,
            num_steps=num_steps,
            guidance_scale=guidance_scale,
            video_length=video_length,
        )
        return await super().predict(PredictRequest(
            service_type="video",
            task_id=task_id,
            payload=payload,
            extra={},
        ))
