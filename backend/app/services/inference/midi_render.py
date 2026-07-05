"""
MIDI Render Service — Local FluidSynth-based MIDI to Audio rendering.

This service runs locally (no HF Space) using FluidSynth via subprocess.
Supports SoundFont (.sf2) for instrument voices.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .base import (
    BaseInferenceService,
    BroadcastCallback,
    PredictRequest,
    PredictResult,
    TaskStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class MidiRenderConfig:
    """Configuration for MIDI rendering."""
    soundfont_path: str = "/usr/share/sounds/sf2/FluidR3_GM.sf2"
    sample_rate: int = 44100
    output_format: str = "wav"  # wav, mp3, flac
    gain: float = 1.0


class MidiRenderService:
    """
    Local MIDI rendering service using FluidSynth.
    
    Unlike other services, this runs locally via subprocess (no HF Space).
    Accepts standard BaseInferenceService constructor for factory compatibility.
    """
    
    def __init__(
            self,
            space_url: str = "local://midi-render",
            api_token: Optional[str] = None,
            fn_index: int = 0,
            retry_config: Optional[Any] = None,
            broadcast: Optional[BroadcastCallback] = None,
            http_timeout: float = 300.0,
            soundfont_path: Optional[str] = None,
        ) -> None:
        # Accept standard BaseInferenceService params for factory compatibility
        self.space_url = space_url
        self.api_token = api_token
        self.retry_config = retry_config
        self.broadcast = broadcast
        self.http_timeout = http_timeout
        
        # MIDI-specific config
        self.config = MidiRenderConfig()
        if soundfont_path:
            self.config.soundfont_path = soundfont_path
        self._verify_fluidsynth()
    
    def _verify_fluidsynth(self) -> None:
        """Verify FluidSynth is available."""
        try:
            result = subprocess.run(
                ["fluidsynth", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                logger.info("FluidSynth found: %s", result.stdout.strip())
            else:
                logger.warning("FluidSynth version check failed: %s", result.stderr)
        except FileNotFoundError:
            logger.warning("FluidSynth not found in PATH. MIDI rendering will fail.")
        except Exception as e:
            logger.warning("FluidSynth check error: %s", e)
    
    async def predict(self, request: PredictRequest) -> PredictResult:
        """Render MIDI project to audio file."""
        task_id = request.task_id
        extra = request.extra
        
        midi_project = extra.get("midi_project")
        soundfont_path = extra.get("soundfont_path") or self.config.soundfont_path
        output_format = extra.get("output_format", self.config.output_format)
        
        if not midi_project:
            return PredictResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                progress=0,
                error="midi_project is required",
                error_code="MISSING_MIDI_PROJECT",
                retryable=False,
                updated_at=time.time(),
            )
        
        # Broadcast starting
        await self._report(PredictResult(
            task_id=task_id,
            status=TaskStatus.PENDING,
            progress=0,
            message="Preparing MIDI project...",
        ))
        
        try:
            # Create temporary MIDI file
            midi_content = self._project_to_midi(midi_project)
            
            with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as mid_file:
                mid_file.write(midi_content)
                midi_path = mid_file.name
            
            try:
                # Render to audio
                result = await self._render_midi(
                    task_id, midi_path, soundfont_path, output_format
                )
                return result
            finally:
                # Cleanup temp MIDI file
                try:
                    os.unlink(midi_path)
                except Exception:
                    pass
                    
        except Exception as e:
            logger.exception("MIDI render failed: %s", e)
            return PredictResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                progress=0,
                error=str(e),
                error_code="MIDI_RENDER_ERROR",
                retryable=True,
                updated_at=time.time(),
            )
    
    def _project_to_midi(self, project: dict) -> bytes:
        """Convert MIDI project dict to Standard MIDI File bytes."""
        # This is a simplified MIDI writer. In production, use mido or pretty_midi.
        # For now, we'll write a basic MIDI file structure.
        
        # Import mido if available, otherwise use manual construction
        try:
            import mido
            return self._project_to_midi_mido(project)
        except ImportError:
            logger.warning("mido not available, using fallback MIDI writer")
            return self._project_to_midi_fallback(project)
    
    def _project_to_midi_mido(self, project: dict) -> bytes:
        """Create MIDI using mido library."""
        import mido
        from mido import Message, MetaMessage, MidiFile, MidiTrack
        
        mid = MidiFile(type=1, ticks_per_beat=project.get("ticksPerQuarter", 480))
        
        # Tempo track
        tempo_track = MidiTrack()
        tempo_track.append(MetaMessage('set_tempo', tempo=mido.bpm2tempo(project.get("tempo", 120)), time=0))
        tempo_track.append(MetaMessage('time_signature', 
            numerator=project.get("timeSignature", {}).get("numerator", 4),
            denominator=project.get("timeSignature", {}).get("denominator", 4),
            time=0))
        tempo_track.append(MetaMessage('end_of_track', time=1))
        mid.tracks.append(tempo_track)
        
        # Instrument tracks
        for track_data in project.get("tracks", []):
            track = MidiTrack()
            channel = track_data.get("channel", 0)
            
            # Program change
            instrument = track_data.get("instrument", 0)
            track.append(Message('program_change', program=instrument, channel=channel, time=0))
            
            # Sort notes by start time
            notes = sorted(track_data.get("notes", []), key=lambda n: n.get("startTick", 0))
            
            current_time = 0
            for note in notes:
                pitch = note.get("pitch", 60)
                velocity = note.get("velocity", 100)
                start_tick = note.get("startTick", 0)
                duration = note.get("durationTicks", 480)
                
                delta = start_tick - current_time
                if delta > 0:
                    track.append(Message('note_on', note=pitch, velocity=velocity, channel=channel, time=delta))
                else:
                    track.append(Message('note_on', note=pitch, velocity=velocity, channel=channel, time=0))
                
                track.append(Message('note_off', note=pitch, velocity=0, channel=channel, time=duration))
                current_time = start_tick + duration
            
            track.append(MetaMessage('end_of_track', time=1))
            mid.tracks.append(track)
        
        # Save to bytes
        import io
        buffer = io.BytesIO()
        mid.save(file=buffer)
        return buffer.getvalue()
    
    def _project_to_midi_fallback(self, project: dict) -> bytes:
        """Fallback minimal MIDI writer without mido."""
        # Very basic MIDI file - just enough for simple playback
        # In production, ensure mido is installed
        ticks_per_beat = project.get("ticksPerQuarter", 480)
        tempo = project.get("tempo", 120)
        microseconds_per_beat = int(60_000_000 / tempo)
        
        # Build a minimal MIDI file (type 1)
        # This is a simplified implementation
        tracks_data = []
        
        # Track 0: Tempo map
        track0 = bytearray()
        track0.extend(b'MTrk')
        track0.extend((0).to_bytes(4, 'big'))  # placeholder for length
        
        # Set tempo
        track0.extend(b'\x00\xFF\x51\x03')
        track0.extend(microseconds_per_beat.to_bytes(3, 'big'))
        track0.extend(b'\x00\xFF\x2F\x00')  # End of track
        
        # Fix track length
        track_len = len(track0) - 8
        track0[4:8] = track_len.to_bytes(4, 'big')
        tracks_data.append(track0)
        
        # Instrument tracks
        for track_data in project.get("tracks", []):
            trk = bytearray()
            trk.extend(b'MTrk')
            trk.extend((0).to_bytes(4, 'big'))
            
            channel = track_data.get("channel", 0)
            instrument = track_data.get("instrument", 0)
            
            # Program change
            trk.extend(b'\x00\xC0')
            trk.append(instrument & 0x7F)
            
            notes = sorted(track_data.get("notes", []), key=lambda n: n.get("startTick", 0))
            current_time = 0
            
            for note in notes:
                pitch = min(max(note.get("pitch", 60), 0), 127)
                velocity = min(max(note.get("velocity", 100), 0), 127)
                start = note.get("startTick", 0)
                dur = note.get("durationTicks", ticks_per_beat)
                
                delta = start - current_time
                if delta > 0:
                    trk.extend(self._encode_varlen(delta))
                else:
                    trk.append(0x00)
                
                trk.append(0x90 | (channel & 0x0F))  # Note on
                trk.append(pitch)
                trk.append(velocity)
                
                trk.extend(self._encode_varlen(dur))
                trk.append(0x80 | (channel & 0x0F))  # Note off
                trk.append(pitch)
                trk.append(0x00)
                
                current_time = start + dur
            
            trk.extend(b'\x00\xFF\x2F\x00')  # End of track
            track_len = len(trk) - 8
            trk[4:8] = track_len.to_bytes(4, 'big')
            tracks_data.append(trk)
        
        # Write MIDI file header
        header = bytearray()
        header.extend(b'MThd')
        header.extend((6).to_bytes(4, 'big'))  # header length
        header.extend((1).to_bytes(2, 'big'))   # format 1
        header.extend((len(tracks_data)).to_bytes(2, 'big'))
        header.extend(ticks_per_beat.to_bytes(2, 'big'))
        
        # Combine
        output = bytearray()
        output.extend(header)
        for trk in tracks_data:
            output.extend(trk)
        
        return bytes(output)
    
    def _encode_varlen(self, value: int) -> bytes:
        """Encode integer as MIDI variable-length quantity."""
        if value == 0:
            return b'\x00'
        buf = bytearray()
        while value > 0:
            buf.insert(0, value & 0x7F)
            value >>= 7
        for i in range(len(buf) - 1):
            buf[i] |= 0x80
        return bytes(buf)
    
    async def _render_midi(
        self,
        task_id: str,
        midi_path: str,
        soundfont_path: str,
        output_format: str,
    ) -> PredictResult:
        """Render MIDI to audio using FluidSynth."""
        
        # Create output file
        output_dir = Path("/tmp/midi_renders")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_filename = f"{task_id}.{output_format}"
        output_path = output_dir / output_filename
        
        # Build FluidSynth command
        cmd = [
            "fluidsynth",
            "-ni",  # no interactive, no GUI
            "-r", str(self.config.sample_rate),
            "-g", str(self.config.gain),
            "-o", f"audio.file.name={output_path}",
            "-o", f"audio.file.type={output_format}",
            soundfont_path,
            midi_path,
        ]
        
        logger.info("Running FluidSynth: %s", " ".join(cmd))
        
        await self._report(PredictResult(
            task_id=task_id,
            status=TaskStatus.RUNNING,
            progress=10,
            message="Starting FluidSynth render...",
        ))
        
        # Run FluidSynth
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        # Monitor progress
        start_time = time.time()
        while True:
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
                break
            except asyncio.TimeoutError:
                elapsed = time.time() - start_time
                progress = min(int(elapsed * 5), 90)  # rough progress estimate
                await self._report(PredictResult(
                    task_id=task_id,
                    status=TaskStatus.RUNNING,
                    progress=progress,
                    message=f"Rendering... ({elapsed:.0f}s)",
                ))
        
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown FluidSynth error"
            logger.error("FluidSynth failed: %s", error_msg)
            return PredictResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                progress=0,
                error=f"FluidSynth error: {error_msg}",
                error_code="FLUIDSYNTH_ERROR",
                retryable=True,
                updated_at=time.time(),
            )
        
        # Verify output file exists
        if not output_path.exists():
            return PredictResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                progress=0,
                error="Output file not created",
                error_code="OUTPUT_MISSING",
                retryable=False,
                updated_at=time.time(),
            )
        
        # For local files, we can't serve them directly via URL in the same way.
        # In a real deployment, you'd copy to a served directory or return base64.
        # For now, we'll read and base64 encode for demo purposes.
        # In production, you'd use a file server or object storage.
        
        file_size = output_path.stat().st_size
        logger.info("Rendered audio: %s (%d bytes)", output_path, file_size)
        
        # Read and encode (for demo - in production use a file server)
        with open(output_path, "rb") as f:
            audio_data = f.read()
        
        audio_b64 = base64.b64encode(audio_data).decode()
        data_url = f"data:audio/{output_format};base64,{audio_b64}"
        
        # Cleanup
        try:
            output_path.unlink()
        except Exception:
            pass
        
        return PredictResult(
            task_id=task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message="MIDI rendered successfully",
            result_url=data_url,
            metadata={
                "format": output_format,
                "size": file_size,
                "sample_rate": self.config.sample_rate,
            },
            updated_at=time.time(),
        )
    
    async def _report(self, result: PredictResult) -> None:
        """Push progress/result to frontend via broadcast callback."""
        if self.broadcast:
            try:
                await self.broadcast(result.task_id, result)
            except Exception as exc:
                logger.error("Broadcast callback failed: %s", exc)
        logger.info(
            "[%s] %s (%d%%) %s",
            result.task_id[:8],
            result.status.value,
            result.progress,
            result.message or result.error or "",
        )
    
    async def health_check(self) -> tuple[bool, str]:
        """Check if FluidSynth is available."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "fluidsynth", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            if proc.returncode == 0:
                return True, "FluidSynth available"
            return False, "FluidSynth check failed"
        except FileNotFoundError:
            return False, "FluidSynth not installed"
        except Exception as e:
            return False, str(e)[:100]


# Factory function for use with WorkflowEngine
async def create_midi_render_service(
    broadcast: Optional[BroadcastCallback] = None,
    soundfont_path: Optional[str] = None,
) -> MidiRenderService:
    """Factory to create MidiRenderService with optional custom soundfont."""
    config = MidiRenderConfig()
    if soundfont_path:
        config.soundfont_path = soundfont_path
    return MidiRenderService(config=config, broadcast=broadcast)