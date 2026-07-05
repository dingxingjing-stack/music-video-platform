"""
Mix Engine Service

Multi-track audio mixing engine. Accepts a list of tracks with volume,
pan, EQ, and reverb parameters; uses ffmpeg to render the composite
mix into a single stereo audio file.

POST /api/v1/mix/render takes:
  {
    "tracks": [
      {"url": "/results/...", "volume": -6.0, "pan": 0.0,
       "eq": {"high": 2, "mid": 0, "low": -3},
       "solo": false, "mute": false,
       "reverb_send": 0.2},
      ...
    ],
    "output_format": "wav",   // wav or mp3
    "master_volume": 0.0       // dB
  }

Returns a task_id; WS /ws/progress/{task_id} streams progress.
On completion, result_url contains the mixed audio file.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
from typing import Any

logger = logging.getLogger(__name__)


async def render_mix(
    task_id: str,
    tracks: list[dict[str, Any]],
    results_dir: str,
    *,
    output_format: str = "wav",
    master_volume: float = 0.0,
) -> str:
    """Render a multi-track mix and return the result URL path."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        _render_mix_sync, tracks, results_dir, task_id,
        output_format, master_volume,
    )
    return f"/results/{task_id}_mix.{output_format}"


def _render_mix_sync(
    tracks: list[dict[str, Any]],
    results_dir: str,
    task_id: str,
    output_format: str,
    master_volume: float,
) -> str:
    """Synchronous ffmpeg-based mix render."""
    ffmpeg = _find_ffmpeg()

    # Determine active tracks (solo overrides mute)
    any_solo = any(t.get("solo", False) for t in tracks)
    active = [
        t for t in tracks
        if (not t.get("mute", False) or any_solo)
        and (not any_solo or t.get("solo", False))
    ]
    if not active:
        raise RuntimeError("No active tracks to mix (all muted)")

    # Build per-track filter chains, then merge.
    #
    # Strategy: each input [i:a] goes through volume → EQ → pan → reverb send.
    # Output of each track is [t{i}]. All [t{i}] are amix'd into [mix],
    # then master volume → [out].
    #
    # Pan law: equal-power. For pan p ∈ [-1, 1]:
    #   L_gain = cos((p+1) * π/4)
    #   R_gain = sin((p+1) * π/4)
    # This keeps total power constant and avoids the discontinuities
    # of the previous linear-pan approach.

    import math

    track_filters: list[str] = []
    mix_inputs: list[str] = []

    for i, t in enumerate(active):
        vol_db = float(t.get("volume", 0.0))
        pan = max(-1.0, min(1.0, float(t.get("pan", 0.0))))
        eq = t.get("eq", {}) if isinstance(t.get("eq"), dict) else {}
        reverb_send = float(t.get("reverb_send", 0.0))

        parts: list[str] = [f"[{i}:a]"]

        # Force stereo
        parts.append("aformat=channel_layouts=stereo")

        # Volume
        if vol_db != 0.0:
            parts.append(f"volume={vol_db}dB")

        # 3-band EQ
        eq_bands = [
            ("low", 100, "h", 200),    # highshelf-like at 100Hz, width 200Hz
            ("mid", 1000, "q", 1.0),   # peaking at 1kHz, Q=1.0
            ("high", 8000, "h", 200),  # highshelf at 8kHz, width 200Hz
        ]
        for band, freq, width_type, width_val in eq_bands:
            db_val = float(eq.get(band, 0) or 0)
            if db_val != 0.0:
                parts.append(f"equalizer=f={freq}:t={width_type}:w={width_val}:g={db_val}")

        # Equal-power pan (afilter pan=stereo)
        #   left  = cos((pan+1) * π/4)
        #   right = sin((pan+1) * π/4)
        angle = (pan + 1.0) * math.pi / 4.0
        left_gain = math.cos(angle)
        right_gain = math.sin(angle)
        # Clamp to 4 decimals for filter stability
        parts.append(f"pan=stereo|c0={left_gain:.4f}|c1={right_gain:.4f}")

        # Reverb send (aecho approximation)
        if reverb_send > 0.0:
            wet = max(0.0, min(1.0, reverb_send))
            dry = 1.0 - wet
            # asplit → dry path + wet path (aecho) → amix
            parts.append(f"asplit=2[d{i}a][d{i}b]")
            wet_chain = (
                f"[d{i}b]aecho=0.8:0.7:{int(40)}|{int(60)}:{wet:.3f}|{wet:.3f}[d{i}r];"
                f"[d{i}a]volume={dry:.3f}[d{i}c];"
                f"[d{i}c][d{i}r]amix=inputs=2:duration=longest:weights=1 {wet:.3f}[t{i}]"
            )
            track_filters.append(";".join(parts))
            track_filters.append(wet_chain)
        else:
            parts.append(f"[t{i}]")
            track_filters.append(";".join(parts))

        mix_inputs.append(f"[t{i}]")

    # Final amix of all tracks → master volume → [out]
    mix_filter = (
        f"{''.join(mix_inputs)}amix=inputs={len(active)}:duration=longest[mix0]"
    )
    if master_volume != 0.0:
        mix_filter += f";[mix0]volume={master_volume}dB[out]"
    else:
        mix_filter += ";[mix0]anull[out]"

    track_filters.append(mix_filter)
    filter_complex = ";".join(track_filters)

    # Input files
    inputs: list[str] = []
    for t in active:
        src = _resolve_audio_path(t.get("url", ""))
        inputs.extend(["-i", src])

    out_path = os.path.join(results_dir, f"{task_id}_mix.{output_format}")
    cmd: list[str] = [
        ffmpeg, "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:a", "pcm_s16le" if output_format == "wav" else "libmp3lame",
    ]
    if output_format == "mp3":
        cmd.extend(["-b:a", "320k"])
    cmd.append(out_path)

    logger.info(
        "Mix render: %d tracks, filter_complex %d chars",
        len(active), len(filter_complex),
    )
    logger.debug("Mix filter: %s", filter_complex)

    try:
        subprocess.run(
            cmd, check=True, capture_output=True, timeout=300,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="replace")[-800:]
        logger.error("Mix ffmpeg failed: %s", stderr)
        raise RuntimeError(f"Mix render failed: {stderr}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Mix render timed out (300s)")

    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError("Output file empty — mix failed")

    logger.info("Mix render complete: %s (%d bytes)", out_path, os.path.getsize(out_path))
    return out_path


def _find_ffmpeg() -> str:
    import shutil
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "..", "bin", "ffmpeg.exe"),
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "bin", "ffmpeg.exe"),
    ]
    for c in candidates:
        p = os.path.abspath(c)
        if os.path.exists(p):
            return p
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise RuntimeError("ffmpeg not found")


def _resolve_audio_path(url: str) -> str:
    """Resolve a URL or /results/ path to a local filesystem path."""
    if url.startswith("/results/"):
        candidate = os.path.join(
            os.path.dirname(__file__), "..", "..", "results",
            os.path.basename(url),
        )
        candidate = os.path.abspath(candidate)
        if os.path.exists(candidate):
            return candidate
    # If it's a data URL or remote URL, ffmpeg can handle it directly
    return url
