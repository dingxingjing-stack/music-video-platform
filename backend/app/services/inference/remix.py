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
        """Synchronous DSP via ffmpeg filter_complex (runs in executor)."""
        import shutil
        import subprocess

        # Write temp input
        tmp_in = tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False)
        tmp_in.write(audio_bytes)
        tmp_in.close()
        tmp_out = tempfile.mktemp(suffix=".wav")

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            logger.error("ffmpeg not found — remix unavailable")
            return None

        # Build ffmpeg filter chain:
        # 1. asetrate for pitch shift (changes sample rate → pitch changes)
        # 2. atempo for tempo change (preserves pitch, changes speed)
        # 3. EQ via aeval / lowshelf / highshelf filters for timbre
        filters: list[str] = []

        if pitch != 0:
            # Pitch shift (pitch-only, tempo preserved):
            # 1. asetrate changes the sample rate metadata → pitch goes up
            #    by N semitones but duration shrinks by factor 2^(N/12)
            # 2. atempo reverses the duration change, restoring original speed
            pitch_rate = int(44100 * (2.0 ** (pitch / 12.0)))
            tempo_fix = 2.0 ** (-pitch / 12.0)
            filters.append(f"asetrate={pitch_rate}")
            filters.append(f"atempo={tempo_fix:.6f}")
            filters.append("aresample=44100")

        if tempo != 1.0:
            # atempo handles tempo change while preserving pitch
            # ffmpeg allows 0.5–2.0 per filter; chain if outside range
            t = tempo
            while t > 2.0:
                filters.append("atempo=2.0")
                t /= 2.0
            while t < 0.5:
                filters.append("atempo=0.5")
                t *= 2.0
            if t != 1.0:
                filters.append(f"atempo={t:.4f}")

        # Timbre EQ via lowshelf/highshelf
        eq = TIMBRE_EQ_PRESETS.get(timbre, TIMBRE_EQ_PRESETS["warm"])
        bass_boost = eq.get("bass_boost", 0.0)
        bass_cut = eq.get("bass_cut", 0.0)
        treble_boost = eq.get("treble_boost", 0.0)
        treble_cut = eq.get("treble_cut", 0.0)
        mid_boost = eq.get("mid_boost", 0.0)
        mid_cut = eq.get("mid_cut", 0.0)

        bass_gain = bass_boost or bass_cut
        if bass_gain != 0.0:
            filters.append(f"lowshelf=f=250:g={bass_gain}")

        treble_gain = treble_boost or treble_cut
        if treble_gain != 0.0:
            filters.append(f"highshelf=f=4000:g={treble_gain}")

        mid_gain = mid_boost or mid_cut
        if mid_gain != 0.0:
            filters.append(f"equalizer=f=1000:t=q:w=1.0:g={mid_gain}")

        # Normalize via dynaudnorm for consistent loudness
        filters.append("dynaudnorm=f=200")

        filter_str = ",".join(filters) if filters else "anull"

        cmd = [
            ffmpeg, "-y", "-i", tmp_in.name,
            "-af", filter_str,
            "-ar", "44100", "-ac", "2",
            "-c:a", "pcm_s16le",
            tmp_out,
        ]

        logger.info("Remix ffmpeg filter: %s", filter_str)

        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode(errors="replace")[-500:]
            logger.error("Remix ffmpeg failed: %s", stderr)
            return None
        except subprocess.TimeoutExpired:
            logger.error("Remix ffmpeg timed out")
            return None

        try:
            with open(tmp_out, "rb") as f:
                return f.read()
        except OSError as exc:
            logger.error("Remix output read failed: %s", exc)
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
        import shutil
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            return True, f"Remix service available (ffmpeg: {ffmpeg})"
        return False, "ffmpeg not installed"

    # Stub abstract methods (service doesn't use HF Spaces)
    def _build_payload(self, **kwargs) -> dict[str, Any]:
        return {}

    async def _do_submit(self, t: str, p: dict[str, Any]) -> Optional[str]:
        return None

    def _parse_response(self, e: dict[str, Any]) -> Optional[dict[str, Any]]:
        return None