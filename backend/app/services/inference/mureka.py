"""Mureka AI Inference Service

Handles all music-related generation via Mureka API:
  - Song generation (lyrics + prompt → full song)
  - Music generation (prompt → instrumental)
  - Lyrics generation
  - Vocal cloning
  - BGM generation
  - Text-to-speech

API: https://api.mureka.ai/v1/song/generate
Auth: Bearer <API_KEY>
Models: v7.6, O2, V8, V9
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

from .base import (
    BaseInferenceService,
    BroadcastCallback,
    PredictRequest,
    PredictResult,
    RetryConfig,
    TaskStatus,
)

logger = logging.getLogger(__name__)

_MUREKA_BASE_URL = os.getenv("MUREKA_BASE_URL", "https://api.mureka.ai/v1")
_MUREKA_API_KEY = os.getenv("MUREKA_API_KEY", "")
_MUREKA_MODEL = os.getenv("MUREKA_MODEL", "v9")


class MurekaService(BaseInferenceService):
    """Mureka AI music generation service."""

    SERVICE_TYPE = "mureka"

    SUPPORTED_ENDPOINTS = {
        "song": "/song/generate",       # lyrics + prompt → full song
        "music": "/music/generate",     # prompt → instrumental
        "bgm": "/bgm/generate",         # background music
        "lyrics": "/lyrics/generate",   # generate lyrics only
        "tts": "/tts/generate",         # text to speech
        "vocal-clone": "/vocal-clone",  # voice cloning
        "extend": "/song/extend",       # extend existing song
        "remix": "/remix",              # remix existing track
        "describe": "/describe-song",   # describe song from audio
        "stems": "/stems/export",       # export stems
    }

    def __init__(
        self,
        space_url: str = _MUREKA_BASE_URL,
        api_token: Optional[str] = None,
        fn_index: int = 0,
        retry_config: Optional[RetryConfig] = None,
        broadcast: Optional[BroadcastCallback] = None,
        http_timeout: float = 300.0,
        model: str = "v9",
    ):
        super().__init__(
            space_url=space_url,
            api_token=api_token or _MUREKA_API_KEY,
            fn_index=fn_index,
            retry_config=retry_config,
            broadcast=broadcast,
            http_timeout=http_timeout,
        )
        self._model = model
        self._base_url = space_url.rstrip("/")

    async def predict(self, req: PredictRequest, **kwargs: Any) -> PredictResult:
        """Execute Mureka API call based on task type."""
        task_type = req.task_type or "song"
        params = req.params or {}

        # Build endpoint
        endpoint = self.SUPPORTED_ENDPOINTS.get(task_type, self.SUPPORTED_ENDPOINTS["song"])
        url = f"{self._base_url}{endpoint}"

        # Build payload
        payload = self._build_payload(task_type, params, kwargs)

        logger.info("Mureka %s → %s (model=%s)", task_type, url, self._model)

        # Report progress
        self._report(TaskStatus.PENDING, 0, "Starting Mureka generation...")
        await asyncio.sleep(0.5)
        self._report(TaskStatus.RUNNING, 30, f"Generating via Mureka {self._model}...")

        # Call API
        try:
            async with self._http_client() as client:
                resp = await client.post(url, json=payload, timeout=self.http_timeout)

            if resp.status_code != 200:
                err_msg = resp.text[:300]
                logger.error("Mureka error %s: %s", resp.status_code, err_msg)
                self._report(TaskStatus.FAILED, 0, f"Mureka API error: {err_msg}")
                return PredictResult(
                    task_id=req.task_id,
                    status=TaskStatus.FAILED,
                    progress=0,
                    message=f"Mureka error: {err_msg}",
                    service_type=self.SERVICE_TYPE,
                )

            data = resp.json()
            self._report(TaskStatus.RUNNING, 80, "Processing response...")
            await asyncio.sleep(0.3)

            # Extract audio URL from response
            audio_url = data.get("audio_url") or data.get("output_url") or data.get("url", "")
            if not audio_url:
                # Check nested fields
                for key in ("result", "data", "output"):
                    if key in data:
                        nested = data[key]
                        if isinstance(nested, dict):
                            audio_url = nested.get("audio_url") or nested.get("url") or nested.get("output_url", "")
                            if audio_url:
                                break

            status = TaskStatus.COMPLETED if audio_url else TaskStatus.FAILED
            self._report(status, 100, "Done!" if status == TaskStatus.COMPLETED else "No output URL")

            return PredictResult(
                task_id=req.task_id,
                status=status,
                progress=100 if status == TaskStatus.COMPLETED else 0,
                message="Mureka generation complete",
                result_url=audio_url or None,
                service_type=self.SERVICE_TYPE,
                metadata={
                    "model": self._model,
                    "endpoint": task_type,
                    "raw_response": data,
                },
            )

        except Exception as exc:
            logger.exception("Mureka request failed")
            self._report(TaskStatus.FAILED, 0, str(exc)[:200])
            return PredictResult(
                task_id=req.task_id,
                status=TaskStatus.FAILED,
                progress=0,
                message=str(exc)[:200],
                service_type=self.SERVICE_TYPE,
            )

    def _build_payload(self, task_type: str, params: dict, kwargs: dict) -> dict:
        """Build Mureka API request payload based on task type."""
        model = self._model or _MUREKA_MODEL

        common = {
            "model": model,
        }

        if task_type == "song":
            # Lyrics to song or prompt to song
            return {
                **common,
                "prompt": params.get("prompt", kwargs.get("prompt", "")),
                "lyrics": params.get("lyrics", kwargs.get("lyrics", "")),
                "style": params.get("style", kwargs.get("style", "pop")),
                "duration": params.get("duration", kwargs.get("duration", 30)),
                "num_songs": params.get("num_songs", kwargs.get("num_songs", 1)),
                "generate_lyrics": params.get("generate_lyrics", False),
            }

        elif task_type == "music":
            # Prompt to instrumental music
            return {
                **common,
                "prompt": params.get("prompt", kwargs.get("prompt", "")),
                "style": params.get("style", kwargs.get("style", "")),
                "duration": params.get("duration", kwargs.get("duration", 30)),
            }

        elif task_type == "bgm":
            return {
                **common,
                "prompt": params.get("prompt", kwargs.get("prompt", "")),
                "style": params.get("style", kwargs.get("style", "")),
                "duration": params.get("duration", kwargs.get("duration", 30)),
                "mood": params.get("mood", kwargs.get("mood", "")),
            }

        elif task_type == "lyrics":
            return {
                **common,
                "prompt": params.get("prompt", kwargs.get("prompt", "")),
                "style": params.get("style", kwargs.get("style", "")),
            }

        elif task_type == "tts":
            return {
                **common,
                "text": params.get("text", kwargs.get("text", "")),
                "voice": params.get("voice", kwargs.get("voice", "")),
                "speed": params.get("speed", kwargs.get("speed", 1.0)),
            }

        elif task_type == "vocal-clone":
            return {
                **common,
                "name": params.get("name", kwargs.get("name", "")),
                "audio_url": params.get("audio_url", kwargs.get("audio_url", "")),
                "text": params.get("text", kwargs.get("text", "")),
            }

        elif task_type == "extend":
            return {
                **common,
                "audio_url": params.get("audio_url", kwargs.get("audio_url", "")),
                "duration": params.get("duration", kwargs.get("duration", 30)),
                "style": params.get("style", kwargs.get("style", "")),
            }

        elif task_type == "remix":
            return {
                **common,
                "audio_url": params.get("audio_url", kwargs.get("audio_url", "")),
                "style": params.get("style", kwargs.get("style", "")),
                "lyrics": params.get("lyrics", kwargs.get("lyrics", "")),
            }

        elif task_type == "describe":
            return {
                **common,
                "audio_url": params.get("audio_url", kwargs.get("audio_url", "")),
            }

        elif task_type == "stems":
            return {
                **common,
                "audio_url": params.get("audio_url", kwargs.get("audio_url", "")),
            }

        # Default: song generation
        return {
            **common,
            "prompt": params.get("prompt", kwargs.get("prompt", "")),
            "lyrics": params.get("lyrics", kwargs.get("lyrics", "")),
            "style": params.get("style", kwargs.get("style", "pop")),
            "duration": params.get("duration", kwargs.get("duration", 30)),
        }

    async def health_check(self) -> tuple[bool, str]:
        """Check Mureka API connectivity."""
        try:
            async with self._http_client() as client:
                resp = await client.get(self._base_url, timeout=10)
                if resp.status_code == 200:
                    return True, "Mureka API healthy"
                return True, f"Mureka reachable (status={resp.status_code})"
        except Exception as exc:
            return False, f"Mureka unreachable: {exc}"
