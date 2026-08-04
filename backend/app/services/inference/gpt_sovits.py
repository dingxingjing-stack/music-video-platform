"""
GPT-SoVITS Inference Service

Handles voice cloning via GPT-SoVITS deployed on a Hugging Face Space.

API Assumptions (based on typical GPT-SoVITS Gradio Space layout):
  - Input 1: reference_audio (file) — 1-3 min WAV/MP3 reference voice
  - Input 2: text (string) — target text to synthesize
  - Input 3: language (string) — "zh", "en", "jp", etc.
  - Input 4: opt_filename (string, optional) — output filename
  - Output: synthesized audio file

  POST /api/predict (multipart):
    session_hash, event_data, fn_index + files={"reference_audio": (...)}

  Response: {"event_url": "https://.../api/predict/events/..."}

  Event stream "process_completed" output[0]:
    {"file": "/path/to/output.wav", "url": "/file=/path/to/output.wav"}

  NOTE: Actual fn_index and input order depend on the specific Space's
  Gradio app.py. Adjust fn_index and data array order if your Space
  has a different layout.
"""

from __future__ import annotations

import logging
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


class GPTSovitsService(GradioSpaceMixin, BaseInferenceService):
    """Voice cloning service backed by GPT-SoVITS on HF Spaces."""

    SERVICE_TYPE = "tts"

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
        text: str,
        *,
        language: str = "zh",
        opt_filename: Optional[str] = None,
        reference_audio: Optional[bytes] = None,
    ) -> dict[str, Any]:
        """Build the Gradio prediction payload.

        Returns a dict with:
          - "data": list of input values (for event_data)
          - "_files": optional multipart files dict (for _do_submit)
        """
        data_array = [
            None,           # position 0: reference audio (filled via _files)
            text,           # position 1: target text
            language,       # position 2: language code
            opt_filename or "",  # position 3: optional filename
        ]
        payload: dict[str, Any] = {"data": data_array}

        # Attach audio bytes for multipart upload — _do_submit pops _files
        if reference_audio:
            payload["_files"] = {
                "reference_audio": ("ref.wav", reference_audio, "audio/wav")
            }
        return payload

    async def _do_submit(
        self,
        task_id: str,
        payload: dict[str, Any],
    ) -> Optional[str]:
        """Submit to Gradio Space. Pops _files for multipart upload."""
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
    # Unified contract: predict() — builds PredictRequest internally
    # ------------------------------------------------------------------

    async def predict(self, request: PredictRequest) -> PredictResult:
        """
        Unified entry-point.

        Extracts domain parameters from ``request.extra``, builds the
        internal PredictRequest-style payload, then delegates to the
        base class ``predict()`` for cold-start retry + event polling.
        """
        reference_audio = request.extra.get("reference_audio")
        if not reference_audio:
            return PredictResult(
                task_id=request.task_id,
                status=TaskStatus.FAILED,
                progress=0,
                error="Missing 'reference_audio' bytes in PredictRequest.extra",
            )

        text = request.extra.get("text", "")
        if not text:
            return PredictResult(
                task_id=request.task_id,
                status=TaskStatus.FAILED,
                progress=0,
                error="Missing 'text' in PredictRequest.extra",
            )

        # Build the internal payload (this IS the PredictRequest payload)
        payload = self._build_payload(
            text=text,
            language=request.extra.get("language", "zh"),
            opt_filename=request.extra.get("opt_filename"),
            reference_audio=reference_audio,
        )

        # Delegate to base class predict() which handles:
        #   cold-start retry → _do_submit → _poll_events → result
        return await super().predict(PredictRequest(
            service_type=request.service_type,
            task_id=request.task_id,
            payload=payload,
            extra=request.extra,
        ))

    # ------------------------------------------------------------------
    # Convenience method (still available for direct use)
    # ------------------------------------------------------------------

    async def synthesize(
        self,
        task_id: str,
        reference_audio: bytes,
        text: str,
        *,
        language: str = "zh",
        opt_filename: Optional[str] = None,
    ) -> PredictResult:
        """Direct convenience method — bypasses PredictRequest."""
        payload = self._build_payload(
            text=text,
            language=language,
            opt_filename=opt_filename,
            reference_audio=reference_audio,
        )
        return await super().predict(PredictRequest(
            service_type="tts",
            task_id=task_id,
            payload=payload,
            extra={},
        ))
