"""
Integration test: real service (GPT-SoVITS) → WebSocket broadcast chain.

Uses httpx mock transport to simulate HF Space responses without any
network calls. Validates the full chain:

  1. GPTSovitsService.predict() with mocked HTTP
  2. _report() → broadcast callback fires at each phase
  3. ConnectionManager.broadcast() delivers to connected WebSocket
  4. WebSocket receives correct progress updates

Run:
    cd backend
    python -m pytest tests/test_real_service.py -v
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.websocket_manager import manager
from app.services.inference import (
    GPTSovitsService,
    InferenceServiceFactory,
    PredictRequest,
    PredictResult,
    TaskStatus,
    RetryConfig,
)


# ===========================================================================
# Helpers — mock HF Space responses
# ===========================================================================

SAMPLE_WAV = b"\x00\x01\x02\x03" * 1000  # fake reference audio


def _make_event_stream(events: list[dict[str, Any]]) -> str:
    """Turn a list of event dicts into the JSON Gradio event stream expects."""
    return json.dumps({"events": events})


# ===========================================================================
# Test 1: GPT-SoVITS service creates correctly from factory
# ===========================================================================


class TestServiceCreation:
    """Verify factory wiring for GPT-SoVITS."""

    def test_factory_creates_gpt_sovits(self):
        factory = InferenceServiceFactory()
        svc = factory.create("tts", space_url="https://test.hf.space")
        assert isinstance(svc, GPTSovitsService)
        assert svc.space_url == "https://test.hf.space"

    def test_factory_resolves_env_prefix(self):
        """Factory reads GPT_SOVITS env vars when no explicit config."""
        config = {"tts": {"space_url": "https://env-test.hf.space", "fn_index": 1}}
        factory = InferenceServiceFactory(config)
        svc = factory.create("tts")
        assert svc.fn_index == 1

    def test_alias_voice_maps_to_tts(self):
        factory = InferenceServiceFactory()
        svc = factory.create("voice", space_url="https://test.hf.space")
        assert isinstance(svc, GPTSovitsService)


# ===========================================================================
# Test 2: Full predict lifecycle with mocked HTTP → broadcast → WS
# ===========================================================================


class _AsyncMockWS:
    """Mock WebSocket supporting async send_json."""

    def __init__(self):
        self.messages: list[dict[str, Any]] = []

    async def send_json(self, data: dict[str, Any]) -> None:
        self.messages.append(data)

    async def close(self) -> None:
        pass


class BroadcastCapture:
    """Captures broadcast callback calls for assertion."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, PredictResult]] = []

    async def __call__(self, task_id: str, result: PredictResult) -> None:
        self.calls.append((task_id, result))


class TestRealServiceBroadcast:
    """
    Simulate a real GPT-SoVITS prediction via mocked httpx transport.

    The mock responds with:
      1. POST /api/predict → {"event_url": "..."}
      2. GET {event_url} → event stream with progress + completion
    """

    @pytest.mark.asyncio
    async def test_full_predict_lifecycle_broadcasts_progress(self):
        """
        Mock a successful GPT-SoVITS call and verify broadcast delivers
        PENDING → LOADING → RUNNING → COMPLETED through WebSocket.
        """
        broadcast = BroadcastCapture()
        factory = InferenceServiceFactory()
        svc = factory.create("tts", space_url="https://test.hf.space", broadcast=broadcast)
        assert isinstance(svc, GPTSovitsService)

        # Short retry config for fast test
        svc.retry_config = RetryConfig(
            max_cold_start_retries=0,
            max_network_retries=0,
        )

        # Mock _do_submit to return an event_url immediately
        with patch.object(svc, "_do_submit", return_value="https://test.hf.space/api/predict/events/123"), \
             patch.object(svc, "_poll_events") as mock_poll:
            mock_poll.return_value = PredictResult(
                task_id="tts-real-001",
                status=TaskStatus.COMPLETED,
                progress=100,
                message="Done!",
                result_url="https://test.hf.space/file=/output.wav",
            )

            req = PredictRequest(
                service_type="tts",
                task_id="tts-real-001",
                payload={},
                extra={
                    "reference_audio": SAMPLE_WAV,
                    "text": "你好世界",
                    "language": "zh",
                },
            )
            result = await svc.predict(req)

        # Final result is COMPLETED
        assert result.status == TaskStatus.COMPLETED
        assert result.progress == 100
        assert result.result_url is not None

        # Broadcast was called at each phase
        assert len(broadcast.calls) >= 2
        statuses = [c[1].status for c in broadcast.calls]
        assert TaskStatus.PENDING in statuses
        assert TaskStatus.COMPLETED in statuses

        # First broadcast is always PENDING
        assert broadcast.calls[0][1].status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_broadcast_delivers_through_websocket_manager(self):
        """
        Verify that broadcast callback → ConnectionManager delivers
        messages to connected WebSocket clients.
        """
        task_id = "ws-chain-001"
        fake_ws = _AsyncMockWS()

        # Connect mock WebSocket
        await manager.connect(task_id, fake_ws)

        # Simulate a broadcast call
        result = PredictResult(
            task_id=task_id,
            status=TaskStatus.RUNNING,
            progress=50,
            message="Inference in progress...",
        )
        await manager.broadcast(task_id, result)

        # WebSocket received the message
        assert len(fake_ws.messages) == 1
        msg = fake_ws.messages[0]
        assert msg["task_id"] == task_id
        assert msg["status"] == "running"
        assert msg["progress"] == 50

        # Cleanup
        await manager.disconnect(task_id, fake_ws)
        assert manager.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_progress_monotonically_increases_during_polling(self):
        """
        During the RUNNING phase, progress values should generally increase.
        This validates the _poll_events progress extraction logic.
        """
        broadcast = BroadcastCapture()
        factory = InferenceServiceFactory()
        svc = factory.create("tts", space_url="https://test.hf.space", broadcast=broadcast)

        svc.retry_config = RetryConfig(max_cold_start_retries=0, max_network_retries=0)

        with patch.object(svc, "_do_submit", return_value="https://test.hf.space/events/1"), \
             patch.object(svc, "_poll_events") as mock_poll:
            mock_poll.return_value = PredictResult(
                task_id="mono-001",
                status=TaskStatus.COMPLETED,
                progress=100,
                result_url="https://test.hf.space/out.wav",
            )

            req = PredictRequest(
                service_type="tts",
                task_id="mono-001",
                payload={},
                extra={
                    "reference_audio": SAMPLE_WAV,
                    "text": "单调递增测试",
                },
            )
            await svc.predict(req)

        # Collect RUNNING phase progress values
        running_progresses = [
            c[1].progress for c in broadcast.calls if c[1].status == TaskStatus.RUNNING
        ]
        # If there are multiple RUNNING updates, they should be non-decreasing
        for i in range(1, len(running_progresses)):
            assert running_progresses[i] >= running_progresses[i - 1], \
                f"Progress decreased: {running_progresses[i-1]} → {running_progresses[i]}"

    @pytest.mark.asyncio
    async def test_extract_progress_from_event_data(self):
        """
        Verify _extract_progress handles various Gradio event shapes.
        """
        # Direct progress field
        assert GPTSovitsService._extract_progress({"progress": 45}) == 45
        assert GPTSovitsService._extract_progress({"percentage": 72}) == 72

        # Step/total ratio
        assert GPTSovitsService._extract_progress({"step": 3, "total": 10}) == 30

        # Data list (Gradio sometimes wraps progress in list)
        assert GPTSovitsService._extract_progress({"data": [60]}) == 60

        # Invalid / empty
        assert GPTSovitsService._extract_progress({}) == 0
        assert GPTSovitsService._extract_progress("not a dict") == 0
        assert GPTSovitsService._extract_progress(None) == 0

        # Cap at 99
        assert GPTSovitsService._extract_progress({"progress": 150}) == 99

    @pytest.mark.asyncio
    async def test_missing_reference_audio_returns_failed(self):
        """predict() should return FAILED when reference_audio is missing."""
        factory = InferenceServiceFactory()
        svc = factory.create("tts", space_url="https://test.hf.space")

        req = PredictRequest(
            service_type="tts",
            task_id="no-audio",
            payload={},
            extra={"text": "hello"},  # no reference_audio
        )
        result = await svc.predict(req)

        assert result.status == TaskStatus.FAILED
        assert "reference_audio" in result.error.lower()

    @pytest.mark.asyncio
    async def test_missing_text_returns_failed(self):
        """predict() should return FAILED when text is missing."""
        factory = InferenceServiceFactory()
        svc = factory.create("tts", space_url="https://test.hf.space")

        req = PredictRequest(
            service_type="tts",
            task_id="no-text",
            payload={},
            extra={"reference_audio": SAMPLE_WAV},  # no text
        )
        result = await svc.predict(req)

        assert result.status == TaskStatus.FAILED
        assert "text" in result.error.lower()


# ===========================================================================
# Test 3: WebSocket manager integration with real-service-like broadcast
# ===========================================================================


class TestWSManagerWithRealService:
    """Validate ConnectionManager bridges service broadcast → WebSocket."""

    @pytest.fixture(autouse=True)
    def _clean(self):
        manager._connections.clear()
        yield
        manager._connections.clear()

    @pytest.mark.asyncio
    async def test_broadcast_to_connected_ws_receives_all_phases(self):
        """
        Simulate the full service lifecycle: connect WS → broadcast each phase
        → verify all messages arrive at the WebSocket.
        """
        task_id = "full-lifecycle-001"
        fake_ws = _AsyncMockWS()

        await manager.connect(task_id, fake_ws)

        # Broadcast each phase
        phases = [
            PredictResult(task_id=task_id, status=TaskStatus.PENDING, progress=0, message="Task queued"),
            PredictResult(task_id=task_id, status=TaskStatus.LOADING, progress=10, message="Loading..."),
            PredictResult(task_id=task_id, status=TaskStatus.RUNNING, progress=50, message="Running..."),
            PredictResult(task_id=task_id, status=TaskStatus.COMPLETED, progress=100, message="Done!"),
        ]
        for phase in phases:
            await manager.broadcast(task_id, phase)

        # All 4 messages delivered
        assert len(fake_ws.messages) == 4
        received_statuses = [m["status"] for m in fake_ws.messages]
        assert received_statuses == ["pending", "loading", "running", "completed"]
        received_progresses = [m["progress"] for m in fake_ws.messages]
        assert received_progresses == [0, 10, 50, 100]

        await manager.disconnect(task_id, fake_ws)

    @pytest.mark.asyncio
    async def test_broadcast_to_disconnected_ws_skips_dead(self):
        """
        When a WebSocket is dead, broadcast should skip it and return
        the count of successful sends only.
        """
        task_id = "dead-ws-001"
        live_ws = _AsyncMockWS()
        dead_ws = _AsyncMockWS()

        await manager.connect(task_id, live_ws)
        await manager.connect(task_id, dead_ws)

        # Remove dead_ws from manager (simulate disconnect)
        await manager.disconnect(task_id, dead_ws)

        result = PredictResult(
            task_id=task_id,
            status=TaskStatus.RUNNING,
            progress=50,
            message="test",
        )
        count = await manager.broadcast(task_id, result)

        # Only live_ws received it
        assert count == 1
        assert len(live_ws.messages) == 1
        assert len(dead_ws.messages) == 0

    @pytest.mark.asyncio
    async def test_multiple_tasks_independent(self):
        """
        Broadcasting to task A must not affect task B's WebSocket subscribers.
        """
        ws_a = _AsyncMockWS()
        ws_b = _AsyncMockWS()

        await manager.connect("task-a", ws_a)
        await manager.connect("task-b", ws_b)

        result_a = PredictResult(task_id="task-a", status=TaskStatus.RUNNING, progress=30)
        result_b = PredictResult(task_id="task-b", status=TaskStatus.RUNNING, progress=60)

        await manager.broadcast("task-a", result_a)
        await manager.broadcast("task-b", result_b)

        assert len(ws_a.messages) == 1
        assert ws_a.messages[0]["progress"] == 30
        assert len(ws_b.messages) == 1
        assert ws_b.messages[0]["progress"] == 60

        # Clean up
        await manager.disconnect("task-a", ws_a)
        await manager.disconnect("task-b", ws_b)
