from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from app.core.metrics import MetricsRegistry
from app.core.settings import settings


class EventBus:
    def __init__(self, metrics: MetricsRegistry) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._metrics = metrics
        self._last_payload: dict[str, Any] | None = None
        self._ws_clients = 0
        self._sse_clients = 0

    @property
    def last_payload(self) -> dict[str, Any] | None:
        return self._last_payload

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    @asynccontextmanager
    async def subscribe(self, channel: str = "ws") -> AsyncGenerator[asyncio.Queue[dict[str, Any]], None]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=settings.max_stream_queue)
        self._subscribers.add(queue)
        if channel == "ws":
            self._ws_clients += 1
            self._metrics.set_value("ws_clients", self._ws_clients)
        else:
            self._sse_clients += 1
            self._metrics.set_value("sse_clients", self._sse_clients)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)
            if channel == "ws":
                self._ws_clients = max(0, self._ws_clients - 1)
                self._metrics.set_value("ws_clients", self._ws_clients)
            else:
                self._sse_clients = max(0, self._sse_clients - 1)
                self._metrics.set_value("sse_clients", self._sse_clients)

    async def publish(self, payload: dict[str, Any]) -> None:
        self._last_payload = payload
        for queue in list(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                self._metrics.increment("buffer_drops")
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                self._metrics.increment("buffer_drops")
