"""
End-to-end integration test for the full WebSocket broadcast chain.

NOTE: These tests require fastapi + websocket_manager which depend on pydantic
compiled for the current Python version. In environments where pydantic is
only available for a different Python version (e.g. venv cp311 vs system cp312),
these tests are skipped gracefully.

Tests the complete flow:
  1. MockInferenceService.predict() -> calls _report() at each phase
  2. _report() -> calls broadcast callback -> manager.broadcast()
  3. WebSocket subscriber receives PredictResult JSON messages

P5-B.7：HTTP 入口 POST /api/v1/predict/mock 已退休（410 Gone），故广播链契约
改为直接驱动 MockInferenceService 验证，并新增端点退休守卫。
"""

from __future__ import annotations

import sys
import asyncio
import pytest

# Graceful skip when fastapi/pydantic are not importable (e.g. cp311 venv
# conflicting with cp312 system python)
try:
    from fastapi.testclient import TestClient
    from main import app
    from app.websocket_manager import manager
    from app.services.inference import PredictResult, TaskStatus
except (ImportError, ModuleNotFoundError) as exc:
    pytest.skip(f"Skipping e2e tests: {exc}", allow_module_level=True)


@pytest.fixture(autouse=True)
def clean_manager():
    manager._connections.clear()
    yield
    manager._connections.clear()


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# End-to-end broadcast chain test
# ---------------------------------------------------------------------------


class _BroadcastCollector:
    """Captures broadcast calls for assertion."""
    def __init__(self) -> None:
        self.calls: list[tuple[str, PredictResult]] = []

    async def __call__(self, task_id: str, result: PredictResult) -> None:
        self.calls.append((task_id, result))


class TestMockServiceBroadcastChain:
    """Validate the broadcast chain contract by driving MockInferenceService directly.

    P5-B.7 之前这一组用例是经由 `POST /api/v1/predict/mock` 间接触发的；该端点
    已退休，因此保留同等断言（生命周期 / 注入 / task_id 一致性 / payload 契约），
    只把驱动方式换成 service 层直调，另加一条端点退休守卫。
    """

    @staticmethod
    def _run(collector, task_id: str, duration: float, tick: float):
        from app.services.inference.base import PredictRequest
        from app.services.inference.mock import MockInferenceService

        svc = MockInferenceService(
            service_type="mock",
            duration=duration,
            tick_interval=tick,
            broadcast=collector,
        )
        return asyncio.run(
            svc.predict(PredictRequest(
                service_type="mock", task_id=task_id, payload={}, extra={},
            ))
        )

    def test_predict_endpoint_is_retired(self, client):
        """P5-B.7：predict 端点族对任何 service_type 都必须返回 410。"""
        for st in ("mock", "tts", "music", "video", "midi", "mureka", "voice", "bogus"):
            resp = client.post(f"/api/v1/predict/{st}", json={"text": "hi"})
            assert resp.status_code == 410, f"{st} -> {resp.status_code}"

    def test_mock_run_endpoint_is_retired(self, client):
        """P5-B.6：/api/v1/mock/run 必须返回 410，不再匿名创建后台任务。"""
        assert client.post("/api/v1/mock/run", json={}).status_code == 410

    def test_mock_service_triggers_broadcast_lifecycle(self):
        collector = _BroadcastCollector()
        result = self._run(collector, "e2e-001", 2.0, 0.5)

        assert result.status == TaskStatus.COMPLETED
        assert result.progress == 100

        calls = collector.calls
        assert len(calls) >= 4, f"Expected >= 4 broadcast calls, got {len(calls)}"

        statuses = [c[1].status for c in calls]
        assert statuses[0] == TaskStatus.PENDING
        assert TaskStatus.LOADING in statuses
        assert TaskStatus.RUNNING in statuses
        assert statuses[-1] == TaskStatus.COMPLETED

        running_progs = [c[1].progress for c in calls if c[1].status == TaskStatus.RUNNING]
        for i in range(1, len(running_progs)):
            assert running_progs[i] >= running_progs[i - 1]

        last_call = calls[-1]
        assert last_call[1].status == TaskStatus.COMPLETED
        assert last_call[1].progress == 100
        assert last_call[1].result_url is not None

    def test_broadcast_callback_is_injected(self):
        collector = _BroadcastCollector()
        self._run(collector, "inject-001", 1.0, 0.5)

        assert len(collector.calls) >= 1
        assert collector.calls[0][0] == "inject-001"

    def test_broadcast_preserves_task_id_consistency(self):
        collector = _BroadcastCollector()
        self._run(collector, "consistency-001", 1.0, 0.5)

        task_ids = {c[0] for c in collector.calls}
        assert task_ids == {"consistency-001"}, f"got {task_ids}"

    def test_broadcast_payload_has_required_fields(self):
        collector = _BroadcastCollector()
        self._run(collector, "fields-001", 1.0, 0.5)

        required = {"task_id", "status", "progress", "message", "updated_at"}
        assert collector.calls, "broadcast 未被调用"
        for task_id, result in collector.calls:
            d = result.to_dict()
            assert required.issubset(d.keys()), f"Missing keys: {required - d.keys()}"
            assert 0 <= d["progress"] <= 100
            assert isinstance(d["status"], str)

    def test_completed_task_broadcasts_terminal_state(self):
        collector = _BroadcastCollector()
        result = self._run(collector, "error-001", 0.5, 0.2)

        assert result.status == TaskStatus.COMPLETED
        assert collector.calls[-1][1].status == TaskStatus.COMPLETED


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------


class _AsyncMockWS:
    """Mock WebSocket that supports async send_json."""
    def __init__(self):
        self.messages: list = []

    async def send_json(self, data):
        self.messages.append(data)

    async def close(self):
        pass


class TestWebSocketIntegration:
    """Test that the ConnectionManager correctly bridges broadcast -> WS."""

    @pytest.mark.asyncio
    async def test_manager_broadcast_delivers_to_connected_ws(self):
        """
        Verify that when a WebSocket is connected and broadcast() is called,
        the message is delivered to that WebSocket.
        """
        from tests.test_websocket import _AsyncMockWS

        task_id = "integration-001"
        fake_ws = _AsyncMockWS()
        await manager.connect(task_id, fake_ws)

        result = PredictResult(
            task_id=task_id,
            status=TaskStatus.RUNNING,
            progress=50,
            message="Integration test",
        )
        count = await manager.broadcast(task_id, result)

        assert count == 1
        assert len(fake_ws.messages) == 1
        assert fake_ws.messages[0]["task_id"] == task_id
        assert fake_ws.messages[0]["status"] == "running"
        assert fake_ws.messages[0]["progress"] == 50

        await manager.disconnect(task_id, fake_ws)

    @pytest.mark.asyncio
    async def test_broadcast_fails_gracefully_for_unknown_task(self):
        """Broadcasting to an unknown task should return 0 silently."""
        result = PredictResult(
            task_id="unknown",
            status=TaskStatus.RUNNING,
            progress=50,
            message="no subscribers",
        )
        count = await manager.broadcast("nonexistent-task", result)
        assert count == 0

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up_connections(self):
        """After disconnect, the task should no longer be in active_tasks."""
        task_id = "cleanup-001"
        fake_ws = _AsyncMockWS()
        await manager.connect(task_id, fake_ws)
        assert task_id in manager.active_tasks
        assert manager.subscriber_count == 1

        await manager.disconnect(task_id, fake_ws)
        assert task_id not in manager.active_tasks
        assert manager.subscriber_count == 0
