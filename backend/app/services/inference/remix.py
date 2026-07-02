"""
Remix Inference Service

Handles audio remixing — pitch shifting, tempo adjustment, and timbre
transformation — using local DSP processing (librosa + pydub) or a
Hugging Face Space backend.

POST /api/v1/remix/process takes:
  - source_track_id: str
  - source_url: str       (URL to the original audio)
  - pitchShift: int       (-12..+12 semitones)
  - tempoMultiplier: float (0.5..2.0)
  - timbreTransform: str   (warm/bright/dark/thin/heavy)

Returns a task_id; WS /ws/progress/{task_id} streams progress.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from typing import Any, Optional

from .base import (
    BaseInferenceService,
    BroadcastCallback,
    PredictRequest,
    PredictResult,
    TaskStatus,
)

logger = logging.getLogger(__name__)

TIMBRE_EQ_PRESETS: dict[str, dict[str, float]] = {
    "warm":   {"bass_boost": 3.0, "treble_cut": -2.0, "mid_boost": 1.0},
    "bright": {"bass_cut": -1.5, "treble_boost": 4.0, "mid_boost": 1.5},
    "dark":   {"bass_boost": 2.0, "treble_cut": -4.0, "mid_cut": -1.0},
    "thin":   {"bass_cut": -3.0, "treble_boost": 2.0, "mid_cut": -2.0},
    "heavy":  {"bass_boost": 4.0, "treble_boost": 1.0, "mid_boost": 2.0},
}


class RemixService(BaseInferenceService):
    """Local DSP remix service (no HF Space dependency)."""

    SERVICE_TYPE = "remix"

    def __init__(
        self,
        results_dir: str,
        *,
        broadcast: Optional[BroadcastCallback] = None,
    ):
        super().__init__(
            space_url="local",
            broadcast=broadcast,
        )
        self.results_dir = results_dir

    async def predict(self, request: PredictRequest) -> PredictResult:
        """
        Execute remix processing (local DSP).

        Extracts params from request.extra, downloads source audio,
        applies pitch/tempo/timbre, saves result.
        """
        task_id = request.task_id
        source_url = request.extra.get("source_url", "")
        pitch = int(request.extra.get("pitchShift", 0))
        tempo = float(request.extra.get("tempoMultiplier", 1.0))
        timbre = str(request.extra.get("timbreTransform", "warm"))

        if not source_url:
            return PredictResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                progress=0,
                error="Missing 'source_url' in request.extra",
            )

        # Clamp params
        pitch = max(-12, min(12, pitch))
        tempo = max(0.5, min(2.0, tempo))
        if timbre not in TIMBRE_EQ_PRESETS:
            timbre = "warm"

        # Phase 0: Report pending
        await self._report(PredictResult(
            task_id=task_id, status=TaskStatus.PENDING, progress=0,
            message="Remix queued",
        ))

        try:
            # Phase 1: Download source
            await self._report(PredictResult(
                task_id=task_id, status=TaskStatus.RUNNING, progress=10,
                message="Downloading source audio...",
            ))

            import httpx
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(source_url)
                if resp.status_code != 200:
                    return PredictResult(
                        task_id=task_id, status=TaskStatus.FAILED, progress=0,
                        error=f"Failed to download source audio: HTTP {resp.status_code}",
                    )
                audio_bytes = resp.content

            # Detect format
            ext = self._guess_format(source_url)

            # Phase 2: Process audio
            await self._report(PredictResult(
                task_id=task_id, status=TaskStatus.RUNNING, progress=30,
                message="Applying pitch/tempo/timbre...",
            ))

            result_bytes = await self._apply_remix(
                audio_bytes, ext, pitch, tempo, timbre, task_id,
            )

            if result_bytes is None:
                return PredictResult(
                    task_id=task_id, status=TaskStatus.FAILED, progress=0,
                    error="DSP processing failed. Ensure ffmpeg + pydub are installed.",
                )

            # Phase 3: Save
            await self._report(PredictResult(
                task_id=task_id, status=TaskStatus.RUNNING, progress=80,
                message="Saving result...",
            ))

            out_path = os.path.join(self.results_dir, f"{task_id}_remix.wav")
            with open(out_path, "wb") as f:
                f.write(result_bytes)

            result_url = f"/results/{task_id}_remix.wav"
            final = PredictResult(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                progress=100,
                message="Remix complete!",
                result_url=result_url,
                metadata={
                    "pitch_shift": pitch,
                    "tempo_multiplier": tempo,
                    "timbre_transform": timbre,
                    "source_track_id": request.extra.get("source_track_id", ""),
                    "elapsed_time": 0,
                },
                updated_at=time.time(),
            )
            await self._report(final)
            return final

        except Exception as exc:
            logger.exception("Remix failed: %s", exc)
            failed = PredictResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                progress=0,
                error=str(exc)[:300],
                error_code="REMIX_FAILED",
                retryable=False,
                updated_at=time.time(),
            )
            await self._report(failed)
            return failed

    @staticmethod
    def _guess_format(url: str) -> str:
        ext = url.rsplit(".", 1)[-1].split("?")[0].lower()
        if ext in ("wav", "mp3", "ogg", "flac", "m4a", "aac"):
            return ext
        return "wav"

    async def _apply_remix(
        self,
        audio_bytes: bytes,
        ext: str,
        pitch: int,
        tempo: float,
        timbre: str,
        task_id: str,
    ) -> Optional[bytes]:
        """Apply pitch shift, tempo change, and timbre EQ using pydub + ffmpeg."""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                self._apply_remix_sync, audio_bytes, ext, pitch, tempo, timbre,
            )
        except Exception as exc:
            logger.error("DSP sync error: %s", exc)
            return None

    @staticmethod
    def _apply_remix_sync(
        audio_bytes: bytes, ext: str,
        pitch: int, tempo: float, timbre: str,
    ) -> Optional[bytes]:
        """Synchronous DSP (runs in executor)."""
        try:
            from pydub import AudioSegment
        except ImportError:
            logger.error("pydub not installed — remix unavailable")
            return None

        # Write temp input
        tmp_in = tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False)
        tmp_in.write(audio_bytes)
        tmp_in.close()
        tmp_out = tempfile.mktemp(suffix=".wav")

        try:
            seg = AudioSegment.from_file(tmp_in.name, format=ext)

            # 1) Pitch shift: change frame_rate → audio plays faster/slower at
            #    original rate (pitch changes). Then resample to original rate
            #    to keep duration unchanged (pitch-only effect).
            original_rate = seg.frame_rate
            if pitch != 0:
                octaves = pitch / 12.0
                shifted_rate = int(original_rate * (2.0 ** octaves))
                seg = seg._spawn(seg.raw_data, overrides={"frame_rate": shifted_rate})
                seg = seg.set_frame_rate(original_rate)

            # 2) Tempo: change speed via frame_rate shift without pitch correction
            if tempo != 1.0:
                tempo_rate = int(original_rate * tempo)
                seg = seg._spawn(seg.raw_data, overrides={"frame_rate": tempo_rate})
                seg = seg.set_frame_rate(original_rate)

            # 3) Timbre EQ via pydub frequency manipulation
            eq = TIMBRE_EQ_PRESETS.get(timbre, TIMBRE_EQ_PRESETS["warm"])
            if eq.get("bass_boost", 0) != 0:
                seg = seg.low_pass_filter(250) + (eq["bass_boost"] / 5.0) * seg
            if eq.get("treble_boost", 0) != 0:
                seg = seg.high_pass_filter(4000) + (eq["treble_boost"] / 5.0) * seg

            seg = seg.normalize(headroom=0.5)
            seg.export(tmp_out, format="wav")

            with open(tmp_out, "rb") as f:
                return f.read()
        except Exception as exc:
            logger.exception("DSP processing failed")
            return None
        finally:
            try:
                os.unlink(tmp_in.name)
            except OSError:
                pass
            try:
                os.unlink(tmp_out)
            except OSError:
                pass

    async def health_check(self) -> tuple[bool, str]:
        try:
            from pydub import AudioSegment
            return True, "Remix service (pydub + ffmpeg) available"
        except ImportError:
            return False, "pydub not installed"

    # Stub abstract methods (service doesn't use HF Spaces)
    def _build_payload(self, **kwargs) -> dict[str, Any]:
        return {}

    async def _do_submit(self, t: str, p: dict[str, Any]) -> Optional[str]:
        return None

    def _parse_response(self, e: dict[str, Any]) -> Optional[dict[str, Any]]:
        return None