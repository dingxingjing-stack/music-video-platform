"""
Demucs Inference Service

Handles audio stem separation via Demucs deployed on a Hugging Face Space.

Supports splitting audio into stems: vocals, drums, bass, other (and 6s mode:
vocals, drums, bass, guitar, piano, strings).

API Assumptions:
  - Input 1: audio_file (file) — input audio to separate
  - Input 2: stem_count (select) — "4" or "6" stems
  - Input 3: remove_reverb (checkbox) — optional denoising
  - Output: separated stem files (zip or individual WAV files)

  POST /api/predict (multipart):
    session_hash, event_data, fn_index + files={"audio_file": (...)}

  Response: {"event_url": "https://.../api/predict/events/..."}

  Event stream "process_completed" output:
    zip file or dict of stem filenames → download URLs
"""

from __future__ import annotations

import base64
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


class DemucsService(GradioSpaceMixin, BaseInferenceService):
    """Audio stem separation service backed by Demucs on HF Spaces."""

    SERVICE_TYPE = "demucs"

    STEM_OPTIONS = ["4", "6"]

    def __init__(
        self,
        space_url: str,
        api_token: Optional[str] = None,
        fn_index: int = 0,
        retry_config: Optional[RetryConfig] = None,
        broadcast: Optional[BroadcastCallback] = None,
        http_timeout: float = 600.0,
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
        *,
        stem_count: str = "4",
        remove_reverb: bool = False,
    ) -> dict[str, Any]:
        """Build the Gradio prediction payload for stem separation."""
        data_array = [
            None,           # position 0: audio file (filled via _files)
            stem_count,     # position 1: number of stems
            remove_reverb,  # position 2: remove reverb checkbox
        ]
        payload: dict[str, Any] = {"data": data_array}
        return payload

    async def _do_submit(
        self,
        task_id: str,
        payload: dict[str, Any],
    ) -> Optional[str]:
        """Submit to Gradio Space with multipart audio upload."""
        files = payload.pop("_files", None)
        data_array = payload.pop("data", [])

        enriched = {
            "session_hash": self._session_hash,
            "event_data": data_array,
            "fn_index": self.fn_index,
            "batch": False,
        }

        resp = await self._submit_gradio_prediction(
            event_url=f"{self.api_base}/api/predict",
            payload=enriched,
            files=files,
        )

        if resp.get("_sleeping") or resp.get("_error"):
            return None
        return resp.get("event_url")

    def _parse_response(self, event_data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Parse Gradio event stream; return stem download info on completion."""
        if event_data.get("type") != "process_completed":
            return None

        output_raw = event_data.get("output") if "output" in event_data else event_data.get("data", [])

        # Output can be a list of file dicts (one per stem) or a zip file
        if isinstance(output_raw, list) and len(output_raw) > 0:
            # Collect all stem URLs
            stems = {}
            for item in output_raw:
                if isinstance(item, dict):
                    file_info = item.get("file") or item.get("url")
                    if file_info:
                        stem_name = item.get("name", item.get("label", "stem"))
                        url = file_info.get("url") if isinstance(file_info, dict) else str(file_info)
                        if url and "/" in url:
                            url = f"{self.api_base}{url}"
                        stems[stem_name] = url
                elif isinstance(item, str):
                    stems[f"stem_{len(stems)}"] = f"{self.api_base}{item}" if "/" in item else item
            if stems:
                return {"stems": stems, "type": "demucs_separation"}
        elif isinstance(output_raw, dict):
            file_info = output_raw.get("file") or output_raw.get("url")
            if file_info:
                url = file_info.get("url") if isinstance(file_info, dict) else str(file_info)
                if url and "/" in url:
                    url = f"{self.api_base}{url}"
                return {"url": url, "type": "demucs_zip"}

        return None

    # ------------------------------------------------------------------
    # Override _poll_events for demucs-specific progress messages
    # ------------------------------------------------------------------

    async def _poll_events(
        self,
        event_url: str,
        task_id: str,
        *,
        remaining: float,
        poll_interval: float = 5.0,
    ) -> PredictResult:
        """Poll with demucs-specific progress messages."""
        deadline = time.monotonic() + remaining
        poll_count = 0
        net_failures = 0
        last_reported_progress = 0

        while time.monotonic() < deadline:
            poll_count += 1

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(event_url)

                net_failures = 0

                if resp.status_code == 200:
                    data = resp.json() if resp.text else {}
                    events = data.get("events", []) if isinstance(data, dict) else []

                    for event in events:
                        event_type = event.get("type", "")
                        event_data = event.get("data", {})

                        if event_type == "process_completed":
                            output = self._parse_response(event)
                            if output is not None:
                                return PredictResult(
                                    task_id=task_id,
                                    status=TaskStatus.COMPLETED,
                                    progress=100,
                                    message="Audio separated into stems!",
                                    result_url=output.get("url"),
                                    metadata={**output, "elapsed_time": round(time.time() - (deadline - remaining), 2)},
                                    updated_at=time.time(),
                                )

                        if event_type == "process_generating":
                            real_progress = self._extract_progress(event_data)
                            if real_progress > 0 and real_progress != last_reported_progress:
                                last_reported_progress = real_progress
                                progress_result = PredictResult(
                                    task_id=task_id,
                                    status=TaskStatus.RUNNING,
                                    progress=real_progress,
                                    message=f"Separating stems... ({real_progress}%)",
                                    updated_at=time.time(),
                                )
                                await self._report(progress_result)

                        if event_type == "process_failed":
                            error_msg = str(event_data) if event_data else "Unknown failure"
                            return PredictResult(
                                task_id=task_id,
                                status=TaskStatus.FAILED,
                                progress=0,
                                error=error_msg[:200],
                                error_code="SEPARATION_FAILED",
                                retryable=True,
                                updated_at=time.time(),
                            )

                    estimated = min(poll_count * 3, 90)
                    if estimated != last_reported_progress:
                        last_reported_progress = estimated
                        progress_result = PredictResult(
                            task_id=task_id,
                            status=TaskStatus.RUNNING,
                            progress=estimated,
                            message="Separating stems...",
                            updated_at=time.time(),
                        )
                        await self._report(progress_result)

                    return PredictResult(
                        task_id=task_id,
                        status=TaskStatus.RUNNING,
                        progress=last_reported_progress,
                        message="Separating stems...",
                        updated_at=time.time(),
                    )

                if resp.status_code >= 500:
                    net_failures += 1
                    wait = self.retry_config.get_network_delay(net_failures - 1)
                    await asyncio_sleep(wait)
                    continue

                logger.warning("Poll unexpected status %d", resp.status_code)
                return PredictResult(
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    progress=0,
                    error=f"Poll received HTTP {resp.status_code}",
                    error_code="POLL_HTTP_ERROR",
                    retryable=False,
                    updated_at=time.time(),
                )

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
                net_failures += 1
                jitter = self._add_jitter(
                    self.retry_config.get_network_delay(net_failures - 1),
                )
                await asyncio_sleep(jitter)
                continue

            except Exception as exc:
                logger.warning("Poll unexpected error: %s", exc)
                await asyncio_sleep(poll_interval)
                continue

            await asyncio_sleep(poll_interval)

        return PredictResult(
            task_id=task_id,
            status=TaskStatus.FAILED,
            progress=0,
            error="Stem separation timed out",
            error_code="SEPARATION_TIMEOUT",
            retryable=True,
            last_attempt=poll_count,
            updated_at=time.time(),
        )

    # ------------------------------------------------------------------
    # Unified contract: predict()
    # ------------------------------------------------------------------

    async def predict(self, request: PredictRequest) -> PredictResult:
        """
        Unified entry-point.

        Extracts audio bytes and stem options from ``request.extra``,
        validates parameters, builds the internal payload, then delegates
        to the base class.
        """
        audio_b64 = request.extra.get("audio_base64", "")
        if not audio_b64:
            return PredictResult(
                task_id=request.task_id,
                status=TaskStatus.FAILED,
                progress=0,
                error="Missing 'audio_base64' in PredictRequest.extra",
            )

        try:
            audio_bytes = base64.b64decode(audio_b64)
        except Exception:
            return PredictResult(
                task_id=request.task_id,
                status=TaskStatus.FAILED,
                progress=0,
                error="Invalid base64 in 'audio_base64'",
            )

        if not audio_bytes:
            return PredictResult(
                task_id=request.task_id,
                status=TaskStatus.FAILED,
                progress=0,
                error="Empty audio data",
            )

        # Validate stem_count
        stem_count = request.extra.get("stem_count", "4")
        if stem_count not in self.STEM_OPTIONS:
            return PredictResult(
                task_id=request.task_id,
                status=TaskStatus.FAILED,
                progress=0,
                error=f"Invalid stem_count '{stem_count}'. Must be one of: {self.STEM_OPTIONS}",
            )

        # Normalize remove_reverb — handle string "true"/"false" from JSON
        remove_reverb_raw = request.extra.get("remove_reverb", False)
        if isinstance(remove_reverb_raw, str):
            remove_reverb = remove_reverb_raw.lower() in ("true", "1", "yes")
        else:
            remove_reverb = bool(remove_reverb_raw)

        payload = self._build_payload(
            stem_count=stem_count,
            remove_reverb=remove_reverb,
        )
        payload["_files"] = {"audio_file": ("input.wav", audio_bytes, "audio/wav")}

        return await super().predict(PredictRequest(
            service_type=request.service_type,
            task_id=request.task_id,
            payload=payload,
            extra=request.extra,
        ))

    # ------------------------------------------------------------------
    # Convenience method
    # ------------------------------------------------------------------

    async def separate(
        self,
        task_id: str,
        audio_bytes: bytes,
        *,
        stem_count: str = "4",
        remove_reverb: bool = False,
    ) -> PredictResult:
        """Direct convenience method — bypasses PredictRequest."""
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
        return await self.predict(PredictRequest(
            service_type="demucs",
            task_id=task_id,
            payload={},
            extra={
                "audio_base64": audio_b64,
                "stem_count": stem_count,
                "remove_reverb": remove_reverb,
            },
        ))


# ------------------------------------------------------------------
# Standalone helper (avoid circular import of asyncio.sleep)
# ------------------------------------------------------------------

async def asyncio_sleep(seconds: float) -> None:
    """Standalone sleep to avoid importing asyncio in module scope."""
    import asyncio
    await asyncio.sleep(seconds)
