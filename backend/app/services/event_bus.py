from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from app.core.metrics import MetricsRegistry
from app.core.settings import settings

log = logging.getLogger(__name__)

# Optional Redis — imported at runtime so the app starts without it installed.
try:
    import redis.asyncio as aioredis  # type: ignore[import]
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False

_REDIS_CHANNEL = "telemetry_events"


class EventBus:
    """
    Dual-mode event bus: Redis pub/sub (plan §5.3 highload buffer) with
    automatic in-memory fallback if Redis is unreachable or not installed.

    Redis mode:  publish() → Redis PUBLISH → background reader → local asyncio.Queue per subscriber.
    Memory mode: publish() → local asyncio.Queue per subscriber (original behaviour).

    The x10 spike absorption described in §5.3 is provided by Redis buffering bursts
    before they reach individual subscriber queues.
    """

    def __init__(self, metrics: MetricsRegistry) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._metrics = metrics
        self._last_payload: dict[str, Any] | None = None
        self._ws_clients = 0
        self._sse_clients = 0

        # Redis state — resolved lazily on first publish/subscribe
        self._redis_client: Any | None = None          # aioredis.Redis
        self._redis_reader_task: asyncio.Task[None] | None = None
        self._use_redis: bool = False
        self._redis_init_done: bool = False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def last_payload(self) -> dict[str, Any] | None:
        return self._last_payload

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    @asynccontextmanager
    async def subscribe(self, channel: str = "ws") -> AsyncGenerator[asyncio.Queue[dict[str, Any]], None]:
        await self._ensure_redis()
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
        await self._ensure_redis()

        if self._use_redis and self._redis_client is not None:
            try:
                await self._redis_client.publish(_REDIS_CHANNEL, json.dumps(payload))
                return  # Redis reader task will fan out to local queues
            except Exception as exc:  # pragma: no cover
                log.warning("Redis publish failed (%s); falling back to in-memory fan-out.", exc)
                self._use_redis = False

        # In-memory fan-out (fallback or no-Redis path)
        self._fan_out(payload)

    # ------------------------------------------------------------------
    # Redis lifecycle helpers
    # ------------------------------------------------------------------

    async def _ensure_redis(self) -> None:
        """Lazily connect to Redis once; sets self._use_redis flag."""
        if self._redis_init_done:
            return
        self._redis_init_done = True

        if not _REDIS_AVAILABLE:
            log.info("redis.asyncio not installed — running in-memory event bus.")
            return

        try:
            client = aioredis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
            )
            await client.ping()
            self._redis_client = client
            self._use_redis = True
            # Start background reader that fans out Redis messages to local queues
            self._redis_reader_task = asyncio.create_task(
                self._redis_reader_loop(), name="redis_reader"
            )
            log.info("Redis connected at %s — using Redis pub/sub event bus.", settings.redis_url)
        except Exception as exc:
            log.info("Redis not reachable (%s) — using in-memory event bus.", exc)
            self._use_redis = False

    async def _redis_reader_loop(self) -> None:
        """
        Subscribe to the Redis channel and fan out to all local asyncio queues.
        Reconnects automatically if the connection drops (§5.4 fault tolerance).
        """
        backoff = 1
        while True:
            try:
                pubsub = self._redis_client.pubsub()  # type: ignore[union-attr]
                await pubsub.subscribe(_REDIS_CHANNEL)
                log.debug("Redis reader subscribed to '%s'.", _REDIS_CHANNEL)
                backoff = 1
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            payload = json.loads(message["data"])
                            self._fan_out(payload)
                        except Exception:  # pragma: no cover
                            pass
            except asyncio.CancelledError:
                return
            except Exception as exc:
                log.warning("Redis reader error (%s); reconnecting in %ds.", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    # ------------------------------------------------------------------
    # Internal fan-out (used by both paths)
    # ------------------------------------------------------------------

    def _fan_out(self, payload: dict[str, Any]) -> None:
        """Push payload to all local subscriber queues; drop oldest frame if full (§5.3 backpressure)."""
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
