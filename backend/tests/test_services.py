"""
Integration tests for midi_render, mix_engine, remix, watermark services.

Run:
    cd backend
    python -m pytest tests/test_services.py -v
"""

from __future__ import annotations

import sys, os
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional

import pytest

BACKEND_ROOT = os.path.join(os.path.dirname(__file__), "..")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.services.inference.midi_render import MidiRenderService, MidiRenderConfig
from app.services.mix_engine import render_mix
from app.services.inference.remix import RemixService
from app.services.watermark import (
    AudioFingerprintService, BlindWatermarkService, WatermarkPayload,
    AudioFingerprint,
)
from app.services.inference.base import PredictResult, TaskStatus, PredictRequest


# ═══════════════════════════════════════════════════════════════════════
# MIDI Render Service
# ═══════════════════════════════════════════════════════════════════════


class TestMidiRenderService:
    def test_init_defaults(self):
        svc = MidiRenderService()
        assert svc.space_url == "local://midi-render"
        assert svc.config.sample_rate == 44100

    def test_init_custom_soundfont(self):
        svc = MidiRenderService(soundfont_path="/custom/path.sf2")
        assert svc.config.soundfont_path == "/custom/path.sf2"

    def test_factory_compat_params(self):
        svc = MidiRenderService(
            space_url="local://test", api_token="tok123",
            http_timeout=60.0, soundfont_path="/test.sf2",
        )
        assert svc.space_url == "local://test"
        assert svc.api_token == "tok123"
        assert svc.http_timeout == 60.0
        assert svc.config.soundfont_path == "/test.sf2"

    def test_config_dataclass(self):
        cfg = MidiRenderConfig(sample_rate=48000, output_format="mp3", gain=2.0)
        assert cfg.sample_rate == 48000
        assert cfg.output_format == "mp3"
        assert cfg.gain == 2.0

    @pytest.mark.asyncio
    async def test_predict_missing_midi_project(self):
        svc = MidiRenderService()
        req = PredictRequest(service_type="midi", task_id="midi-001", payload={}, extra={})
        result = await svc.predict(req)
        assert result.status == TaskStatus.FAILED
        assert result.error_code == "MISSING_MIDI_PROJECT"

    def test_midi_config_serializable(self):
        cfg = MidiRenderConfig()
        d = {"sample_rate": cfg.sample_rate, "output_format": cfg.output_format}
        assert d["sample_rate"] == 44100
        assert d["output_format"] == "wav"


# ═══════════════════════════════════════════════════════════════════════
# Mix Engine Service
# ═══════════════════════════════════════════════════════════════════════


class TestMixEngine:
    def test_render_mix_exists(self):
        assert callable(render_mix)

    def test_module_importable(self):
        import app.services.mix_engine
        assert hasattr(app.services.mix_engine, "render_mix")


# ═══════════════════════════════════════════════════════════════════════
# Remix Service
# ═══════════════════════════════════════════════════════════════════════


class TestRemixService:
    def test_service_exists(self):
        assert RemixService is not None
        assert hasattr(RemixService, "SERVICE_TYPE")

    def test_health_check_method_exists(self):
        assert hasattr(RemixService, "health_check")

    def test_predict_method_exists(self):
        assert hasattr(RemixService, "predict")


# ═══════════════════════════════════════════════════════════════════════
# Watermark Service
# ═══════════════════════════════════════════════════════════════════════


class TestWatermarkPayload:
    def test_round_trip(self):
        payload = WatermarkPayload(
            owner_id="user-001", project_id="proj-456",
            timestamp="2026-07-05", rights="all_rights_reserved",
            signature="deadbeef12345678",
        )
        raw = payload.to_bytes()
        assert len(raw) == 128
        decoded = WatermarkPayload.from_bytes(raw)
        assert decoded.owner_id == "user-001"
        assert decoded.project_id == "proj-456"
        assert decoded.rights == "all_rights_reserved"

    def test_to_dict(self):
        payload = WatermarkPayload(owner_id="x", project_id="y", timestamp="")
        d = payload.to_dict()
        assert d["owner_id"] == "x"
        assert d["project_id"] == "y"
        assert "rights" in d

    def test_overflow_truncation(self):
        long_id = "a" * 200
        payload = WatermarkPayload(owner_id=long_id, project_id="x", timestamp="")
        raw = payload.to_bytes()
        assert len(raw) == 128

    def test_empty_payload(self):
        payload = WatermarkPayload(owner_id="", project_id="", timestamp="")
        raw = payload.to_bytes()
        decoded = WatermarkPayload.from_bytes(raw)
        assert decoded.owner_id == ""
        assert decoded.project_id == ""


class TestAudioFingerprint:
    def test_to_dict(self):
        fp = AudioFingerprint(
            mfcc_hash="abc123", chroma_hash="def456",
            spectral_centroid_mean=1500.5, spectral_bandwidth_mean=800.0,
            duration_sec=10.0, sample_rate=44100,
        )
        d = fp.to_dict()
        assert d["mfcc_hash"] == "abc123"
        assert d["spectral_centroid_mean"] == 1500.5

    def test_composite_id(self):
        fp = AudioFingerprint(
            mfcc_hash="abc", chroma_hash="def",
            spectral_centroid_mean=1000.0, spectral_bandwidth_mean=500.0,
            duration_sec=5.0, sample_rate=44100,
        )
        cid = fp.composite_id
        assert len(cid) == 16
        assert all(c in "0123456789abcdef" for c in cid)

    def test_timestamp_auto_set(self):
        fp = AudioFingerprint(
            mfcc_hash="x", chroma_hash="y",
            spectral_centroid_mean=0, spectral_bandwidth_mean=0,
            duration_sec=1.0, sample_rate=44100,
        )
        assert fp.timestamp > 0


class TestBlindWatermarkService:
    def test_payload_to_bits(self):
        payload = WatermarkPayload(owner_id="u", project_id="p", timestamp="")
        bits = BlindWatermarkService._payload_to_bits(payload)
        assert len(bits) == 128 * 8  # 1024 bits

    def test_bits_to_payload_roundtrip(self):
        payload = WatermarkPayload(owner_id="user-001", project_id="proj-456",
                                    timestamp="2026-07-05")
        bits = BlindWatermarkService._payload_to_bits(payload)
        decoded = BlindWatermarkService._bits_to_payload(bits)
        assert decoded is not None
        assert decoded.owner_id == "user-001"
        assert decoded.project_id == "proj-456"

    def test_sync_preamble_exists(self):
        assert len(BlindWatermarkService.SYNC_PREAMBLE) == 2
        assert BlindWatermarkService.SYNC_PREAMBLE[0] == 0xA5
        assert BlindWatermarkService.SYNC_PREAMBLE[1] == 0x5A

    def test_carrier_band_in_ultrasonic(self):
        assert BlindWatermarkService.CARRIER_BAND_LOW >= 18000
        assert BlindWatermarkService.CARRIER_BAND_HIGH <= 20000