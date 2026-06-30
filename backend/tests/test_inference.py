"""
Integration tests for the inference service layer.

Full call chain:
  Factory.create() → broadcast injected → predict(PredictRequest) → PredictResult

Uses pytest + pytest-asyncio + unittest.mock — ZERO network calls.

Run:
    cd backend
    python -m pytest tests/test_inference.py -v

Requires:
    pip install pytest pytest-asyncio httpx
"""

from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional

import pytest

# Ensure backend root is on sys.path
BACKEND_ROOT = os.path.join(os.path.dirname(__file__), "..")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.services.inference import (
    CogVideoXService,
    GPTSovitsService,
    InferenceServiceFactory,
    MusicGenService,
    PredictRequest,
    PredictResult,
    RetryConfig,
    TaskStatus,
    ConfigError,
    get_factory,
    reset_factory,
)
from app.services.inference.base import ErrorCategory, _classify_http_error
from app.services.inference.factory import _SERVICE_REGISTRY, _ALIASES


# ===========================================================================
# Fixtures
# ===========================================================================

SAMPLE_WAV_BYTES = b"\x00\x01\x02\x03" * 1000

FAKE_TTS_URL = "https://test-user/gpt-sovits-demo"
FAKE_MUSIC_URL = "https://huggingface.co/spaces/facebook/MusicGen"
FAKE_VIDEO_URL = "https://huggingface.co/spaces/THUDM/CogVideoX-2b"

FAKE_TTS_API = "https://test-user-gpt-sovits-demo.hf.space"
FAKE_MUSIC_API = "https://huggingface.co/spaces-facebook-musicgen.hf.space"
FAKE_VIDEO_API = "https://huggingface.co/spaces-thudm-cogvideox-2b.hf.space"


class BroadcastCapture:
    """Captures broadcast_callback calls for assertion."""

    def __init__(self):
        self.calls: list[tuple[str, PredictResult]] = []

    async def __call__(self, task_id: str, result: PredictResult):
        self.calls.append((task_id, result))


# ===========================================================================
# Test 1: Factory — creation, config resolution, broadcast injection
# ===========================================================================


class TestFactoryCreation:
    """Test InferenceServiceFactory creates correct service types."""

    def test_create_tts(self):
        factory = InferenceServiceFactory()
        svc = factory.create("tts", space_url=FAKE_TTS_URL)
        assert isinstance(svc, GPTSovitsService)
        assert svc.space_url == FAKE_TTS_URL

    def test_create_music(self):
        factory = InferenceServiceFactory()
        svc = factory.create("music", space_url=FAKE_MUSIC_URL)
        assert isinstance(svc, MusicGenService)

    def test_create_video(self):
        factory = InferenceServiceFactory()
        svc = factory.create("video", space_url=FAKE_VIDEO_URL)
        assert isinstance(svc, CogVideoXService)

    def test_alias_voice_maps_to_tts(self):
        factory = InferenceServiceFactory()
        svc = factory.create("voice", space_url=FAKE_TTS_URL)
        assert isinstance(svc, GPTSovitsService)

    def test_alias_t2v_maps_to_video(self):
        factory = InferenceServiceFactory()
        svc = factory.create("t2v", space_url=FAKE_VIDEO_URL)
        assert isinstance(svc, CogVideoXService)

    def test_unknown_service_type_raises(self):
        factory = InferenceServiceFactory()
        with pytest.raises(ConfigError, match="Unknown service type"):
            factory.create("unknown_service")

    def test_create_all(self):
        config = {
            "tts": {"space_url": FAKE_TTS_URL},
            "music": {"space_url": FAKE_MUSIC_URL},
            "video": {"space_url": FAKE_VIDEO_URL},
        }
        factory = InferenceServiceFactory(config)
        all_svcs = factory.create_all()
        assert "tts" in all_svcs
        assert "music" in all_svcs
        assert "video" in all_svcs
        assert isinstance(all_svcs["tts"], GPTSovitsService)
        assert isinstance(all_svcs["music"], MusicGenService)
        assert isinstance(all_svcs["video"], CogVideoXService)

    def test_cache_reuse_same_config(self):
        factory = InferenceServiceFactory()
        svc1 = factory.create("tts", space_url=FAKE_TTS_URL)
        svc2 = factory.create("tts", space_url=FAKE_TTS_URL)
        assert svc1 is svc2

    def test_no_cache_different_config(self):
        factory = InferenceServiceFactory()
        svc1 = factory.create("tts", space_url=FAKE_TTS_URL)
        svc2 = factory.create("tts", space_url="https://different.hf.space")
        assert svc1 is not svc2

    def test_config_dict_resolution(self):
        config = {
            "tts": {"space_url": "https://config-test.hf.space", "fn_index": 2}
        }
        factory = InferenceServiceFactory(config)
        svc = factory.create("tts")
        assert svc.space_url == "https://config-test.hf.space"
        assert svc.fn_index == 2

    def test_override_bypasses_config(self):
        config = {"tts": {"space_url": "https://config.hf.space"}}
        factory = InferenceServiceFactory(config)
        svc = factory.create("tts", space_url="https://override.hf.space")
        assert svc.space_url == "https://override.hf.space"

    def test_broadcast_injected_into_service(self):
        """Verify broadcast callback is wired into the service instance."""
        bc = BroadcastCapture()
        factory = InferenceServiceFactory()
        svc = factory.create("tts", space_url=FAKE_TTS_URL, broadcast=bc)
        assert svc.broadcast is bc

    def test_missing_space_url_raises(self, monkeypatch):
        """Ensure factory raises when no space_url is configured at all."""
        monkeypatch.delenv("GPT_SOVITS_SPACE_URL", raising=False)
        factory = InferenceServiceFactory()
        with pytest.raises(ConfigError, match="Missing required config"):
            factory.create("tts")

    def test_invalidate_clears_cache(self):
        factory = InferenceServiceFactory()
        svc1 = factory.create("tts", space_url=FAKE_TTS_URL)
        factory.invalidate("tts")
        svc2 = factory.create("tts", space_url=FAKE_TTS_URL)
        assert svc1 is not svc2

    def test_module_singleton(self):
        reset_factory()
        f1 = get_factory()
        f2 = get_factory()
        assert f1 is f2
        reset_factory()


# ===========================================================================
# Test 2: Unified predict() contract — full flow via Factory
# ===========================================================================


class TestPredictContract:
    """
    Test the complete chain:
      Factory.create(broadcast=...) → svc.predict(PredictRequest) → PredictResult
    """

    @pytest.fixture
    def broadcast(self):
        return BroadcastCapture()

    @pytest.fixture
    def factory(self):
        config = {
            "tts": {"space_url": FAKE_TTS_URL, "fn_index": 0},
            "music": {"space_url": FAKE_MUSIC_URL, "fn_index": 0},
            "video": {"space_url": FAKE_VIDEO_URL, "fn_index": 0},
        }
        return InferenceServiceFactory(config)

    # --- TTS ---

    @pytest.mark.asyncio
    async def test_tts_predict_success_via_factory(self, factory, broadcast):
        svc = factory.create("tts", broadcast=broadcast)
        assert isinstance(svc, GPTSovitsService)
        assert svc.broadcast is broadcast

        with patch.object(svc, "_do_submit") as mock_submit, \
             patch.object(svc, "_poll_events") as mock_poll:
            mock_submit.return_value = f"{FAKE_TTS_API}/api/predict/events/tts-ok"
            mock_poll.return_value = PredictResult(
                task_id="tts-001",
                status=TaskStatus.COMPLETED,
                progress=100,
                result_url=f"{FAKE_TTS_API}/file=/tmp/output.wav",
            )

            req = PredictRequest(
                service_type="tts",
                task_id="tts-001",
                payload={},
                extra={
                    "reference_audio": SAMPLE_WAV_BYTES,
                    "text": "你好世界",
                    "language": "zh",
                },
            )
            result = await svc.predict(req)

        assert result.status == TaskStatus.COMPLETED
        assert result.result_url is not None
        assert result.progress == 100
        assert result.is_terminal is True
        # Verify broadcast was called with progress updates
        assert len(broadcast.calls) >= 2
        statuses = [c[1].status for c in broadcast.calls]
        assert TaskStatus.PENDING in statuses
        assert TaskStatus.COMPLETED in statuses

    @pytest.mark.asyncio
    async def test_tts_predict_missing_reference_audio(self):
        """predict() fails gracefully when reference_audio is absent."""
        factory = InferenceServiceFactory()
        svc = factory.create("tts", space_url=FAKE_TTS_URL)

        req = PredictRequest(
            service_type="tts",
            task_id="tts-bad",
            payload={},
            extra={"text": "hello"},  # no reference_audio
        )
        result = await svc.predict(req)

        assert result.status == TaskStatus.FAILED
        assert "reference_audio" in result.error.lower()

    @pytest.mark.asyncio
    async def test_tts_predict_missing_text(self):
        factory = InferenceServiceFactory()
        svc = factory.create("tts", space_url=FAKE_TTS_URL)

        req = PredictRequest(
            service_type="tts",
            task_id="tts-bad2",
            payload={},
            extra={"reference_audio": SAMPLE_WAV_BYTES},  # no text
        )
        result = await svc.predict(req)

        assert result.status == TaskStatus.FAILED
        assert "text" in result.error.lower()

    # --- Music ---

    @pytest.mark.asyncio
    async def test_music_predict_success_via_factory(self, factory, broadcast):
        svc = factory.create("music", broadcast=broadcast)
        assert isinstance(svc, MusicGenService)

        with patch.object(svc, "_do_submit") as mock_submit, \
             patch.object(svc, "_poll_events") as mock_poll:
            mock_submit.return_value = f"{FAKE_MUSIC_API}/api/predict/events/music-ok"
            mock_poll.return_value = PredictResult(
                task_id="music-001",
                status=TaskStatus.COMPLETED,
                progress=100,
                result_url=f"{FAKE_MUSIC_API}/file=/tmp/music.wav",
            )

            req = PredictRequest(
                service_type="music",
                task_id="music-001",
                payload={},
                extra={"prompt": "upbeat jazz piano", "duration": 15.0},
            )
            result = await svc.predict(req)

        assert result.status == TaskStatus.COMPLETED
        assert result.result_url is not None
        assert result.is_terminal is True

    @pytest.mark.asyncio
    async def test_music_predict_missing_prompt(self):
        factory = InferenceServiceFactory()
        svc = factory.create("music", space_url=FAKE_MUSIC_URL)

        req = PredictRequest(
            service_type="music",
            task_id="music-bad",
            payload={},
            extra={},
        )
        result = await svc.predict(req)

        assert result.status == TaskStatus.FAILED
        assert "prompt" in result.error.lower()

    # --- Video ---

    @pytest.mark.asyncio
    async def test_video_predict_success_via_factory(self, factory, broadcast):
        svc = factory.create("video", broadcast=broadcast)
        assert isinstance(svc, CogVideoXService)

        with patch.object(svc, "_do_submit") as mock_submit, \
             patch.object(svc, "_poll_events") as mock_poll:
            mock_submit.return_value = f"{FAKE_VIDEO_API}/api/predict/events/video-ok"
            mock_poll.return_value = PredictResult(
                task_id="video-001",
                status=TaskStatus.COMPLETED,
                progress=100,
                result_url=f"{FAKE_VIDEO_API}/file=/tmp/video.mp4",
            )

            req = PredictRequest(
                service_type="video",
                task_id="video-001",
                payload={},
                extra={"prompt": "a cat playing piano"},
            )
            result = await svc.predict(req)

        assert result.status == TaskStatus.COMPLETED
        assert result.result_url is not None
        assert result.result_url.endswith(".mp4")
        assert result.is_terminal is True

    @pytest.mark.asyncio
    async def test_video_predict_missing_prompt(self):
        factory = InferenceServiceFactory()
        svc = factory.create("video", space_url=FAKE_VIDEO_URL)

        req = PredictRequest(
            service_type="video",
            task_id="video-bad",
            payload={},
            extra={},
        )
        result = await svc.predict(req)

        assert result.status == TaskStatus.FAILED
        assert "prompt" in result.error.lower()


# ===========================================================================
# Test 3: End-to-end Factory → predict → result with cold-start simulation
# ===========================================================================


class TestColdStartFlow:
    """Simulate the cold-start retry path through the full chain."""

    @pytest.mark.asyncio
    async def test_tts_cold_start_then_success(self):
        """First _do_submit returns None (sleeping), second succeeds."""
        factory = InferenceServiceFactory()
        svc = factory.create("tts", space_url=FAKE_TTS_URL)

        with patch("asyncio.sleep", return_value=None):
            with patch.object(svc, "_do_submit") as mock_submit, \
                 patch.object(svc, "_poll_events") as mock_poll:
                mock_submit.side_effect = [
                    None, None, f"{FAKE_TTS_API}/api/predict/events/ok"
                ]
                mock_poll.return_value = PredictResult(
                    task_id="cold-1",
                    status=TaskStatus.COMPLETED,
                    progress=100,
                    result_url=f"{FAKE_TTS_API}/file=/out.wav",
                )

                req = PredictRequest(
                    service_type="tts",
                    task_id="cold-1",
                    payload={},
                    extra={
                        "reference_audio": SAMPLE_WAV_BYTES,
                        "text": "重试测试",
                    },
                )
                result = await svc.predict(req)

        assert result.status == TaskStatus.COMPLETED
        assert mock_submit.call_count == 3  # 2 failures + 1 success

    @pytest.mark.asyncio
    async def test_music_cold_start_then_success(self):
        factory = InferenceServiceFactory()
        svc = factory.create("music", space_url=FAKE_MUSIC_URL)

        with patch("asyncio.sleep", return_value=None):
            with patch.object(svc, "_do_submit") as mock_submit, \
                 patch.object(svc, "_poll_events") as mock_poll:
                mock_submit.side_effect = [
                    None, f"{FAKE_MUSIC_API}/api/predict/events/ok"
                ]
                mock_poll.return_value = PredictResult(
                    task_id="cold-2",
                    status=TaskStatus.COMPLETED,
                    progress=100,
                    result_url=f"{FAKE_MUSIC_API}/file=/out.wav",
                )

                req = PredictRequest(
                    service_type="music",
                    task_id="cold-2",
                    payload={},
                    extra={"prompt": "rock solo"},
                )
                result = await svc.predict(req)

        assert result.status == TaskStatus.COMPLETED
        assert mock_submit.call_count == 2

    @pytest.mark.asyncio
    async def test_cold_start_exhausted_returns_structured_error(self):
        """When all cold-start retries fail, return FAILED with error_code."""
        factory = InferenceServiceFactory()
        svc = factory.create("tts", space_url=FAKE_TTS_URL)

        # Always return None (Space never wakes up)
        with patch.object(svc, "_do_submit", return_value=None), \
             patch("asyncio.sleep", return_value=None):
            req = PredictRequest(
                service_type="tts",
                task_id="cold-fail",
                payload={},
                extra={
                    "reference_audio": SAMPLE_WAV_BYTES,
                    "text": "永远醒不来",
                },
            )
            result = await svc.predict(req)

        assert result.status == TaskStatus.FAILED
        assert result.error_code == "COLD_START_EXHAUSTED"
        assert result.retryable is True
        assert result.last_attempt == 3  # max_cold_start_retries

    @pytest.mark.asyncio
    async def test_network_connect_error_retries_then_fails(self):
        """
        _do_submit raises httpx.ConnectError repeatedly.
        Base predict() should retry with exponential backoff and
        eventually return FAILED with structured error — never crash.
        """
        import httpx

        factory = InferenceServiceFactory()
        svc = factory.create("tts", space_url=FAKE_TTS_URL)

        # Use a short retry config so the test runs quickly
        svc.retry_config = RetryConfig(
            max_network_retries=3,
            network_base_delay=0.01,   # 10ms
            network_max_delay=0.05,
            network_backoff_factor=2.0,
            # Cold-start config also shortened
            max_cold_start_retries=2,
            cold_start_base_delay=0.01,
            cold_start_max_delay=0.05,
        )

        with patch.object(svc, "_do_submit", side_effect=httpx.ConnectError("Connection refused")), \
             patch.object(svc, "_poll_events") as mock_poll:
            mock_poll.return_value = PredictResult(
                task_id="net-fail",
                status=TaskStatus.COMPLETED,
                progress=100,
            )

            req = PredictRequest(
                service_type="tts",
                task_id="net-fail",
                payload={},
                extra={
                    "reference_audio": SAMPLE_WAV_BYTES,
                    "text": "网络重试测试",
                    "max_wait": 10,
                },
            )
            result = await svc.predict(req)

        # Should have retried and eventually returned FAILED
        assert result.status == TaskStatus.FAILED
        assert result.retryable is True
        assert result.last_attempt >= 1
        # Should NOT have raised an exception
        assert result.error is not None
        assert "ConnectError" in result.error or "Connection refused" in result.error

    @pytest.mark.asyncio
    async def test_read_timeout_retries_then_succeeds(self):
        """
        _do_submit raises httpx.ReadTimeout once, then succeeds.
        Base predict() should retry with backoff and proceed to polling.
        """
        import httpx

        factory = InferenceServiceFactory()
        svc = factory.create("music", space_url=FAKE_MUSIC_URL)

        # Short retry config for fast test
        svc.retry_config = RetryConfig(
            max_network_retries=5,
            network_base_delay=0.01,
            network_max_delay=0.05,
            network_backoff_factor=2.0,
            max_cold_start_retries=2,
            cold_start_base_delay=0.01,
            cold_start_max_delay=0.05,
        )

        call_count = 0

        async def flaky_submit(task_id: str, payload: dict) -> Optional[str]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ReadTimeout("Read timed out")
            return f"{FAKE_MUSIC_API}/api/predict/events/ok"

        with patch("asyncio.sleep", return_value=None):
            with patch.object(svc, "_do_submit", side_effect=flaky_submit), \
                 patch.object(svc, "_poll_events") as mock_poll:
                mock_poll.return_value = PredictResult(
                    task_id="timeout-retry",
                    status=TaskStatus.COMPLETED,
                    progress=100,
                    result_url=f"{FAKE_MUSIC_API}/file=/out.wav",
                )

                req = PredictRequest(
                    service_type="music",
                    task_id="timeout-retry",
                    payload={},
                    extra={
                        "prompt": "test prompt",
                        "max_wait": 10,
                    },
                )
                result = await svc.predict(req)

        assert result.status == TaskStatus.COMPLETED
        assert result.result_url is not None
        assert call_count == 2  # 1 timeout + 1 success

    @pytest.mark.asyncio
    async def test_make_failed_result_factory(self):
        """
        _make_failed_result produces a properly structured PredictResult(FAILED).
        """
        factory = InferenceServiceFactory()
        svc = factory.create("tts", space_url=FAKE_TTS_URL)

        result = svc._make_failed_result(
            task_id="fail-test",
            error="Space failed to wake",
            error_code="COLD_START_EXHAUSTED",
            last_attempt=3,
            retryable=True,
            cumulative_error="ConnectError: Connection refused",
        )

        assert result.status == TaskStatus.FAILED
        assert result.error_code == "COLD_START_EXHAUSTED"
        assert result.retryable is True
        assert result.last_attempt == 3
        assert "Space failed to wake" in result.error
        assert "ConnectError" in result.error
        assert result.is_terminal is True
        assert result.progress == 0


# ===========================================================================
# Test 4: PredictResult contract — new structured error fields
# ===========================================================================


class TestPredictResultContract:
    """Verify PredictResult interface is correct with new fields."""

    def test_completed_result(self):
        r = PredictResult(
            task_id="t1",
            status=TaskStatus.COMPLETED,
            progress=100,
            result_url="https://example.com/out.wav",
        )
        assert r.is_terminal is True
        assert r.to_dict()["status"] == "completed"

    def test_failed_result_with_error_code(self):
        r = PredictResult(
            task_id="t2",
            status=TaskStatus.FAILED,
            progress=0,
            error="Timeout",
            error_code="POLL_TIMEOUT",
            retryable=True,
            last_attempt=5,
        )
        assert r.is_terminal is True
        assert r.error_code == "POLL_TIMEOUT"
        assert r.retryable is True
        assert r.last_attempt == 5

    def test_failed_result_without_optional_fields(self):
        r = PredictResult(
            task_id="t3",
            status=TaskStatus.FAILED,
            progress=0,
            error="Simple error",
        )
        assert r.error_code is None
        assert r.retryable is False
        assert r.last_attempt == 0

    def test_running_not_terminal(self):
        r = PredictResult(
            task_id="t4",
            status=TaskStatus.RUNNING,
            progress=50,
        )
        assert r.is_terminal is False

    def test_cancelled_is_terminal(self):
        r = PredictResult(
            task_id="t5",
            status=TaskStatus.CANCELLED,
            progress=0,
        )
        assert r.is_terminal is True

    def test_metadata_passthrough(self):
        r = PredictResult(
            task_id="t6",
            status=TaskStatus.COMPLETED,
            progress=100,
            metadata={"filename": "song.wav", "duration": 10.5},
        )
        assert r.to_dict()["metadata"]["filename"] == "song.wav"

    def test_task_progress_backward_compat(self):
        from app.services.inference import TaskProgress
        tp = TaskProgress(
            task_id="t7",
            status=TaskStatus.COMPLETED,
            progress=100,
            result_url="http://example.com/a.wav",
        )
        assert isinstance(tp, PredictResult)
        assert tp.is_terminal is True

    def test_to_dict_includes_new_fields(self):
        r = PredictResult(
            task_id="t8",
            status=TaskStatus.FAILED,
            progress=0,
            error="OOM",
            error_code="INFRA_ERROR",
            retryable=True,
            last_attempt=3,
        )
        d = r.to_dict()
        assert d["error_code"] == "INFRA_ERROR"
        assert d["retryable"] is True
        assert d["last_attempt"] == 3


# ===========================================================================
# Test 5: Error classification
# ===========================================================================


class TestErrorClassification:
    """Verify _classify_http_error distinguishes transient vs permanent."""

    def test_connect_error_is_transient(self):
        import httpx
        exc = httpx.ConnectError("refused")
        assert _classify_http_error(exc) == ErrorCategory.TRANSIENT

    def test_read_timeout_is_transient(self):
        import httpx
        exc = httpx.ReadTimeout("timeout")
        assert _classify_http_error(exc) == ErrorCategory.TRANSIENT

    def test_remote_protocol_error_is_transient(self):
        import httpx
        exc = httpx.RemoteProtocolError("broken pipe")
        assert _classify_http_error(exc) == ErrorCategory.TRANSIENT

    def test_pool_timeout_is_transient(self):
        import httpx
        exc = httpx.PoolTimeout("pool timeout")
        assert _classify_http_error(exc) == ErrorCategory.TRANSIENT

    def test_unknown_error_is_infra(self):
        exc = RuntimeError("something weird")
        assert _classify_http_error(exc) == ErrorCategory.INFRASTRUCTURE


# ===========================================================================
# Test 6: RetryConfig — dual-layer backoff
# ===========================================================================


class TestRetryConfig:
    def test_cold_start_backoff(self):
        cfg = RetryConfig(
            cold_start_base_delay=60,
            cold_start_backoff_factor=2,
            cold_start_max_delay=300,
        )
        assert cfg.get_cold_start_delay(0) == 60
        assert cfg.get_cold_start_delay(1) == 120
        assert cfg.get_cold_start_delay(2) == 240
        assert cfg.get_cold_start_delay(5) == 300  # capped

    def test_network_backoff(self):
        cfg = RetryConfig(
            network_base_delay=1,
            network_backoff_factor=2,
            network_max_delay=30,
        )
        assert cfg.get_network_delay(0) == 1
        assert cfg.get_network_delay(1) == 2
        assert cfg.get_network_delay(2) == 4
        assert cfg.get_network_delay(5) == 30  # capped

    def test_default_config(self):
        cfg = RetryConfig()
        assert cfg.max_cold_start_retries == 3
        assert cfg.cold_start_base_delay == 60
        assert cfg.network_base_delay == 1
        assert cfg.network_max_delay == 30
        assert cfg.retryable_http_codes == [502, 503, 504]


# ===========================================================================
# Test 7: Registry & aliases
# ===========================================================================


class TestServiceRegistry:
    def test_all_types_registered(self):
        assert "tts" in _SERVICE_REGISTRY
        assert "music" in _SERVICE_REGISTRY
        assert "video" in _SERVICE_REGISTRY

    def test_registry_class_mapping(self):
        cls, _ = _SERVICE_REGISTRY["tts"]
        assert cls is GPTSovitsService
        cls, _ = _SERVICE_REGISTRY["music"]
        assert cls is MusicGenService
        cls, _ = _SERVICE_REGISTRY["video"]
        assert cls is CogVideoXService

    def test_aliases(self):
        assert _ALIASES.get("voice") == "tts"
        assert _ALIASES.get("audio") == "tts"
        assert _ALIASES.get("t2v") == "video"
        assert _ALIASES.get("text2video") == "video"
        assert _ALIASES.get("music_gen") == "music"


# ===========================================================================
# Test 8: Cancel
# ===========================================================================


class TestCancel:
    @pytest.mark.asyncio
    async def test_cancel_returns_cancelled_status(self):
        factory = InferenceServiceFactory()
        svc = factory.create("tts", space_url=FAKE_TTS_URL)
        result = await svc.cancel("task-999")
        assert result.status == TaskStatus.CANCELLED
        assert result.is_terminal is True
        assert "cancelled" in result.message.lower()
