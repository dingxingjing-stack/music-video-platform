"""
Audio Watermark Service

Embeds and extracts copyright watermarks into/from audio files.
Two modes:
  1. Fingerprint — extract MFCC + chroma hash for identification
  2. Blind watermark — embed near-silent coded markers in frequency domain

Uses ffmpeg for frequency-domain manipulation and librosa for
spectral fingerprint extraction.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import struct
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)


# ---- Data types -------------------------------------------------------------

@dataclass
class AudioFingerprint:
    """Spectral fingerprint of an audio segment."""
    mfcc_hash: str
    chroma_hash: str
    spectral_centroid_mean: float
    spectral_bandwidth_mean: float
    duration_sec: float
    sample_rate: int
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mfcc_hash": self.mfcc_hash,
            "chroma_hash": self.chroma_hash,
            "spectral_centroid_mean": self.spectral_centroid_mean,
            "spectral_bandwidth_mean": self.spectral_bandwidth_mean,
            "duration_sec": self.duration_sec,
            "sample_rate": self.sample_rate,
            "timestamp": self.timestamp,
        }

    @property
    def composite_id(self) -> str:
        """Unique composite ID for this fingerprint."""
        parts = f"{self.mfcc_hash}:{self.chroma_hash}:{self.spectral_centroid_mean:.1f}"
        return hashlib.sha256(parts.encode()).hexdigest()[:16]


@dataclass
class WatermarkPayload:
    """Data embedded as a blind watermark."""
    owner_id: str
    project_id: str
    timestamp: str
    rights: str = "all_rights_reserved"
    signature: str = ""

    def to_bytes(self) -> bytes:
        """Serialize payload to a compact binary form (max 128 bytes)."""
        raw = json.dumps({
            "o": self.owner_id,
            "p": self.project_id,
            "t": self.timestamp,
            "r": self.rights,
            "s": self.signature,
        }, separators=(",", ":"))
        data = raw.encode("utf-8")
        if len(data) > 128:
            data = data[:128]
        # Pad to fixed 128 bytes with zeros
        return data.ljust(128, b"\x00")

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner_id": self.owner_id,
            "project_id": self.project_id,
            "timestamp": self.timestamp,
            "rights": self.rights,
            "signature": self.signature,
        }

    @classmethod
    def from_bytes(cls, data: bytes) -> WatermarkPayload:
        text = data.rstrip(b"\x00").decode("utf-8", errors="replace")
        raw = json.loads(text)
        return cls(
            owner_id=raw.get("o", ""),
            project_id=raw.get("p", ""),
            timestamp=raw.get("t", ""),
            rights=raw.get("r", ""),
            signature=raw.get("s", ""),
        )


# ---- Fingerprint extraction -------------------------------------------------

class AudioFingerprintService:
    """Extract librosa-based spectral fingerprints."""

    @staticmethod
    async def extract(audio_path: str) -> Optional[AudioFingerprint]:
        """Extract MFCC + chroma + spectral stats from audio file."""
        try:
            import librosa
        except ImportError:
            logger.error("librosa not installed — fingerprint unavailable")
            return None

        try:
            y, sr = await asyncio.to_thread(
                librosa.load, audio_path, sr=None, mono=True, duration=30.0
            )
        except Exception as e:
            logger.error("Failed to load audio: %s", e)
            return None

        if len(y) < sr * 0.5:  # at least 0.5 seconds
            logger.warning("Audio too short for fingerprint")
            return None

        try:
            # MFCC hash
            mfcc_raw = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
            mfcc_mean = mfcc_raw.mean(axis=1)
            mfcc_hash = hashlib.sha256(mfcc_mean.tobytes()).hexdigest()[:16]

            # Chroma hash
            chroma_raw = librosa.feature.chroma_stft(y=y, sr=sr, n_chroma=12)
            chroma_mean = chroma_raw.mean(axis=1)
            chroma_hash = hashlib.sha256(chroma_mean.tobytes()).hexdigest()[:16]

            # Spectral stats
            centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
            bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)

            return AudioFingerprint(
                mfcc_hash=mfcc_hash,
                chroma_hash=chroma_hash,
                spectral_centroid_mean=float(centroid.mean()),
                spectral_bandwidth_mean=float(bandwidth.mean()),
                duration_sec=float(len(y) / sr),
                sample_rate=int(sr),
            )
        except Exception as e:
            logger.exception("Fingerprint extraction error: %s", e)
            return None


# ---- Blind watermark (FFT domain) ------------------------------------------

class BlindWatermarkService:
    """
    Embed/extract blind watermarks in the frequency domain.

    Strategy: Choose a narrow frequency band (18-20 kHz, inaudible to most
    humans), encode watermark bits as phase/frequency shifts within that band.
    Uses ffmpeg for the band manipulation and Python for bit packing.
    """

    CARRIER_BAND_LOW = 18000   # Hz — above typical human hearing range
    CARRIER_BAND_HIGH = 20000  # Hz
    BITS_PER_SECOND = 8        # Low baud to avoid artifacts
    SYNC_PREAMBLE = b"\xA5\x5A"  # 2-byte sync marker

    @classmethod
    def _payload_to_bits(cls, payload: WatermarkPayload) -> list[int]:
        """Convert WatermarkPayload to bit stream."""
        raw = payload.to_bytes()  # 128 bytes
        bits: list[int] = []
        for byte_val in raw:
            for shift in range(7, -1, -1):
                bits.append((byte_val >> shift) & 1)
        return bits

    @classmethod
    def _bits_to_payload(cls, bits: list[int]) -> Optional[WatermarkPayload]:
        """Convert bit stream back to WatermarkPayload."""
        if len(bits) < 128 * 8:
            return None
        raw = bytearray()
        for i in range(0, 128 * 8, 8):
            chunk = bits[i:i + 8]
            if len(chunk) < 8:
                break
            byte_val = sum(bit << (7 - j) for j, bit in enumerate(chunk))
            raw.append(byte_val)
        return WatermarkPayload.from_bytes(bytes(raw))

    @classmethod
    async def embed(
        cls,
        audio_path: str,
        payload: WatermarkPayload,
        output_path: str,
    ) -> bool:
        """
        Embed a blind watermark into audio.

        Uses ffmpeg band-split + amerge to insert the encoded carrier band
        into the original audio without audible artifacts.
        """
        bits = cls._payload_to_bits(payload)
        total_bits = len(bits)

        # Get audio duration
        import subprocess
        probe = await asyncio.to_thread(
            subprocess.run,
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", audio_path,
            ],
            capture_output=True, text=True, timeout=10,
        )
        duration = float(json.loads(probe.stdout)["format"]["duration"])

        # Check: enough time for all bits at BITS_PER_SECOND
        needed_duration = total_bits / cls.BITS_PER_SECOND
        if duration < needed_duration:
            logger.warning(
                "Audio too short: %.1fs < %.1fs needed for %d bits",
                duration, needed_duration, total_bits,
            )
            # Pad with trailing zeros
            bits.extend([0] * int((needed_duration - duration) * cls.BITS_PER_SECOND))

        # Generate a synthetic carrier signal with FSK modulation
        # We generate the carrier as raw PCM and let ffmpeg mix it into
        # the high-frequency band.
        sample_rate = 44100
        sec_per_bit = 1.0 / cls.BITS_PER_SECOND
        samples_per_bit = int(sample_rate * sec_per_bit)

        # Build carrier: bit=0 → 18.5kHz, bit=1 → 19.5kHz
        carrier_samples = np.array([], dtype=np.float32)
        for bit in bits:
            freq = 18500 if bit == 0 else 19500
            t = np.arange(samples_per_bit, dtype=np.float32) / sample_rate
            chunk = np.sin(2.0 * np.pi * freq * t, dtype=np.float32) * 0.02  # very low amplitude
            carrier_samples = np.concatenate([carrier_samples, chunk])

        # Write carrier as temporary WAV
        import struct as st
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_carrier:
            tmp_carrier_path = tmp_carrier.name

        try:
            # Manual WAV header + PCM data (16-bit)
            num_samples = len(carrier_samples)
            data_size = num_samples * 2
            riff_size = 36 + data_size

            with open(tmp_carrier_path, "wb") as f:
                # RIFF header
                f.write(b"RIFF")
                f.write(riff_size.to_bytes(4, "little"))
                f.write(b"WAVE")
                # fmt chunk
                f.write(b"fmt ")
                f.write((16).to_bytes(4, "little"))      # chunk size
                f.write((1).to_bytes(2, "little"))        # PCM format
                f.write((1).to_bytes(2, "little"))        # mono
                f.write(sample_rate.to_bytes(4, "little"))
                f.write((sample_rate * 2).to_bytes(4, "little"))  # byte rate
                f.write((2).to_bytes(2, "little"))        # block align
                f.write((16).to_bytes(2, "little"))       # bits per sample
                # data chunk
                f.write(b"data")
                f.write(data_size.to_bytes(4, "little"))
                # PCM samples (int16, low amplitude)
                samples_int16 = (carrier_samples * 32767 * 0.02).astype(np.int16)
                f.write(samples_int16.tobytes())

            # ffmpeg: band-pass the carrier, then mix with original
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-i", audio_path,
                "-i", tmp_carrier_path,
                "-filter_complex",
                (
                    f"[1:a]bandpass=f={cls.CARRIER_BAND_LOW}:w=2000"
                    ",volume=0.003[a1];"
                    "[0:a][a1]amix=inputs=2:duration=first:weights=1 0.005[aout]"
                ),
                "-map", "[aout]",
                "-c:a", "pcm_s16le",
                output_path,
            ]
            proc = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            if proc.returncode != 0:
                logger.error("ffmpeg watermark embed failed: %s", stderr.decode()[:200])
                return False

            logger.info("Watermark embedded: %s → %s", audio_path, output_path)
            return True

        finally:
            try:
                os.unlink(tmp_carrier_path)
            except Exception:
                pass

    @classmethod
    async def extract(
        cls,
        audio_path: str,
    ) -> Optional[WatermarkPayload]:
        """
        Extract blind watermark from audio file.

        Band-pass isolate the carrier band, decode FSK bits,
        reconstruct WatermarkPayload.
        """
        audio_duration = await cls._get_duration(audio_path)
        if audio_duration is None or audio_duration < 1.0:
            return None

        # Extract carrier band to raw PCM
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_extract:
            tmp_extract_path = tmp_extract.name

        try:
            ffmpeg_extract = [
                "ffmpeg", "-y",
                "-i", audio_path,
                "-af", (
                    f"bandpass=f={cls.CARRIER_BAND_LOW}:w=2000,"
                    f"volume=200,"
                    "highpass=f=10000"
                ),
                "-ac", "1",
                "-ar", "44100",
                "-c:a", "pcm_s16le",
                tmp_extract_path,
            ]
            proc = await asyncio.create_subprocess_exec(
                *ffmpeg_extract,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

            if proc.returncode != 0:
                logger.warning("ffmpeg watermark extract failed: %s", stderr.decode()[:200])
                return None

            # Decode PCM → FSK → bits
            bits = cls._decode_fsk(tmp_extract_path, 44100)
            if bits is None:
                return None

            return cls._bits_to_payload(bits)

        finally:
            try:
                os.unlink(tmp_extract_path)
            except Exception:
                pass

    @classmethod
    async def _get_duration(cls, path: str) -> Optional[float]:
        import subprocess
        try:
            probe = await asyncio.to_thread(
                subprocess.run,
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", path],
                capture_output=True, text=True, timeout=10,
            )
            return float(json.loads(probe.stdout)["format"]["duration"])
        except Exception:
            return None

    @classmethod
    def _decode_fsk(cls, pcm_path: str, sample_rate: int) -> Optional[list[int]]:
        """Decode FSK bits from PCM WAV file."""
        import struct as st
        try:
            with open(pcm_path, "rb") as f:
                # Skip WAV header (44 bytes standard)
                f.seek(44)
                raw = f.read()

            sec_per_bit = 1.0 / cls.BITS_PER_SECOND
            samples_per_bit = int(sample_rate * sec_per_bit)

            if len(raw) < samples_per_bit * 2 * 4:  # need preamble + at least some data
                return None

            # Convert raw bytes to float samples
            num_samples = len(raw) // 2
            samples = np.zeros(num_samples, dtype=np.float32)
            for i in range(num_samples):
                val = st.unpack("<h", raw[i * 2:(i + 1) * 2])[0]
                samples[i] = float(val) / 32767.0

            # FSK decode: compute dominant frequency in each bit window
            bits: list[int] = []
            for i in range(0, len(samples) - samples_per_bit, samples_per_bit):
                window = samples[i:i + samples_per_bit]
                if len(window) < samples_per_bit // 2:
                    break

                # Simple zero-crossing rate to distinguish 18.5kHz vs 19.5kHz
                # Count sign changes
                sign_changes = 0
                prev_sign = window[0] >= 0
                for val in window[1:]:
                    cur_sign = val >= 0
                    if cur_sign != prev_sign:
                        sign_changes += 1
                    prev_sign = cur_sign

                # 18.5kHz → ~37000 zero-crossings/sec → ~462 per bit window
                # 19.5kHz → ~39000 zero-crossings/sec → ~487 per bit window
                # But we're analyzing PCM, not raw analog — use FFT instead
                # Skip simplified approach; use proper FFT
                break

            # Proper FFT-based decode
            bits = []
            n_fft = min(1024, samples_per_bit)
            for i in range(0, len(samples) - samples_per_bit, samples_per_bit):
                window = samples[i:i + samples_per_bit]
                if len(window) < n_fft:
                    break
                fft = np.abs(np.fft.rfft(window[:n_fft], n=n_fft))
                freqs = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate)
                # Find peak near 18.5k or 19.5k
                mask_low = (freqs >= 18000) & (freqs <= 19000)
                mask_high = (freqs >= 19000) & (freqs <= 20000)
                energy_low = fft[mask_low].max() if mask_low.any() else 0
                energy_high = fft[mask_high].max() if mask_high.any() else 0
                bits.append(1 if energy_high > energy_low else 0)

            if len(bits) < 16:  # need at least preamble + some header
                return None

            # Find sync preamble pattern in bits
            preamble_bits: list[int] = []
            for byte_val in cls.SYNC_PREAMBLE:
                for shift in range(7, -1, -1):
                    preamble_bits.append((byte_val >> shift) & 1)

            sync_idx = None
            for i in range(len(bits) - len(preamble_bits)):
                if bits[i:i + len(preamble_bits)] == preamble_bits:
                    sync_idx = i + len(preamble_bits)
                    break

            if sync_idx is None:
                logger.warning("No sync preamble found in extracted bits")
                return None

            return bits[sync_idx:]

        except Exception as e:
            logger.exception("FSK decode error: %s", e)
            return None


# ---- Batch utility ----------------------------------------------------------

async def fingerprint_and_watermark(
    audio_path: str,
    owner_id: str,
    project_id: str,
    output_dir: str = "",
) -> dict[str, Any]:
    """
    One-shot: extract fingerprint + embed watermark + return credentials.
    """
    fp_svc = AudioFingerprintService()
    wm_svc = BlindWatermarkService()

    fingerprint = await fp_svc.extract(audio_path)

    payload = WatermarkPayload(
        owner_id=owner_id,
        project_id=project_id,
        timestamp=str(int(time.time())),
        rights="all_rights_reserved",
        signature=fingerprint.composite_id if fingerprint else "",
    )

    out_dir = output_dir or str(Path(audio_path).parent)
    watermarked_path = str(Path(out_dir) / f"watermarked_{Path(audio_path).name}")

    success = await wm_svc.embed(audio_path, payload, watermarked_path)

    return {
        "fingerprint": fingerprint.to_dict() if fingerprint else None,
        "watermark": payload.to_dict() if hasattr(payload, "to_dict") else {},
        "watermarked": success,
        "watermarked_path": watermarked_path if success else None,
        "composite_id": fingerprint.composite_id if fingerprint else None,
    }