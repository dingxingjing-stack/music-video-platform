"""
Inference Service Base Module

Abstract base classes and shared utilities for all AI inference services.
Handles cold-start detection, dual-strategy exponential backoff retry,
timeout management, and WebSocket progress broadcasting.

Design principles:
  - Decoupled from FastAPI route layer (uses callback injection)
  - Safe JSON parsing (all .get() chains, never direct key access)
  - Connection lifecycle managed via async context manager
  - No circular imports
  - Unified predict() contract enforced by ABC

Architecture:
  BaseInferenceService.predict()  <-  unified entry point (subclasses override)
      |- _build_payload(**kwargs)  <-  abstract: build request body
      |- _do_submit(task_id, payload)  <-  abstract: send to HF Space
      |- _parse_response(event)  <-  abstract: parse event stream

Retry Strategy (dual-layer):
  Layer 1 — Cold-start backoff:    60s -> 120s -> 240s  (for Space sleeping)
  Layer 2 — Network jitter backoff: 1s -> 2s -> 4s      (for HTTP transients)
  Both use exponential growth with configurable base/factor/cap.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Optional

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & Data Classes
# ---------------------------------------------------------------------------


class TaskStatus(str, Enum):
    """Task lifecycle states."""

    PENDING = "pending"
    QUEUED = "queued"
    LOADING = "loading"       # Space cold-start: model loading into VRAM
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SLEEPING = "sleeping"     # Space is asleep; next request triggers cold-start


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


class ErrorCategory(str, Enum):
    """Categorise errors to decide whether retry is worthwhile."""

    TRANSIENT = "transient"       # Network hiccup, 503, timeout -- retry
    PERMANENT = "permanent"       # Bad input, 4xx -- do not retry
    INFRASTRUCTURE = "infra"      # Space down, OOM -- maybe retry with backoff


def _classify_http_error(exc: Exception) -> ErrorCategory:
    """Classify an exception to decide retry policy."""
    if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError)):
        return ErrorCategory.TRANSIENT
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code < 500:
            return ErrorCategory.PERMANENT
        return ErrorCategory.TRANSIENT
    if isinstance(exc, (httpx.PoolTimeout, httpx.ProxyError)):
        return ErrorCategory.TRANSIENT
    return ErrorCategory.INFRASTRUCTURE


# ---------------------------------------------------------------------------
# PredictRequest / PredictResult -- unified I/O contracts
# ---------------------------------------------------------------------------


@dataclass(frozen=False)
class PredictRequest:
    """
    Unified input contract for all inference services.

    Attributes:
        service_type: One of ``"tts"``, ``"music"``, ``"video"``.
        task_id: Caller-assigned unique identifier.
        payload: Service-specific dict built by ``_build_payload()``.
        extra: Arbitrary kwargs forwarded to the service's convenience method.
    """

    service_type: str
    task_id: str
    payload: dict[str, Any]
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=False)
class PredictResult:
    """
    Unified output contract for all inference services.

    All consumers (routes, workers, frontends) read from this single shape.
    Failed results carry structured error information for debugging.
    """

    task_id: str
    status: TaskStatus
    progress: int               # 0-100
    message: str = ""
    result_url: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None      # machine-readable error code
    retryable: bool = False               # whether the caller should retry
    last_attempt: int = 0                 # which attempt failed (1-based)
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "result_url": self.result_url,
            "error": self.error,
            "error_code": self.error_code,
            "retryable": self.retryable,
            "last_attempt": self.last_attempt,
            "metadata": self.metadata,
            "updated_at": self.updated_at,
        }

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        )


@dataclass
class TaskProgress(PredictResult):
    """
    Backward-compatible alias: TaskProgress IS a PredictResult.

    Existing code that references TaskProgress continues to work.
    """

    pass


# ---------------------------------------------------------------------------
# Callback type alias -- avoids circular import with main.py
# ---------------------------------------------------------------------------

BroadcastCallback = Callable[[str, PredictResult], Coroutine[Any, Any, None]]


# ---------------------------------------------------------------------------
# Dual-layer Retry Configuration
# ---------------------------------------------------------------------------


@dataclass
class RetryConfig:
    """
    Two independent backoff strategies for different failure modes.

    cold_start_backoff:
      Used when _do_submit returns None (Space sleeping / cold-starting).
      Long intervals because loading a model into VRAM takes minutes.
      Default: 60s -> 120s -> 240s (cap 300s)

    network_backoff:
      Used for HTTP transients (ConnectError, ReadTimeout) during submit
      or event polling. Short intervals because these are usually fleeting.
      Default: 1s -> 2s -> 4s (cap 30s)
    """

    # -- Cold-start layer --
    max_cold_start_retries: int = 3
    cold_start_base_delay: float = 60.0
    cold_start_max_delay: float = 300.0
    cold_start_backoff_factor: float = 2.0

    # -- Network layer --
    max_network_retries: int = 5
    network_base_delay: float = 1.0
    network_max_delay: float = 30.0
    network_backoff_factor: float = 2.0

    # -- Shared --
    retryable_http_codes: list[int] = field(
        default_factory=lambda: [502, 503, 504]
    )

    def get_cold_start_delay(self, attempt: int) -> float:
        delay = self.cold_start_base_delay * (self.cold_start_backoff_factor ** attempt)
        return min(delay, self.cold_start_max_delay)

    def get_network_delay(self, attempt: int) -> float:
        delay = self.network_base_delay * (self.network_backoff_factor ** attempt)
        return min(delay, self.network_max_delay)


DEFAULT_RETRY_CONFIG = RetryConfig()


# ---------------------------------------------------------------------------
# Base Inference Service
# ---------------------------------------------------------------------------


class BaseInferenceService(ABC):
    """
    Abstract base for all AI inference services.

    **Unified contract** -- every service MUST implement::

        async def predict(self, request: PredictRequest) -> PredictResult

    The base class provides:
      - Dual-layer exponential backoff (cold-start + network transient)
      - HTTP error classification (transient vs permanent)
      - WebSocket progress broadcasting
      - Event-stream polling with jitter-aware retry
      - Health checking
      - HTTP client lifecycle management
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        space_url: str,
        api_token: Optional[str] = None,
        retry_config: Optional[RetryConfig] = None,
        broadcast: Optional[BroadcastCallback] = None,
        http_timeout: float = 600.0,
    ) -> None:
        self.space_url = space_url.rstrip("/")
        self.api_token = api_token
        self.retry_config = retry_config or DEFAULT_RETRY_CONFIG
        self.broadcast = broadcast
        self.http_timeout = http_timeout

        # Derive api_base from space_url — supports two formats:
        #   1) https://huggingface.co/spaces/<owner>/<name>
        #      → https://<owner>-<name>.hf.space
        #   2) https://<owner>-<name>.hf.space
        #      → https://<owner>-<name>.hf.space (unchanged)
        host = self.space_url.split("//")[-1]
        if host.startswith("huggingface.co/spaces/"):
            # Extract owner/name and construct *.hf.space domain
            path = host[len("huggingface.co/spaces/"):]
            # Replace / with - to form the subdomain
            subdomain = path.replace("/", "-")
            self.api_base = f"https://{subdomain}.hf.space"
        else:
            self.api_base = f"https://{host}"

        self._http_client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "BaseInferenceService":
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.http_timeout, connect=30.0),
            headers=self._auth_header(),
        )
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def _auth_header(self) -> dict[str, str]:
        if self.api_token:
            return {"Authorization": f"Bearer {self.api_token}"}
        return {}

    # ------------------------------------------------------------------
    # PUBLIC API -- the unified contract
    # ------------------------------------------------------------------

    async def predict(self, request: PredictRequest) -> PredictResult:
        """
        Unified entry-point for ALL inference services.

        Orchestrates the full lifecycle:
          1. PENDING  -> broadcast initial state
          2. LOADING  -> cold-start retry loop (exponential backoff)
          3. RUNNING  -> event-stream polling (with network jitter retry)
          4. COMPLETED / FAILED -> broadcast final state

        Subclasses MUST implement ``_do_submit()`` and ``_parse_response()``;
        this method handles all retry, timeout, and progress logic.
        """
        task_id = request.task_id
        max_wait = request.extra.get("max_wait", 900)
        deadline = time.monotonic() + max_wait

        # ── Phase 0: Pending ──────────────────────────────────────
        result = PredictResult(
            task_id=task_id,
            status=TaskStatus.PENDING,
            progress=0,
            message="Task queued",
        )
        await self._report(result)

        # ── Phase 1: Cold-start + network retry loop ──────────────
        cold_attempt = 0
        net_attempt = 0
        payload_copy: Optional[dict[str, Any]] = request.payload.copy()
        last_error: Optional[str] = None
        event_url: Optional[str] = None

        while time.monotonic() < deadline:
            try:
                event_url = await self._do_submit(task_id, payload_copy)

                if event_url is not None:
                    # Submission succeeded -- move to polling phase
                    break

                # --- Branch A: Space returned None (cold-start / sleeping) ---
                cold_attempt += 1
                wait = self.retry_config.get_cold_start_delay(cold_attempt - 1)

                # Structured log for cold-start detection
                logger.info(
                    "[%(tid)s] Cold-start detected, Space sleeping. "
                    "Attempt %(attempt)d/%(max)d, next wait %(wait).0fs",
                    extra={"tid": task_id},
                )
                logger.info(
                    "task_id=%(tid)s event=cold_start attempt=%(attempt)d "
                    "max_attempts=%(max)d wait_seconds=%.0f",
                    {"tid": task_id, "attempt": cold_attempt,
                     "max": self.retry_config.max_cold_start_retries,
                     "wait": wait},
                )

                result = PredictResult(
                    task_id=task_id,
                    status=TaskStatus.LOADING,
                    progress=min(10 + cold_attempt * 12, 40),
                    message=(
                        f"Space cold-starting, "
                        f"retry {cold_attempt}/{self.retry_config.max_cold_start_retries}"
                    ),
                )
                await self._report(result)

                if cold_attempt >= self.retry_config.max_cold_start_retries:
                    failed = self._make_failed_result(
                        task_id=task_id,
                        error="Space failed to wake after maximum cold-start retries",
                        error_code="COLD_START_EXHAUSTED",
                        last_attempt=cold_attempt,
                        retryable=True,
                        cumulative_error=last_error,
                    )
                    await self._report(failed)
                    return failed

                await asyncio.sleep(wait)
                # Refresh session hash on each cold-start (Space may have restarted)
                self.refresh_session_if_needed()

            except httpx.ConnectError as exc:
                # Network-layer transient -- use short backoff with jitter
                net_attempt += 1
                if net_attempt > self.retry_config.max_network_retries:
                    failed = self._make_failed_result(
                        task_id=task_id,
                        error="Network failures exceeded maximum retry count",
                        error_code="NETWORK_RETRY_EXHAUSTED",
                        last_attempt=net_attempt,
                        retryable=True,
                        cumulative_error=f"ConnectError: {exc}",
                    )
                    await self._report(failed)
                    return failed
                wait = self.retry_config.get_network_delay(net_attempt - 1)
                jitter = self._add_jitter(wait)

                logger.info(
                    "task_id=%(tid)s event=network_retry attempt=%(attempt)d "
                    "error=%(error)s next_delay=%.1fs",
                    {
                        "tid": task_id,
                        "attempt": net_attempt,
                        "error": str(exc)[:120],
                        "delay": jitter,
                    },
                )

                result = PredictResult(
                    task_id=task_id,
                    status=TaskStatus.LOADING,
                    progress=min(10 + net_attempt * 8, 30),
                    message=f"Network transient, retrying ({net_attempt})",
                )
                await self._report(result)
                last_error = f"ConnectError: {exc}"
                await asyncio.sleep(jitter)

            except httpx.ReadTimeout as exc:
                # Could be cold-start or slow inference -- treat as transient
                net_attempt += 1
                if net_attempt > self.retry_config.max_network_retries:
                    failed = self._make_failed_result(
                        task_id=task_id,
                        error="Network failures exceeded maximum retry count",
                        error_code="NETWORK_RETRY_EXHAUSTED",
                        last_attempt=net_attempt,
                        retryable=True,
                        cumulative_error=f"ReadTimeout: {exc}",
                    )
                    await self._report(failed)
                    return failed
                wait = self.retry_config.get_network_delay(net_attempt - 1)
                jitter = self._add_jitter(wait)

                logger.info(
                    "task_id=%(tid)s event=read_timeout attempt=%(attempt)d "
                    "next_delay=%.1fs",
                    {"tid": task_id, "attempt": net_attempt, "delay": jitter},
                )

                last_error = f"ReadTimeout: {exc}"
                await asyncio.sleep(jitter)

            except httpx.HTTPStatusError as exc:
                category = _classify_http_error(exc)
                if category == ErrorCategory.PERMANENT:
                    logger.error(
                        "task_id=%(tid)s event=permanent_error status=%(status)d "
                        "error=%(error)s -- not retrying",
                        {
                            "tid": task_id,
                            "status": exc.response.status_code,
                            "error": str(exc)[:200],
                        },
                    )
                    failed = PredictResult(
                        task_id=task_id,
                        status=TaskStatus.FAILED,
                        progress=0,
                        error=str(exc)[:300],
                        error_code="PERMANENT_ERROR",
                        retryable=False,
                        updated_at=time.time(),
                    )
                    await self._report(failed)
                    return failed
                # 5xx -- transient, retry with backoff
                net_attempt += 1
                if net_attempt > self.retry_config.max_network_retries:
                    failed = self._make_failed_result(
                        task_id=task_id,
                        error="HTTP 5xx errors exceeded maximum retry count",
                        error_code="HTTP_5XX_EXHAUSTED",
                        last_attempt=net_attempt,
                        retryable=True,
                        cumulative_error=f"HTTP {exc.response.status_code}: {exc}",
                    )
                    await self._report(failed)
                    return failed
                wait = self.retry_config.get_network_delay(net_attempt - 1)
                jitter = self._add_jitter(wait)
                logger.warning(
                    "task_id=%(tid)s event=http_5xx attempt=%(attempt)d "
                    "status=%(status)s next_delay=%.1fs",
                    {
                        "tid": task_id,
                        "attempt": net_attempt,
                        "status": exc.response.status_code,
                        "delay": jitter,
                    },
                )
                last_error = f"HTTP {exc.response.status_code}: {exc}"
                await asyncio.sleep(jitter)

            except Exception as exc:
                # Unknown error -- classify and decide
                category = _classify_http_error(exc)
                if category == ErrorCategory.PERMANENT:
                    logger.error(
                        "task_id=%(tid)s event=permanent_error "
                        "error=%(error)s -- not retrying",
                        {"tid": task_id, "error": str(exc)[:300]},
                    )
                    failed = PredictResult(
                        task_id=task_id,
                        status=TaskStatus.FAILED,
                        progress=0,
                        error=str(exc)[:300],
                        error_code="PERMANENT_ERROR",
                        retryable=False,
                        updated_at=time.time(),
                    )
                    await self._report(failed)
                    return failed

                # Transient / infrastructure -- retry
                net_attempt += 1
                if net_attempt > self.retry_config.max_network_retries:
                    failed = self._make_failed_result(
                        task_id=task_id,
                        error="Transient errors exceeded maximum retry count",
                        error_code="TRANSIENT_RETRY_EXHAUSTED",
                        last_attempt=net_attempt,
                        retryable=True,
                        cumulative_error=str(exc)[:300],
                    )
                    await self._report(failed)
                    return failed
                wait = self.retry_config.get_network_delay(net_attempt - 1)
                jitter = self._add_jitter(wait)
                logger.exception(
                    "task_id=%(tid)s event=unknown_transient attempt=%(attempt)d "
                    "error=%(error)s next_delay=%.1fs",
                    {
                        "tid": task_id,
                        "attempt": net_attempt,
                        "error": str(exc)[:200],
                        "delay": jitter,
                    },
                )
                last_error = str(exc)[:300]
                await asyncio.sleep(jitter)

        # ── Phase 2: Event-stream polling ─────────────────────────
        if event_url is None:
            # All retries exhausted without ever getting an event_url
            failed = self._make_failed_result(
                task_id=task_id,
                error="Submission failed after all retry attempts",
                error_code="SUBMIT_EXHAUSTED",
                last_attempt=max(cold_attempt, net_attempt),
                retryable=True,
                cumulative_error=last_error,
            )
            await self._report(failed)
            return failed

        result = PredictResult(
            task_id=task_id,
            status=TaskStatus.RUNNING,
            progress=50,
            message="Inference running...",
        )
        await self._report(result)

        remaining = max(deadline - time.monotonic(), 30)  # floor at 30s
        final = await self._poll_events(
            event_url,
            task_id,
            remaining=remaining,
        )

        # Report the final result so broadcast captures COMPLETED/FAILED
        await self._report(final)
        return final

    # ------------------------------------------------------------------
    # Failure-result factory -- centralises FAILED envelope
    # ------------------------------------------------------------------

    def _make_failed_result(
        self,
        *,
        task_id: str,
        error: str,
        error_code: str = "RETRY_EXHAUSTED",
        last_attempt: int = 0,
        retryable: bool = True,
        cumulative_error: Optional[str] = None,
    ) -> PredictResult:
        """
        Build a standardised failed PredictResult after all retries exhausted.

        This ensures the caller always receives a valid PredictResult instead
        of an unhandled exception.
        """
        msg_parts = [error]
        if cumulative_error:
            msg_parts.append(f"(last error: {cumulative_error})")
        return PredictResult(
            task_id=task_id,
            status=TaskStatus.FAILED,
            progress=0,
            error="; ".join(msg_parts),
            error_code=error_code,
            retryable=retryable,
            last_attempt=last_attempt,
            updated_at=time.time(),
        )

    async def cancel(self, task_id: str) -> PredictResult:
        result = PredictResult(
            task_id=task_id,
            status=TaskStatus.CANCELLED,
            progress=0,
            message="Task cancelled by user",
        )
        await self._report(result)
        return result

    # ------------------------------------------------------------------
    # Session management hook
    # ------------------------------------------------------------------

    def refresh_session_if_needed(self) -> None:
        """
        Hook for subclasses to refresh their session state on cold-start.

        Default no-op; ``GradioSpaceMixin`` overrides this to regenerate
        the session hash.
        """
        pass

    # ------------------------------------------------------------------
    # Abstract methods -- subclasses MUST implement these
    # ------------------------------------------------------------------

    @abstractmethod
    def _build_payload(self, **kwargs) -> dict[str, Any]:
        """
        Build the service-specific prediction payload.

        Example::

            def _build_payload(self, prompt: str, **kwargs):
                return {"data": [prompt]}
        """
        ...

    @abstractmethod
    async def _do_submit(
        self,
        task_id: str,
        payload: dict[str, Any],
    ) -> Optional[str]:
        """
        Submit payload to the remote inference endpoint.

        Returns:
            The event-stream URL for polling, or None if the Space is
            still cold-starting.
        """
        ...

    @abstractmethod
    def _parse_response(self, event_data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """
        Parse a single event from the inference Space's event stream.

        Return None if the event is not terminal.  On terminal event,
        return a dict with at least a "url" key (download URL for the
        generated media file).
        """
        ...

    # ------------------------------------------------------------------
    # Internal helpers -- event polling
    # ------------------------------------------------------------------

    async def _poll_events(
        self,
        event_url: str,
        task_id: str,
        *,
        remaining: float,
        poll_interval: float = 5.0,
    ) -> PredictResult:
        """
        Poll the HF Space event stream until completion or timeout.

        Implements jitter-aware exponential backoff for transient network
        failures during polling.

        Progress extraction:
          - Parses ``process_generating`` events for real progress data
            (via ``_extract_progress`` — overridable by subclasses).
          - Falls back to poll-count heuristic when no progress data is
            available in the event stream.
          - Broadcasts RUNNING progress updates to WebSocket clients on
            each poll cycle so the frontend receives near-real-time updates.
        """
        deadline = time.monotonic() + remaining
        poll_count = 0
        net_failures = 0  # consecutive network failures
        last_reported_progress = 0  # avoid spamming same progress value

        while time.monotonic() < deadline:
            poll_count += 1

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(event_url)

                # Reset failure counter on success
                net_failures = 0

                if resp.status_code == 200:
                    data = resp.json() if resp.text else {}
                    events = data.get("events", []) if isinstance(data, dict) else []

                    for event in events:
                        event_type = event.get("type", "")
                        event_data = event.get("data", {})

                        # Terminal: completion
                        if event_type == "process_completed":
                            output = self._parse_response(event)
                            if output is not None:
                                return PredictResult(
                                    task_id=task_id,
                                    status=TaskStatus.COMPLETED,
                                    progress=100,
                                    message="Done!",
                                    result_url=output.get("url") or output.get("value"),
                                    metadata=output,
                                    updated_at=time.time(),
                                )

                        # Intermediate: extract real progress
                        if event_type == "process_generating":
                            real_progress = self._extract_progress(event_data)
                            if real_progress > 0 and real_progress != last_reported_progress:
                                last_reported_progress = real_progress
                                progress_result = PredictResult(
                                    task_id=task_id,
                                    status=TaskStatus.RUNNING,
                                    progress=real_progress,
                                    message=f"Inference in progress... ({real_progress}%)",
                                    updated_at=time.time(),
                                )
                                await self._report(progress_result)

                        # Failure event
                        if event_type == "process_failed":
                            error_msg = str(event_data) if event_data else "Unknown failure"
                            return PredictResult(
                                task_id=task_id,
                                status=TaskStatus.FAILED,
                                progress=0,
                                error=error_msg[:200],
                                error_code="GENERATION_FAILED",
                                retryable=True,
                                updated_at=time.time(),
                            )

                    # Heuristic fallback when no progress in events
                    estimated = min(poll_count * 3, 90)
                    if estimated != last_reported_progress:
                        last_reported_progress = estimated
                        progress_result = PredictResult(
                            task_id=task_id,
                            status=TaskStatus.RUNNING,
                            progress=estimated,
                            message="Inference in progress...",
                            updated_at=time.time(),
                        )
                        await self._report(progress_result)

                    # Return the latest progress so the caller sees RUNNING
                    return PredictResult(
                        task_id=task_id,
                        status=TaskStatus.RUNNING,
                        progress=last_reported_progress,
                        message="Inference in progress...",
                        updated_at=time.time(),
                    )

                # Non-200 during poll -- treat as transient if 5xx
                if resp.status_code >= 500:
                    net_failures += 1
                    logger.debug(
                        "Poll HTTP %d (attempt %d, %d consecutive failures)",
                        resp.status_code, poll_count, net_failures,
                    )
                    wait = self.retry_config.get_network_delay(net_failures - 1)
                    await asyncio.sleep(wait)
                    continue

                # Other non-200 -- possibly permanent
                logger.warning("Poll unexpected status %d", resp.status_code)
                return PredictResult(
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    progress=0,
                    error=f"Poll received HTTP {resp.status_code}",
                    error_code="POLL_HTTP_ERROR",
                    retryable=False,
                    updated_at=time.time(),
                )

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
                # Transient network failure -- exponential backoff with jitter
                net_failures += 1
                jitter = self._add_jitter(
                    self.retry_config.get_network_delay(net_failures - 1),
                )
                logger.debug(
                    "Poll network error (failure #%d): %s (wait %.1fs)",
                    net_failures, exc, jitter,
                )
                await asyncio.sleep(jitter)
                continue

            except Exception as exc:
                logger.warning("Poll unexpected error: %s", exc)
                await asyncio.sleep(poll_interval)
                continue

            # Normal iteration -- wait before next poll
            await asyncio.sleep(poll_interval)

        # Timed out
        return PredictResult(
            task_id=task_id,
            status=TaskStatus.FAILED,
            progress=0,
            error="Event polling timed out",
            error_code="POLL_TIMEOUT",
            retryable=True,
            last_attempt=poll_count,
            updated_at=time.time(),
        )

    # ------------------------------------------------------------------
    # Progress extraction — overridable by subclasses
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_progress(event_data: Any) -> int:
        """
        Heuristically extract progress percentage from generation event data.

        Subclasses can override to handle service-specific event shapes.
        Falls back to common field names (progress, percentage, step/total).
        """
        if not isinstance(event_data, dict):
            return 0

        # Direct progress/percentage fields
        for key in ("progress", "percentage", "current"):
            val = event_data.get(key)
            if isinstance(val, (int, float)):
                return min(int(val), 99)

        # Step/total ratio
        step = event_data.get("step", 0)
        total = event_data.get("total", 0)
        if isinstance(step, int) and isinstance(total, int) and total > 0:
            return min(int((step / total) * 100), 99)

        # Gradio-style: "data" may be a list where index 0 is progress
        data_list = event_data.get("data", [])
        if isinstance(data_list, list) and len(data_list) > 0:
            first = data_list[0]
            if isinstance(first, (int, float)):
                return min(int(first), 99)

        return 0

    @staticmethod
    def _add_jitter(delay: float, factor: float = 0.1) -> float:
        """Add random jitter to a delay to prevent thundering herd."""
        jitter = random.uniform(0, delay * factor)
        return delay + jitter

    # ------------------------------------------------------------------
    # Progress reporting
    # ------------------------------------------------------------------

    async def _report(self, result: PredictResult) -> None:
        """Push progress/result to the frontend via the injected callback."""
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

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self) -> tuple[bool, str]:
        """Check whether the inference Space is reachable.

        Tries two strategies:
          1. `*.hf.space` subdomain health endpoint
          2. Direct HEAD request to the original `space_url`
        Falls back to True if either succeeds.
        """
        # Mock mode: skip remote probe, always report healthy
        try:
            import os as _os2
            if (_os2.getenv("TTS_FORCE_MOCK") or "").strip() or (_os2.getenv("MUSIC_FORCE_MOCK") or "").strip() or (_os2.getenv("VIDEO_FORCE_MOCK") or "").strip():
                return True, "Mock service ready (FORCE_MOCK)"
        except Exception:
            pass
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Strategy 1: *.hf.space subdomain
                resp = await client.get(
                    f"{self.api_base}/health",
                    headers=self._auth_header(),
                )
                if resp.status_code == 200:
                    return True, "Space is healthy (via *.hf.space)"
                elif resp.status_code == 503:
                    # Sleeping — still reachable, just cold
                    return True, "Space is sleeping (cold-start required)"

                # Strategy 2: direct HEAD to original space_url
                resp2 = await client.head(
                    self.space_url,
                    headers=self._auth_header(),
                )
                if resp2.status_code == 200:
                    return True, "Space is healthy (direct)"
                elif resp2.status_code == 401:
                    return False, "Space requires authentication (401)"
                return False, f"Unreachable: subdomain={resp.status_code}, direct={resp2.status_code}"
        except httpx.ConnectError:
            return False, "Cannot connect to Space"
        except Exception as exc:
            return False, str(exc)[:100]
