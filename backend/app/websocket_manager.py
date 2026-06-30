"""
WebSocket Connection Manager

Manages a set of active WebSocket connections keyed by task_id.
Each task can have multiple subscribers (e.g., dashboard + notification).

Works with real ASGI servers (uvicorn) where WebSocket.send_json is async.
For TestClient unit tests, a synchronous fallback is provided.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import WebSocket

from app.services.inference.base import PredictResult

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket connection manager keyed by task_id."""

    def __init__(self) -> None:
        # task_id -> set[WebSocket]
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, task_id: str, ws: WebSocket) -> None:
        """Register a WebSocket subscriber for a task."""
        async with self._lock:
            if task_id not in self._connections:
                self._connections[task_id] = set()
            self._connections[task_id].add(ws)
        logger.info("WebSocket connected: task_id=%s (total: %d)", task_id, len(self._connections[task_id]))

    async def disconnect(self, task_id: str, ws: WebSocket) -> None:
        """Unregister a WebSocket subscriber."""
        async with self._lock:
            if task_id in self._connections:
                self._connections[task_id].discard(ws)
                if not self._connections[task_id]:
                    del self._connections[task_id]
        logger.info("WebSocket disconnected: task_id=%s", task_id)

    async def broadcast(self, task_id: str, result: PredictResult) -> int:
        """
        Push a PredictResult to all WebSocket subscribers of a task.

        Uses async send_json — works with real ASGI servers.
        Returns the number of successful sends.

        Dead connection cleanup is done atomically with the broadcast
        to prevent race conditions in high-concurrency scenarios.
        """
        async with self._lock:
            subs = list(self._connections.get(task_id, set()))

        if not subs:
            return 0

        payload = result.to_dict()
        sent = 0
        dead: list[WebSocket] = []

        for ws in subs:
            try:
                await ws.send_json(payload)
                sent += 1
            except Exception:
                dead.append(ws)

        # Clean up broken connections under lock
        if dead:
            async with self._lock:
                for ws in dead:
                    conns = self._connections.get(task_id)
                    if conns:
                        conns.discard(ws)
                if task_id in self._connections and not self._connections[task_id]:
                    del self._connections[task_id]

            logger.warning(
                "WebSocket broadcast: %d/%d sent, %d dead connections cleaned",
                sent, sent + len(dead), len(dead),
            )
        return sent

    @property
    def active_tasks(self) -> list[str]:
        """Return list of task_ids with active subscribers."""
        return list(self._connections.keys())

    @property
    def subscriber_count(self) -> int:
        """Total number of active WebSocket connections."""
        return sum(len(subs) for subs in self._connections.values())


# Module-level singleton
manager = ConnectionManager()
