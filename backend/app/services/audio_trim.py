"""
Audio Trimming Service

Uses ffmpeg to slice audio files by start/end time.
Supports both local files and HTTP URLs.

Usage:
    result = await trim_audio(url, start=3.0, end=15.0)
    # Returns: bytes (audio data) + content_type
"""

from __future__ import annotations

import asyncio
import io
import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


async def trim_audio(
    url: str,
    start: float,
    end: float,
    output_format: str = "wav",
) -> tuple[bytes, str]:
    """
    Trim audio from url between start and end seconds.

    Args:
        url: Local file path or HTTP URL.
        start: Start time in seconds.
        end: End time in seconds.
        output_format: Output format (wav, mp3, etc.).

    Returns:
        Tuple of (audio_bytes, content_type).

    Raises:
        RuntimeError: If ffmpeg is not available or trimming fails.
    """
    duration = end - start
    if duration <= 0:
        raise ValueError(f"Invalid trim range: start={start}, end={end}")

    # Determine input args
    if url.startswith(("http://", "https://")):
        input_args = ["-i", url]
    else:
        # Local file
        input_args = ["-i", url]

    # Build ffmpeg command
    cmd = [
        "ffmpeg",
        "-y",                    # overwrite output
        "-ss", str(start),       # seek to start (accurate)
        "-i", url,               # input (can be URL or path)
        "-t", str(duration),     # duration
        "-c:a", "copy" if output_format == "wav" else "aac",  # codec
        "-f", output_format,     # force format
        "-",                     # output to stdout
    ]

    logger.info("Trimming audio: %s [%.1fs-%.1fs]", url, start, end)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace")[:500]
            logger.error("ffmpeg error: %s", error_msg)
            raise RuntimeError(f"ffmpeg failed: {error_msg}")

        if not stdout:
            raise RuntimeError("Empty output from ffmpeg")

        content_type = "audio/wav" if output_format == "wav" else f"audio/{output_format}"
        return stdout, content_type

    except FileNotFoundError:
        raise RuntimeError(
            "ffmpeg is not installed. Install it with: pip install ffmpeg-python "
            "or download from https://ffmpeg.org/download.html"
        )


def is_ffmpeg_available() -> bool:
    """Check if ffmpeg is available on the system."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
