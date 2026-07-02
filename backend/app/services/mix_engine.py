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
import tempfile
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


async def render_mix(
    task_id: str,
    tracks: list[dict[str, Any]],
    results_dir: str,
    *,
    output_format: str = "wav",
    master_volume: float = 0.0,
) -> str:
    """
    Render a multi-track mix and return the result URL path.

    Each track dict:
        url: str                — source audio path/URL
        volume: float           — dB gain (-60 to +12)
        pan: float              — -1.0 (full left) to +1.0 (full right)
        eq: dict                — {"low": dB, "mid": dB, "high": dB}
        solo: bool              — if any track is soloed, only soloed play
        mute: bool              — muted tracks are silent
        reverb_send: float      — 0.0 to 1.0 wet/dry mix
    """
    loop = asyncio.get_event_loop()
    out_path = await loop.run_in_executor(
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
    ffmpeg = _find_ffmpeg()

    # Determine which tracks play (solo overrides mute)
    any_solo = any(t.get("solo", False) for t in tracks)
    active = []
    for t in tracks:
        if t.get("mute", False) and not any_solo:
            continue
        if any_solo and not t.get("solo", False):
            continue
        active.append(t)

    if not active:
        raise RuntimeError("No active tracks to mix (all muted)")

    # Build ffmpeg per-track processing filters
    filter_chains: list[str] = []
    for i, t in enumerate(active):
        vol_db = t.get("volume", 0.0)
        pan = t.get("pan", 0.0)
        eq = t.get("eq", {}) if isinstance(t.get("eq"), dict) else {}
        reverb_send = t.get("reverb_send", 0.0)

        chain: list[str] = []

        # Input label
        chain.append(f"[{i}:a]")

        # Convert to stereo if mono
        chain.append("aformat=channel_layouts=stereo")

        # Volume adjustment (dB → linear multiplier via ffmpeg volume filter)
        if vol_db != 0:
            chain.append(f"volume={vol_db}dB")

        # 3-band EQ via equalizer filter
        for band, db_val in [("low", eq.get("low", 0)), ("mid", eq.get("mid", 0)), ("high", eq.get("high", 0))]:
            if db_val != 0:
                if band == "low":
                    chain.append(f"equalizer=f=100:t=h:w=200:g={db_val}")
                elif band == "mid":
                    chain.append(f"equalizer=f=1000:t=q:w=0.5:g={db_val}")
                elif band == "high":
                    chain.append(f"equalizer=f=8000:t=h:w=200:g={db_val}")

        # Reverb via aecho delay (simple approximation)
        if reverb_send > 0:
            reflections = [
                f"[{i}r{i}]adelay=20|25[rd{i}]",
                f"[rd{i}]aecho=0.8:0.5:{40}|{50}:0.3|0.3[rv{i}]",
                f"[rv{i}]volume={10 * (reverb_send - 1.0)}dB[rr{i}]",
            ]
            chain.append(f"asplit=2[{i}d{i}][{i}r{i}]")
            chain.extend(reflections)
            chain.append(f"[{i}d{i}][rr{i}]amix=inputs=2:duration=longest[a{i}")
        else:
            chain.append(f"[{i}]anull")

        filter_chains.append(";".join(chain))

    # Pan stage — build amerge/volume per channel
    pan_filters: list[str] = []
    pan_inputs: list[str] = []
    for i, t in enumerate(active):
        pan = t.get("pan", 0.0)

        # Split stereo into left/right
        split = f"[{i}]channelsplit=channel_layout=stereo[{i}L][{i}R]"
        pan_filters.append(split)

        # Pan: adjust L/R gains
        left_gain = _pan_gain(pan, "L")
        right_gain = _pan_gain(pan, "R")
        if left_gain != 1.0:
            pan_filters.append(f"[{i}L]volume={left_gain}[{i}LP]")
        else:
            pan_filters.append(f"[{i}L]anull[{i}LP]")
        if right_gain != 1.0:
            pan_filters.append(f"[{i}R]volume={right_gain}[{i}RP]")
        else:
            pan_filters.append(f"[{i}R]anull[{i}RP]")

        # Merge back to stereo
        pan_filters.append(f"[{i}LP][{i}RP]amerge=inputs=2[{i}]")
        pan_inputs.append(f"[{i}]")

    # Final amix of all tracks
    concat_inputs = "".join(pan_inputs)
    mix_filter = f"{concat_inputs}amix=inputs={len(active)}:duration=longest[out0]"
    if master_volume != 0:
        mix_filter += f";[out0]volume={master_volume}dB[out]"
    else:
        mix_filter += ";[out0]anull[out]"
    pan_filters.append(mix_filter)

    # Map input streams: each track = input file
    inputs: list[str] = []
    for i, t in enumerate(active):
        src = _resolve_audio_path(t.get("url", ""))
        inputs.extend(["-i", src])

    filter_complex = ";".join(filter_chains + pan_filters)

    out_path = os.path.join(results_dir, f"{task_id}_mix.{output_format}")
    cmd = [
        ffmpeg, "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:a", "pcm_s16le" if output_format == "wav" else "libmp3lame",
        "-b:a", "320k" if output_format == "mp3" else "",
        out_path,
    ]
    # Remove empty strings
    cmd = [c for c in cmd if c != ""]

    logger.info("Mix command: %d inputs, %d chars filter_complex",
                len(active), len(filter_complex))

    try:
        proc = subprocess.run(
            cmd, check=True, capture_output=True,
            timeout=300,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="replace")[-500:]
        logger.error("Mix ffmpeg failed: %s", stderr)
        raise RuntimeError(f"Mix render failed: {stderr}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Mix render timed out (300s)")

    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError("Output file empty — mix failed")

    return out_path


def _pan_gain(pan: float, channel: str) -> float:
    """Calculate linear gain for L/R channel based on pan value (-1..1)."""
    pan = max(-1.0, min(1.0, pan))
    if channel == "L":
        return max(0.0, 1.0 - pan) if pan >= 0 else 0.0
    else:
        return max(0.0, 1.0 + pan) if pan <= 0 else 0.0


def _find_ffmpeg() -> str:
    import shutil
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "bin", "ffmpeg.exe"),
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "bin", "ffmpeg.exe"),
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
    if url.startswith("/results/"):
        candidate = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "results",
            os.path.basename(url),
        )
        candidate = os.path.abspath(candidate)
        if os.path.exists(candidate):
            return candidate
    return url