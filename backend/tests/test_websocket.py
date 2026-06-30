"""
WebSocket + Mock integration tests.

Tests the ConnectionManager broadcast logic and the Mock endpoint.
WebSocket integration is tested manually via uvicorn + websocket-client.

NOTE: Full end-to-end WebSocket tests (connect → broadcast → receive)
cannot run in FastAPI TestClient because its single-threaded event loop
starves concurrent asyncio.sleep loops. For real WS testing, run the
server and use the manual test procedure in the docstring.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from main import app
from app.websocket_manager import manager
from app.services.inference import PredictResult, TaskStatus


@pytest.fixture(autouse=True)
def clean_manager():
    """Clear WebSocket connections before/after each test."""
    manager._connections.clear()
    yield
    manager._connections.clear()


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Mock endpoint tests
# ---------------------------------------------------------------------------


class TestMockEndpoint:
    """Test the /api/v1/mock/run endpoint."""

    def test_mock_run_returns_task_id(self, client):
        resp = client.post("/api/v1/mock/run", json={
            "duration": 2.0,
            "tick_interval": 0.5,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "started"
        assert data["websocket"] == f"/ws/progress/{data['task_id']}"
        assert data["duration"] == 2.0

    def test_mock_run_defaults(self, client):
        resp = client.post("/api/v1/mock/run", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["duration"] == 10.0  # default


# ---------------------------------------------------------------------------
# ConnectionManager unit tests (async — uses mock WebSocket)
# ---------------------------------------------------------------------------


class _AsyncMockWS:
    """Mock WebSocket that supports async send_json."""
    def __init__(self):
        self.messages: list = []

    async def send_json(self, data):
        self.messages.append(data)

    async def close(self):
        pass


class TestConnectionManager:
    """Test the ConnectionManager broadcast logic directly."""

    @pytest.mark.asyncio
    async def test_connect_and_disconnect(self):
        task_id = "test-001"
        fake_ws = _AsyncMockWS()
        await manager.connect(task_id, fake_ws)
        assert task_id in manager.active_tasks
        assert manager.subscriber_count == 1
        await manager.disconnect(task_id, fake_ws)
        assert task_id not in manager.active_tasks
        assert manager.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_broadcast_to_single_subscriber(self):
        task_id = "test-002"
        fake_ws = _AsyncMockWS()
        await manager.connect(task_id, fake_ws)
        result = PredictResult(
            task_id=task_id,
            status=TaskStatus.RUNNING,
            progress=50,
            message="test",
        )
        count = await manager.broadcast(task_id, result)
        assert count == 1
        assert len(fake_ws.messages) == 1
        assert fake_ws.messages[0]["progress"] == 50

    @pytest.mark.asyncio
    async def test_broadcast_to_no_subscribers(self):
        result = PredictResult(
            task_id="no-one",
            status=TaskStatus.RUNNING,
            progress=50,
            message="ghost",
        )
        count = await manager.broadcast("no-task-id", result)
        assert count == 0

    @pytest.mark.asyncio
    async def test_broadcast_to_multiple_subscribers(self):
        task_id = "test-multi"
        ws1, ws2 = _AsyncMockWS(), _AsyncMockWS()
        await manager.connect(task_id, ws1)
        await manager.connect(task_id, ws2)
        result = PredictResult(
            task_id=task_id,
            status=TaskStatus.RUNNING,
            progress=25,
            message="hello",
        )
        count = await manager.broadcast(task_id, result)
        assert count == 2
        assert len(ws1.messages) == 1
        assert len(ws2.messages) == 1
        assert ws1.messages[0]["progress"] == 25
        assert ws2.messages[0]["progress"] == 25

    @pytest.mark.asyncio
    async def test_clean_manager_after_each_test(self):
        """Verify the autouse fixture clears connections."""
        assert manager.subscriber_count == 0
        assert manager.active_tasks == []


# ---------------------------------------------------------------------------
# PredictResult serialization (used by WebSocket broadcasts)
# ---------------------------------------------------------------------------


class TestPredictResultSerialization:
    """Verify that broadcast payloads have the correct shape."""

    def test_completed_result_to_dict(self):
        result = PredictResult(
            task_id="abc123",
            status=TaskStatus.COMPLETED,
            progress=100,
            message="Done!",
            result_url="http://example.com/output.wav",
            metadata={"service_type": "mock"},
        )
        d = result.to_dict()
        assert d["task_id"] == "abc123"
        assert d["status"] == "completed"
        assert d["progress"] == 100
        assert d["message"] == "Done!"
        assert d["result_url"] == "http://example.com/output.wav"
        assert d["metadata"]["service_type"] == "mock"
        assert "updated_at" in d

    def test_failed_result_to_dict(self):
        result = PredictResult(
            task_id="fail-001",
            status=TaskStatus.FAILED,
            progress=0,
            error="Something went wrong",
            error_code="TEST_ERROR",
            retryable=False,
        )
        d = result.to_dict()
        assert d["status"] == "failed"
        assert d["error"] == "Something went wrong"
        assert d["error_code"] == "TEST_ERROR"
        assert d["retryable"] is False


# ---------------------------------------------------------------------------
# Task status endpoint
# ---------------------------------------------------------------------------


class TestTaskStatus:
    """Test the /api/v1/tasks/{task_id} endpoint."""

    def test_task_status_shows_subscribers(self, client):
        task_id = "status-test"

        # Before connecting, no subscribers
        resp = client.get(f"/api/v1/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["subscribers"] == 0
