"""
Creative Workflow Engine

Orchestrates multi-step AI music creation paths:

  Path A (Suno-style):  prompt → MusicGen → full audio
  Path B (Hybrid):      prompt → MusicGen (bg) + TTS (vocals) → combine metadata
  Path C (Remix):       audio upload → Demucs (stems) → stem-level playback

Each path is fire-and-forget:
  - POST /api/v1/workflow/{a|b|c} → returns task_id immediately
  - Client connects WS /ws/progress/{task_id} for real-time updates
  - On completion, result contains track/asset metadata for the frontend DAW
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from typing import Any, Optional

import httpx

from .inference.base import (
    BaseInferenceService,
    BroadcastCallback,
    PredictRequest,
    PredictResult,
    TaskStatus,
)
from .inference.mock import MockInferenceService

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """
    Orchestrates creative workflows across multiple inference services.

    Each workflow runs as a background task and broadcasts progress
    updates via WebSocket to connected clients.
    """

    def __init__(
        self,
        broadcast: Optional[BroadcastCallback] = None,
        musicgen_url: Optional[str] = None,
        tts_url: Optional[str] = None,
        demucs_url: Optional[str] = None,
        musicgen_token: Optional[str] = None,
        tts_token: Optional[str] = None,
        demucs_token: Optional[str] = None,
        use_mock: bool = False,
    ):
        self.broadcast = broadcast or (lambda tid, r: asyncio.create_task(self._noop(r)))
        self.musicgen_url = musicgen_url
        self.tts_url = tts_url
        self.demucs_url = demucs_url
        self.musicgen_token = musicgen_token
        self.tts_token = tts_token
        self.demucs_token = demucs_token
        self.use_mock = use_mock
        self._musicgen_svc = None
        self._tts_svc = None
        self._demucs_svc = None

    @staticmethod
    async def _noop(result: PredictResult) -> None:
        logger.info("[workflow] %s (%d%%) %s", result.task_id[:8], result.progress, result.message)

    # ------------------------------------------------------------------
    # Silent broadcast — used internally by services during workflow
    # to suppress intermediate broadcasts (the workflow engine manages WS)
    # ------------------------------------------------------------------

    async def _silent(self, task_id: str, result: PredictResult) -> None:
        """Suppress broadcast — just log internally."""
        logger.info(
            "[workflow:%s] %s (%d%%) %s",
            task_id[:8], result.status.value, result.progress, result.message,
        )

    # Make _silent callable as a 2-arg function (broadcast callback signature)
    # Bound method already has self, so _silent(task_id, result) works fine

    # ------------------------------------------------------------------
    # Service getters (lazy init)
    # ------------------------------------------------------------------

    def _get_musicgen_service(self):
        """Lazy-initialize MusicGen service."""
        if self._musicgen_svc is not None:
            return self._musicgen_svc
        from .inference.musicgen import MusicGenService

        if self.use_mock:
            self._musicgen_svc = MockInferenceService(
                service_type="music-mock",
                duration=15.0,
                tick_interval=0.5,
                broadcast=self.broadcast,
            )
        else:
            assert self.musicgen_url, "MUSICGEN_SPACE_URL required"
            self._musicgen_svc = MusicGenService(
                space_url=self.musicgen_url,
                api_token=self.musicgen_token,
                broadcast=self.broadcast,
            )
        return self._musicgen_svc

    def _get_tts_service(self):
        """Lazy-initialize TTS service."""
        if self._tts_svc is not None:
            return self._tts_svc
        from .inference.gpt_sovits import GPTSovitsService

        if self.use_mock:
            self._tts_svc = MockInferenceService(
                service_type="tts-mock",
                duration=8.0,
                tick_interval=0.5,
                broadcast=self.broadcast,
            )
        else:
            assert self.tts_url, "GPT_SOVITS_SPACE_URL required"
            self._tts_svc = GPTSovitsService(
                space_url=self.tts_url,
                api_token=self.tts_token,
                broadcast=self.broadcast,
            )
        return self._tts_svc

    def _get_demucs_service(self):
        """Lazy-initialize Demucs service."""
        if self._demucs_svc is not None:
            return self._demucs_svc
        from .inference.demucs import DemucsService

        if self.use_mock:
            self._demucs_svc = MockInferenceService(
                service_type="demucs-mock",
                duration=12.0,
                tick_interval=0.5,
                broadcast=self.broadcast,
            )
        else:
            assert self.demucs_url, "DEMUCS_SPACE_URL required"
            self._demucs_svc = DemucsService(
                space_url=self.demucs_url,
                api_token=self.demucs_token,
                broadcast=self.broadcast,
            )
        return self._demucs_svc

    # ------------------------------------------------------------------
    # Path A: Suno-style — prompt → MusicGen → full audio
    # ------------------------------------------------------------------

    async def run_path_a(
        self,
        task_id: str,
        prompt: str,
        *,
        duration: float = 10.0,
        temperature: float = 0.8,
    ) -> PredictResult:
        """
        Path A: One-click music generation.

        Flow: prompt → MusicGen → completed audio track
        """
        track_id = f"track-{task_id}-music"
        tracks = [{
            "id": track_id,
            "name": f"MusicGen: {prompt[:30]}",
            "type": "music",
            "status": "queued",
            "url": None,
            "progress": 0,
        }]

        # Broadcast: starting
        await self._broadcast(task_id, TaskStatus.PENDING, 0, "Generating music...", {
            "path": "a", "tracks": tracks
        })

        svc = self._get_musicgen_service()
        result = await svc.predict(PredictRequest(
            service_type="music",
            task_id=task_id,
            payload={},
            extra={
                "prompt": prompt,
                "duration": duration,
                "temperature": temperature,
            },
        ))

        # Update tracks and broadcast final result
        if result.status == TaskStatus.COMPLETED:
            tracks[0]["status"] = "completed"
            tracks[0]["progress"] = 100
            tracks[0]["url"] = result.result_url
            tracks[0]["elapsed_time"] = result.metadata.get("elapsed_time")

            wrapped = PredictResult(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                progress=100,
                message="Music generated!",
                result_url=result.result_url,
                metadata={
                    "path": "a",
                    "tracks": tracks,
                    **result.metadata,
                },
                updated_at=time.time(),
            )
            await self._broadcast(task_id, TaskStatus.COMPLETED, 100, "Music generated!", wrapped.metadata)
            return wrapped

        # Failed
        tracks[0]["status"] = "failed"
        failed = PredictResult(
            task_id=task_id,
            status=TaskStatus.FAILED,
            progress=0,
            message="Music generation failed",
            error=result.error,
            metadata={"path": "a", "tracks": tracks},
            updated_at=time.time(),
        )
        await self._broadcast(task_id, TaskStatus.FAILED, 0, failed.message, failed.metadata)
        return failed

    # ------------------------------------------------------------------
    # Path B: Hybrid — MusicGen (bg) + TTS (vocals) → combined tracks
    # ------------------------------------------------------------------

    async def run_path_b(
        self,
        task_id: str,
        prompt: str,
        tts_text: str,
        *,
        duration: float = 10.0,
        tts_language: str = "zh",
        reference_audio_b64: Optional[str] = None,
    ) -> PredictResult:
        """
        Path B: Hybrid generation — music bed + TTS vocals.

        Flow:
          1. MusicGen generates background music
          2. TTS generates vocal track (parallel with music)
          3. Both tracks reported as a combined result
        """
        music_track_id = f"track-{task_id}-music"
        tts_track_id = f"track-{task_id}-tts"
        tracks = [
            {"id": music_track_id, "name": "Music Bed", "type": "music",
             "status": "queued", "url": None, "progress": 0},
            {"id": tts_track_id, "name": "Vocals", "type": "tts",
             "status": "queued", "url": None, "progress": 0},
        ]

        # Broadcast: starting
        await self._broadcast(task_id, TaskStatus.PENDING, 0, "Initializing hybrid workflow...", {
            "path": "b", "tracks": tracks,
        })

        # --- Step 1: Generate music bed (parallel with TTS) ---
        music_task = asyncio.create_task(
            self._generate_music(task_id, prompt, duration)
        )

        # --- Step 2: Generate TTS vocals (parallel with music) ---
        if reference_audio_b64:
            tts_task = asyncio.create_task(
                self._generate_tts_real(task_id, tts_text, tts_language, reference_audio_b64)
            )
        else:
            tts_task = asyncio.create_task(
                self._generate_tts_mock(task_id, tts_text)
            )

        # Wait for both
        music_result = await music_task
        tts_result = await tts_task

        # --- Step 3: Combine results ---
        if music_result:
            tracks[0]["name"] = f"Music: {prompt[:30]}"
            tracks[0]["status"] = music_result.status.value
            tracks[0]["url"] = music_result.result_url
            tracks[0]["progress"] = 100 if music_result.status == TaskStatus.COMPLETED else 0
        if tts_result:
            tracks[1]["name"] = f"Vocals: {tts_text[:20]}"
            tracks[1]["status"] = tts_result.status.value
            tracks[1]["url"] = tts_result.result_url
            tracks[1]["progress"] = 100 if tts_result.status == TaskStatus.COMPLETED else 0

        all_done = all(
            t["status"] == "completed" for t in tracks if t["status"] != "queued"
        )

        if all_done and tracks:
            final = PredictResult(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                progress=100,
                message="Hybrid track ready!",
                result_url=tracks[0].get("url"),
                metadata={
                    "path": "b",
                    "tracks": tracks,
                },
                updated_at=time.time(),
            )
            await self._broadcast(task_id, TaskStatus.COMPLETED, 100, "Hybrid track ready!", final.metadata)
            return final
        else:
            failed = PredictResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                progress=0,
                message="Hybrid workflow partially failed",
                error="One or more tracks failed to generate",
                metadata={"path": "b", "tracks": tracks},
                updated_at=time.time(),
            )
            await self._broadcast(task_id, TaskStatus.FAILED, 0, failed.message, failed.metadata)
            return failed

    async def _generate_music(
        self, task_id: str, prompt: str, duration: float
    ) -> Optional[PredictResult]:
        """Generate music bed and return result."""
        svc = self._get_musicgen_service()
        result = await svc.predict(PredictRequest(
            service_type="music",
            task_id=task_id,
            payload={},
            extra={"prompt": prompt, "duration": duration},
        ))
        return result

    async def _generate_tts_real(
        self, task_id: str, text: str, language: str, audio_b64: str
    ) -> Optional[PredictResult]:
        """Generate TTS vocals with real reference audio."""
        # Decode base64 audio to bytes
        try:
            audio_bytes = base64.b64decode(audio_b64)
        except Exception:
            audio_bytes = audio_b64.encode()  # fallback: treat as raw bytes

        svc = self._get_tts_service()
        result = await svc.predict(PredictRequest(
            service_type="tts",
            task_id=task_id,
            payload={},
            extra={
                "text": text,
                "language": language,
                "reference_audio": audio_bytes,
            },
        ))
        return result

    async def _generate_tts_mock(
        self, task_id: str, text: str
    ) -> Optional[PredictResult]:
        """Generate TTS vocals using mock service."""
        svc = MockInferenceService(
            service_type="tts-mock",
            duration=5.0,
            tick_interval=0.3,
            broadcast=self.broadcast,
        )
        result = await svc.predict(PredictRequest(
            service_type="tts",
            task_id=task_id,
            payload={},
            extra={"text": text},
        ))
        return result

    # ------------------------------------------------------------------
    # Path C: Remix — upload audio → Demucs stems → individual tracks
    # ------------------------------------------------------------------

    async def run_path_c(
        self,
        task_id: str,
        audio_base64: str,
        *,
        stem_count: str = "4",
        remove_reverb: bool = False,
    ) -> PredictResult:
        """
        Path C: Original remix — separate uploaded audio into stems.

        Flow: audio upload → Demucs → vocal/drums/bass/other tracks
        """
        upload_track = {
            "id": f"track-{task_id}-upload",
            "name": "Upload",
            "type": "stem",
            "status": "running",
            "url": None,
            "progress": 0,
        }
        await self._broadcast(task_id, TaskStatus.PENDING, 0, "Loading audio...", {
            "path": "c", "tracks": [upload_track]
        })

        svc = self._get_demucs_service()
        result = await svc.predict(PredictRequest(
            service_type="demucs",
            task_id=task_id,
            payload={},
            extra={
                "audio_base64": audio_base64,
                "stem_count": stem_count,
                "remove_reverb": remove_reverb,
            },
        ))

        if result.status == TaskStatus.COMPLETED:
            # Build track list from stems
            stems = result.metadata.get("stems", {})
            tracks = []
            for stem_name, stem_url in stems.items():
                tracks.append({
                    "id": f"track-{task_id}-{stem_name}",
                    "name": stem_name.capitalize(),
                    "type": "stem",
                    "status": "completed",
                    "url": stem_url,
                    "progress": 100,
                })
            if not tracks:
                # Mock mode or single output — create a generic track
                tracks = [{
                    "id": f"track-{task_id}-separation",
                    "name": f"Stems ({stem_count})",
                    "type": "stem",
                    "status": "completed",
                    "url": result.result_url,
                    "progress": 100,
                }]

            wrapped = PredictResult(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                progress=100,
                message="Audio separated into stems!",
                result_url=result.result_url,
                metadata={
                    "path": "c",
                    "tracks": tracks,
                    **result.metadata,
                },
                updated_at=time.time(),
            )
            await self._broadcast(
                task_id, TaskStatus.COMPLETED, 100,
                f"Separated into {len(tracks)} stems!",
                wrapped.metadata,
            )
            return wrapped

        # Failed
        failed = PredictResult(
            task_id=task_id,
            status=TaskStatus.FAILED,
            progress=0,
            message="Stem separation failed",
            error=result.error,
            metadata={"path": "c", "tracks": []},
            updated_at=time.time(),
        )
        await self._broadcast(task_id, TaskStatus.FAILED, 0, failed.message, failed.metadata)
        return failed

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _broadcast(
        self,
        task_id: str,
        status: TaskStatus,
        progress: int,
        message: str,
        metadata: dict[str, Any],
    ) -> None:
        """Broadcast a progress update with track metadata."""
        result = PredictResult(
            task_id=task_id,
            status=status,
            progress=progress,
            message=message,
            metadata=metadata,
            updated_at=time.time(),
        )
        await self.broadcast(task_id, result)
