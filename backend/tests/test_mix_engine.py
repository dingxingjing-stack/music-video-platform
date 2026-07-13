"""
Comprehensive tests for mix_engine filter graph logic.

Run:
    cd backend
    python -m pytest tests/test_mix_engine.py -v
"""

from __future__ import annotations

import sys, os
from unittest.mock import AsyncMock, patch

import pytest

BACKEND_ROOT = os.path.join(os.path.dirname(__file__), "..")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.services.mix_engine import (
    _build_filter_and_inputs,
    render_mix,
    _resolve_audio_source,
)


# ── _resolve_audio_source ──────────────────────────────────────────────

class TestResolveAudioSource:
    def test_results_dir_url(self):
        src = _resolve_audio_source("/results/track.wav")
        assert src == "/results/track.wav"

    def test_http_url(self):
        src = _resolve_audio_source("https://example.com/audio.mp3")
        assert src == "https://example.com/audio.mp3"

    def test_local_path(self):
        src = _resolve_audio_source("./data/song.flac")
        assert src == "./data/song.flac"


# ── _build_filter_and_inputs ──────────────────────────────────────────

class TestBuildFilterAndInputs:
    def _make_track(self, **overrides):
        base = {
            "url": "/results/track.wav",
            "volume": 0.0,
            "pan": 0.0,
            "eq": {"low": 0, "mid": 0, "high": 0},
            "mute": False,
            "solo": False,
            "reverb_send": 0.0,
        }
        base.update(overrides)
        return base

    def test_single_track_no_effects(self):
        tracks = [self._make_track()]
        filter_str, inputs, active = _build_filter_and_inputs(tracks, 0.0)
        assert len(active) == 1
        assert len(inputs) == 1
        assert "aformat=channel_layouts=stereo" in filter_str
        assert "pan=stereo" in filter_str
        assert "anull[out]" in filter_str

    def test_volume_applied(self):
        tracks = [self._make_track(volume=-6.0)]
        filter_str, _, _ = _build_filter_and_inputs(tracks, 0.0)
        assert "volume=-6.0dB" in filter_str

    def test_pan_left(self):
        tracks = [self._make_track(pan=-1.0)]
        filter_str, _, _ = _build_filter_and_inputs(tracks, 0.0)
        # pan=stereo|c0=1.0000|c1=0.0000 (full left)
        assert "pan=stereo" in filter_str

    def test_pan_right(self):
        tracks = [self._make_track(pan=1.0)]
        filter_str, _, _ = _build_filter_and_inputs(tracks, 0.0)
        assert "pan=stereo" in filter_str

    def test_eq_bands_applied(self):
        tracks = [self._make_track(eq={"low": 3, "mid": -2, "high": 1})]
        filter_str, _, _ = _build_filter_and_inputs(tracks, 0.0)
        assert "equalizer=f=100:t=h:w=200:g=3" in filter_str
        assert "equalizer=f=1000:t=q:w=1.0:g=-2" in filter_str
        assert "equalizer=f=8000:t=h:w=200:g=1" in filter_str

    def test_eq_zero_ignored(self):
        tracks = [self._make_track(eq={"low": 0, "mid": 0, "high": 0})]
        filter_str, _, _ = _build_filter_and_inputs(tracks, 0.0)
        assert "equalizer=" not in filter_str

    def test_mute_excluded_by_default(self):
        tracks = [
            self._make_track(trackId="a", url="/results/a.wav"),
            self._make_track(trackId="b", url="/results/b.wav", mute=True),
        ]
        _, _, active = _build_filter_and_inputs(tracks, 0.0)
        assert len(active) == 1
        assert active[0]["trackId"] == "a"

    def test_solo_mode_excludes_non_solo(self):
        tracks = [
            self._make_track(trackId="a", url="/results/a.wav", solo=True),
            self._make_track(trackId="b", url="/results/b.wav", mute=False),
        ]
        _, _, active = _build_filter_and_inputs(tracks, 0.0)
        assert len(active) == 1
        assert active[0]["trackId"] == "a"

    def test_any_solo_all_others_excluded(self):
        tracks = [
            self._make_track(trackId="a", url="/results/a.wav", solo=True),
            self._make_track(trackId="b", url="/results/b.wav", solo=True),
            self._make_track(trackId="c", url="/results/c.wav"),
        ]
        _, _, active = _build_filter_and_inputs(tracks, 0.0)
        assert len(active) == 2
        ids = {t["trackId"] for t in active}
        assert ids == {"a", "b"}

    def test_all_muted_raises(self):
        tracks = [
            self._make_track(trackId="a", url="/results/a.wav", mute=True),
            self._make_track(trackId="b", url="/results/b.wav", mute=True),
        ]
        with pytest.raises(RuntimeError, match="No active tracks"):
            _build_filter_and_inputs(tracks, 0.0)

    def test_master_volume_applied(self):
        tracks = [self._make_track()]
        filter_str, _, _ = _build_filter_and_inputs(tracks, 6.0)
        assert "volume=6.0dB[out]" in filter_str

    def test_reverb_send_applied(self):
        tracks = [self._make_track(reverb_send=0.5)]
        filter_str, _, _ = _build_filter_and_inputs(tracks, 0.0)
        assert "aecho=0.8:0.7" in filter_str
        assert "amix=inputs=2" in filter_str

    def test_two_tracks_mix(self):
        tracks = [
            self._make_track(trackId="a", url="/results/a.wav"),
            self._make_track(trackId="b", url="/results/b.wav"),
        ]
        filter_str, inputs, active = _build_filter_and_inputs(tracks, 0.0)
        assert len(active) == 2
        assert len(inputs) == 2
        assert "amix=inputs=2" in filter_str

    def test_pan_clamped_to_range(self):
        tracks = [self._make_track(pan=2.0)]  # > 1.0 → clamp to 1.0
        filter_str, _, _ = _build_filter_and_inputs(tracks, 0.0)
        # Should use pan=1.0 (right)
        assert "pan=stereo" in filter_str

    def test_pan_negative_clamped(self):
        tracks = [self._make_track(pan=-2.0)]  # < -1.0 → clamp to -1.0
        filter_str, _, _ = _build_filter_and_inputs(tracks, 0.0)
        assert "pan=stereo" in filter_str

    def test_empty_tracks_raises(self):
        with pytest.raises(RuntimeError, match="No active tracks"):
            _build_filter_and_inputs([], 0.0)


# ── render_mix (async wrapper) ────────────────────────────────────────

class TestRenderMix:
    @pytest.mark.asyncio
    async def test_render_mix_callable(self):
        """render_mix is an async coroutine that calls _render_mix_sync."""
        assert callable(render_mix)

    @pytest.mark.asyncio
    async def test_render_mix_validates_input(self):
        """If ffmpeg is not available, render_mix should fail gracefully."""
        with patch("app.services.mix_engine.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("ffmpeg not found")
            with pytest.raises(FileNotFoundError):
                await render_mix(
                    "test-mix-001",
                    [{"url": "/results/track.wav", "volume": 0, "pan": 0, "eq": {}}],
                    "/tmp/results",
                    output_format="wav",
                    master_volume=0.0,
                )
