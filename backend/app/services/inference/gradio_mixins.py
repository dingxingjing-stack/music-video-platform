"""
Gradio Space Mixin

Shared HTTP helpers for interacting with Gradio-backed HF Spaces via REST API.
Handles session management, multipart file uploads, and event-stream polling.

API assumptions (verified against HF Spaces docs, 2025):
  - POST  /api/predict          -> submit prediction, returns {"event_url": "..."}
  - GET   {event_url}           -> poll events stream, returns {"events": [...]}
  - GET   /api/queue-status    -> check if Space is sleeping (returns 503)
  - Files uploaded via multipart/form-data with field name matching the
    Gradio input component name (usually "file" or "audio")
  - Text inputs sent as JSON "data" array matching function signature order

Key change (Step 2):
  _submit_gradio_prediction now propagates network exceptions (ConnectError,
  ReadTimeout) to the caller.  BaseInferenceService.predict() owns the retry
  loop and exponential backoff; this mixin only handles the HTTP round-trip.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class GradioSpaceMixin:
    """
    Mixin that adds Gradio REST API capabilities to any BaseInferenceService.

    Usage:
        class MyService(GradioSpaceMixin, BaseInferenceService):
            ...
    """

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Gradio spaces require a session_hash for stateful interactions.
        # We generate a random one per service instance.
        self._session_hash: str = kwargs.pop("_session_hash", None) or secrets.token_hex(16)
        super().__init__(*args, **kwargs)

    def refresh_session(self) -> None:
        """Generate a new session hash (useful after Space restart)."""
        self._session_hash = secrets.token_hex(16)
        logger.info("Session refreshed: %s", self._session_hash[:8])

    def refresh_session_if_needed(self) -> None:
        """Override base hook: regenerate session after cold-start."""
        self.refresh_session()

    # ------------------------------------------------------------------
    # Prediction submission
    # ------------------------------------------------------------------

    async def _submit_gradio_prediction(
        self,
        event_url: str,
        payload: dict[str, Any],
        files: Optional[dict[str, tuple]] = None,
    ) -> dict[str, Any]:
        """
        POST to a Gradio Space prediction endpoint.

        Args:
            event_url: The full API URL (e.g. https://user-space.hf.space/api/predict)
            payload: JSON body with keys like session_hash, event_data, fn_index
            files: Optional multipart files dict, e.g. {"audio": ("ref.wav", data, "audio/wav")}

        Returns:
            Parsed JSON response, typically {"event_url": "/api/predict/events/..."}.
            Returns {"_sleeping": True} only for 503 (Space explicitly reports sleeping).

        Raises:
            httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError,
            and other network-level exceptions are propagated upward so that
            BaseInferenceService.predict() can apply its retry/backoff logic.
        """
        headers = self._auth_header()
        if files:
            headers["Connection"] = "keep-alive"  # multipart needs it

        async with httpx.AsyncClient(timeout=120.0) as client:
            if files:
                resp = await client.post(
                    event_url,
                    data=payload,
                    files=files,
                    headers=headers,
                )
            else:
                resp = await client.post(
                    event_url,
                    json=payload,
                    headers=headers,
                )

            if resp.status_code == 200:
                return resp.json() if resp.text else {}

            if resp.status_code == 503:
                # Space explicitly reports it is sleeping -- caller will retry
                # with cold-start backoff.
                logger.warning("Space reported sleeping (503)")
                return {"_sleeping": True}

            # Other non-200 -- bubble up via HTTPStatusError
            resp.raise_for_status()

    # ------------------------------------------------------------------
    # Event stream polling
    # ------------------------------------------------------------------

    async def _poll_gradio_events(
        self,
        event_url: str,
        timeout: float = 600.0,
        poll_interval: float = 3.0,
    ) -> dict[str, Any]:
        """
        Poll a Gradio Space event stream until completion or timeout.

        The event stream returns JSON like:
            {"events": [
                {"type": "process_generating", "data": {...}},
                {"type": "process_completed", "data": {"output": [...]}}
            ]}

        Args:
            event_url: Full URL to the events endpoint
            timeout: Max seconds to wait
            poll_interval: Seconds between polls

        Returns:
            Dict with keys "status" ("completed"/"failed"/"timeout") and
            optionally "output" (the prediction output array).
        """
        deadline = time.monotonic() + timeout
        last_progress = 0

        while time.monotonic() < deadline:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(event_url)

                if resp.status_code != 200:
                    logger.debug("Event poll HTTP %d, retrying...", resp.status_code)
                    await asyncio_sleep(poll_interval)
                    continue

                data = resp.json() if resp.text else {}
                events = data.get("events", [])

                for event in events:
                    event_type = event.get("type", "")
                    event_data = event.get("data", {})

                    if event_type == "process_completed":
                        output = event_data if isinstance(event_data, list) else [event_data]
                        return {"status": "completed", "output": output}

                    elif event_type == "process_generating":
                        # Update progress heuristic from generation data
                        progress = self._extract_progress(event_data)
                        if progress > last_progress:
                            logger.debug("Generation progress: %d%%", progress)
                            last_progress = progress

                    elif event_type == "process_failed":
                        error_msg = str(event_data) if event_data else "Unknown failure"
                        return {"status": "failed", "error": error_msg[:200]}

                await asyncio_sleep(poll_interval)

            except (httpx.ConnectError, httpx.ReadTimeout):
                # Space might have gone to sleep between polls
                await asyncio_sleep(min(poll_interval * 2, 30))
                continue
            except Exception as exc:
                logger.warning("Event poll error: %s", exc)
                await asyncio_sleep(poll_interval)
                continue

        return {"status": "timeout", "error": f"Polling timed out after {timeout}s"}

    @staticmethod
    def _extract_progress(event_data: Any) -> int:
        """Delegate to base class for unified progress extraction."""
        from .base import BaseInferenceService
        return BaseInferenceService._extract_progress(event_data)


# ------------------------------------------------------------------
# Standalone helper (avoid circular import of asyncio.sleep)
# ------------------------------------------------------------------

async def asyncio_sleep(seconds: float) -> None:
    """Standalone sleep to avoid importing asyncio in module scope."""
    import asyncio
    await asyncio.sleep(seconds)
