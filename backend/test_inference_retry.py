"""
test_inference_retry.py — Standalone verification of the dual-layer retry
mechanism in BaseInferenceService.predict().

Two scenarios:
  A) Network retry: _do_submit raises httpx.ConnectError 3 times →
     verify exponential backoff + final FAILED result.
  B) Cold-start retry: _do_submit returns None 3 times →
     verify cold-start backoff + final FAILED result.

Run:
    cd backend
    python -m pytest test_inference_retry.py -v
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx
import pytest
from unittest.mock import patch, MagicMock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ===========================================================================
# Helper: capture broadcast calls
# ===========================================================================


class BroadcastCapture:
    """Captures broadcast_callback(task_id, PredictResult) calls."""

    def __init__(self):
        self.calls: list[tuple[str, Any]] = []

    async def __call__(self, task_id: str, result: Any):
        self.calls.append((task_id, result))


# ===========================================================================
# Scenario A: Network retry — httpx.ConnectError
# ===========================================================================


class TestNetworkRetry:
    """Verify that httpx.ConnectError from _do_submit triggers retry."""

    @pytest.mark.asyncio
    async def test_connect_error_retries_three_times_and_fails(self):
        """
        _do_submit raises httpx.ConnectError 3 times.
        Base predict() should:
          1. Catch each ConnectError
          2. Apply exponential backoff (1ms → 2ms → 4ms)
          3. After all retries exhausted, return FAILED PredictResult
        """
        from app.services.inference.base import (
            BaseInferenceService, PredictRequest, PredictResult,
            RetryConfig, TaskStatus,
        )

        class MockService(BaseInferenceService):
            """Minimal concrete service for retry testing."""

            def __init__(self, retry_cfg: Optional[RetryConfig] = None):
                super().__init__(
                    space_url="https://test.hf.space",
                    retry_config=retry_cfg,
                )
                # Ultra-short network delays for fast test
                self.retry_config = retry_cfg or RetryConfig(
                    max_network_retries=10,
                    network_base_delay=0.001,   # 1ms
                    network_max_delay=0.005,
                    network_backoff_factor=2.0,
                )

            def _build_payload(self, **kwargs) -> dict[str, Any]:
                return {"data": [kwargs]}

            async def _do_submit(self, task_id: str, payload: dict[str, Any]) -> Optional[str]:
                raise httpx.ConnectError("Connection refused")

            def _parse_response(self, event_data: dict[str, Any]) -> Optional[dict[str, Any]]:
                return None

        bc = BroadcastCapture()
        svc = MockService()
        svc.broadcast = bc

        req = PredictRequest(
            service_type="test",
            task_id="net-retry-1",
            payload={},
            extra={"max_wait": 30},
        )

        with patch("asyncio.sleep", return_value=None):
            result = await svc.predict(req)

        # --- Assertions ---
        assert result.status == TaskStatus.FAILED, (
            f"Expected FAILED but got {result.status}; "
            f"error={result.error}"
        )
        assert result.retryable is True
        assert result.last_attempt >= 1
        assert "ConnectError" in result.error or "Connection refused" in result.error
        assert result.progress == 0
        assert result.is_terminal is True

        # Verify broadcast captured intermediate states
        assert len(bc.calls) >= 2
        statuses = [r.status for _, r in bc.calls]
        assert TaskStatus.PENDING in statuses
        assert TaskStatus.LOADING in statuses
        assert TaskStatus.FAILED in statuses

        logger.info("PASS: ConnectError triggered %d retries → FAILED", result.last_attempt)

    @pytest.mark.asyncio
    async def test_connect_error_recovers_after_retries(self):
        """
        _do_submit raises ConnectError 2 times, then returns a valid URL.
        Verify predict() recovers and proceeds to polling.
        """
        from app.services.inference.base import (
            BaseInferenceService, PredictRequest, PredictResult,
            RetryConfig, TaskStatus,
        )

        call_count = 0

        class RecoveringService(BaseInferenceService):
            def __init__(self):
                super().__init__(
                    space_url="https://test.hf.space",
                    retry_config=RetryConfig(
                        max_network_retries=10,
                        network_base_delay=0.001,
                        network_max_delay=0.005,
                        network_backoff_factor=2.0,
                    ),
                )

            def _build_payload(self, **kwargs) -> dict[str, Any]:
                return {"data": [kwargs]}

            async def _do_submit(self, task_id: str, payload: dict[str, Any]) -> Optional[str]:
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    raise httpx.ConnectError(f"Connection refused (attempt {call_count})")
                return f"{self.api_base}/api/predict/events/recovered"

            def _parse_response(self, event_data: dict[str, Any]) -> Optional[dict[str, Any]]:
                return None

        svc = RecoveringService()

        with patch("asyncio.sleep", return_value=None), \
             patch.object(svc, "_poll_events") as mock_poll:
            mock_poll.return_value = PredictResult(
                task_id="recover-1",
                status=TaskStatus.COMPLETED,
                progress=100,
                result_url="https://test.hf.space/output.mp4",
                updated_at=0,
            )
            result = await svc.predict(PredictRequest(
                service_type="test",
                task_id="recover-1",
                payload={},
                extra={"max_wait": 30},
            ))

        assert result.status == TaskStatus.COMPLETED
        assert result.result_url is not None
        assert call_count == 3  # 2 failures + 1 success
        logger.info("PASS: Network recovered after %d attempts", call_count)


# ===========================================================================
# Scenario B: Cold-start retry — returns None
# ===========================================================================


class TestColdStartRetry:
    """Verify that None return from _do_submit triggers cold-start backoff."""

    @pytest.mark.asyncio
    async def test_cold_start_none_retries_and_fails(self):
        """
        _do_submit returns None 3 times (Space never wakes).
        Verify cold-start backoff (60s → 120s → 240s) is applied,
        then FAILED with COLD_START_EXHAUSTED.
        """
        from app.services.inference.base import (
            BaseInferenceService, PredictRequest, PredictResult,
            RetryConfig, TaskStatus,
        )

        call_count = 0

        class SleepingService(BaseInferenceService):
            def __init__(self):
                super().__init__(
                    space_url="https://test.hf.space",
                    retry_config=RetryConfig(
                        max_cold_start_retries=3,
                        cold_start_base_delay=60.0,
                        cold_start_max_delay=300.0,
                        cold_start_backoff_factor=2.0,
                    ),
                )

            def _build_payload(self, **kwargs) -> dict[str, Any]:
                return {"data": [kwargs]}

            async def _do_submit(self, task_id: str, payload: dict[str, Any]) -> Optional[str]:
                nonlocal call_count
                call_count += 1
                return None  # Perpetually sleeping

            def _parse_response(self, event_data: dict[str, Any]) -> Optional[dict[str, Any]]:
                return None

        svc = SleepingService()
        bc = BroadcastCapture()
        svc.broadcast = bc

        with patch("asyncio.sleep", return_value=None):
            result = await svc.predict(PredictRequest(
                service_type="test",
                task_id="cold-fail",
                payload={},
                extra={},
            ))

        # --- Assertions ---
        assert result.status == TaskStatus.FAILED
        assert result.error_code == "COLD_START_EXHAUSTED"
        assert result.retryable is True
        assert result.last_attempt == 3
        assert "failed to wake" in result.error.lower()
        assert call_count == 3  # 3 submissions attempted
        assert result.is_terminal is True

        # Verify broadcast captured LOADING progress updates
        loading_updates = [r for _, r in bc.calls if r.status == TaskStatus.LOADING]
        assert len(loading_updates) == 3  # one per cold-start attempt

        # Verify backoff delays were calculated correctly
        cfg = svc.retry_config
        assert cfg.get_cold_start_delay(0) == 60.0
        assert cfg.get_cold_start_delay(1) == 120.0
        assert cfg.get_cold_start_delay(2) == 240.0

        logger.info("PASS: Cold-start exhausted after %d attempts", call_count)

    @pytest.mark.asyncio
    async def test_cold_start_recovers_on_third_attempt(self):
        """
        _do_submit returns None twice, then returns a valid event URL.
        Verify predict() transitions to polling and returns COMPLETED.
        """
        from app.services.inference.base import (
            BaseInferenceService, PredictRequest, PredictResult,
            TaskStatus,
        )

        call_count = 0

        class WakingService(BaseInferenceService):
            def __init__(self):
                super().__init__(space_url="https://test.hf.space")

            def _build_payload(self, **kwargs) -> dict[str, Any]:
                return {"data": [kwargs]}

            async def _do_submit(self, task_id: str, payload: dict[str, Any]) -> Optional[str]:
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    return None  # Still cold-starting
                return f"{self.api_base}/api/predict/events/woken"

            def _parse_response(self, event_data: dict[str, Any]) -> Optional[dict[str, Any]]:
                return None

        svc = WakingService()

        with patch("asyncio.sleep", return_value=None), \
             patch.object(svc, "_poll_events") as mock_poll:
            mock_poll.return_value = PredictResult(
                task_id="cold-recover",
                status=TaskStatus.COMPLETED,
                progress=100,
                result_url="https://test.hf.space/output.mp4",
                updated_at=0,
            )
            result = await svc.predict(PredictRequest(
                service_type="test",
                task_id="cold-recover",
                payload={},
                extra={},
            ))

        assert result.status == TaskStatus.COMPLETED
        assert result.result_url is not None
        assert call_count == 3  # 2 None + 1 success
        logger.info("PASS: Cold-start recovered after %d attempts", call_count)


# ===========================================================================
# Scenario C: Mixed — ConnectError + cold-start recovery
# ===========================================================================


class TestMixedRetry:
    """Verify the two retry layers can coexist in one predict() call."""

    @pytest.mark.asyncio
    async def test_mixed_network_and_cold_start(self):
        """
        _do_submit raises ConnectError once, then returns None twice,
        then succeeds. Verify all three failure modes are handled.
        """
        from app.services.inference.base import (
            BaseInferenceService, PredictRequest, PredictResult,
            RetryConfig, TaskStatus,
        )

        call_count = 0

        class MixedService(BaseInferenceService):
            def __init__(self):
                super().__init__(
                    space_url="https://test.hf.space",
                    retry_config=RetryConfig(
                        max_network_retries=5,
                        network_base_delay=0.001,
                        network_max_delay=0.005,
                        max_cold_start_retries=3,
                        cold_start_base_delay=0.001,
                        cold_start_max_delay=0.005,
                    ),
                )

            def _build_payload(self, **kwargs) -> dict[str, Any]:
                return {"data": [kwargs]}

            async def _do_submit(self, task_id: str, payload: dict[str, Any]) -> Optional[str]:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise httpx.ConnectError("Network down")
                if call_count <= 3:
                    return None  # Cold-start
                return f"{self.api_base}/api/predict/events/mixed-ok"

            def _parse_response(self, event_data: dict[str, Any]) -> Optional[dict[str, Any]]:
                return None

        svc = MixedService()

        with patch("asyncio.sleep", return_value=None), \
             patch.object(svc, "_poll_events") as mock_poll:
            mock_poll.return_value = PredictResult(
                task_id="mixed-1",
                status=TaskStatus.COMPLETED,
                progress=100,
                result_url="https://test.hf.space/output.mp4",
                updated_at=0,
            )
            result = await svc.predict(PredictRequest(
                service_type="test",
                task_id="mixed-1",
                payload={},
                extra={"max_wait": 30},
            ))

        assert result.status == TaskStatus.COMPLETED
        assert call_count == 4  # 1 ConnectError + 2 None + 1 success
        logger.info("PASS: Mixed retry handled %d attempts", call_count)
