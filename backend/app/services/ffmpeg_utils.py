"""FFmpeg helpers for MV rendering and audio processing."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile

logger = logging.getLogger(__name__)


def find_ffmpeg() -> str:
    """Locate ffmpeg binary: bin/ → PATH."""
    local = os.path.join(os.path.dirname(__file__), "..", "..", "..", "bin", "ffmpeg.exe")
    local = os.path.abspath(local)
    if os.path.exists(local):
        return local
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise RuntimeError("ffmpeg not found. Install ffmpeg or place ffmpeg.exe in bin/")


def ffmpeg_run(cmd: list[str]) -> None:
    """Execute ffmpeg command with error handling."""
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    except subprocess.CalledProcessError as exc:
        logger.error("ffmpeg failed: %s", exc.stderr.decode(errors="replace")[:300])
        raise RuntimeError(f"ffmpeg encoding failed: {exc}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("ffmpeg encoding timed out (120s)")


def resolve_audio_path(url: str, results_dir: str) -> str:
    """Convert /results/ local reference to absolute path."""
    if url.startswith("/results/"):
        local = os.path.join(results_dir, os.path.basename(url))
        if os.path.exists(local):
            return local
    return url