from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.auth import create_access_token, decode_token
from app.core.metrics import MetricsRegistry
from app.core.settings import settings
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.health import HealthSnapshot
from app.schemas.telemetry import EnrichedTelemetry, FleetCard, TelemetryEvent
from app.services.alerts import AlertEngine
from app.services.event_bus import EventBus
from app.services.health_engine import HealthIndexEngine
from app.storage.database import Database


security = HTTPBearer(auto_error=False)


class AppContainer:
    def __init__(self) -> None:
        self.metrics = MetricsRegistry()
        self.database = Database(settings.database_url)
        self.bus = EventBus(self.metrics)
        self.health_engine = HealthIndexEngine()
        self.alert_engine = AlertEngine()


container = AppContainer()
router = APIRouter()


def _to_public_event(item: EnrichedTelemetry) -> dict[str, Any]:
    return item.model_dump(mode="json")


def require_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)]) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    try:
        return decode_token(credentials.credentials)
    except Exception as exc:  # pragma: no cover - auth library detail
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    user = settings.demo_users.get(payload.username)
    if not user or user["password"] != payload.password:
        container.metrics.increment("auth_failures")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(payload.username, user["role"])
    container.metrics.increment("auth_success")
    return TokenResponse(access_token=token, role=user["role"])


@router.get("/health")
def healthcheck() -> dict[str, Any]:
    db_ok = container.database.ping()
    stale = container.bus.last_payload is None
    last_timestamp = None
    if container.bus.last_payload:
        last_timestamp = container.bus.last_payload["telemetry"]["timestamp"]
        event_time = datetime.fromisoformat(last_timestamp.replace("Z", "+00:00"))
        stale = (datetime.now(UTC) - event_time).total_seconds() > settings.stale_after_seconds
    return {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "streaming": {"stale": stale, "last_event_timestamp": last_timestamp},
        "queue_depth": 0,
    }


@router.get("/metrics")
def metrics() -> PlainTextResponse:
    body = container.metrics.to_prometheus(queue_depth=0, db_ok=container.database.ping())
    return PlainTextResponse(body, media_type="text/plain; version=0.0.4")


@router.post("/telemetry", response_model=EnrichedTelemetry)
async def ingest_telemetry(payload: TelemetryEvent, _: Annotated[dict[str, Any], Depends(require_user)]) -> EnrichedTelemetry:
    previous = container.database.latest_health(payload.locomotive_id)
    if previous:
        payload.metadata["delta_hours"] = max(
            1 / 3600,
            (payload.timestamp.astimezone(UTC) - previous.timestamp.astimezone(UTC)).total_seconds() / 3600,
        )
    health = container.health_engine.evaluate(payload, previous_health=previous.score if previous else None)
    health.trend = container.database.trend(payload.locomotive_id, points=60) + [health.score]
    alerts = container.alert_engine.evaluate(payload, health)
    event_id = str(uuid4())

    container.database.upsert_locomotive(payload)
    container.database.save_event(event_id, payload, health, alerts)
    container.metrics.increment("total_ingested")
    if alerts:
        container.metrics.increment("total_alerts", len(alerts))

    event = EnrichedTelemetry(
        event_id=event_id,
        telemetry=payload,
        health=health.model_dump(mode="json"),
        alerts=[alert.model_dump(mode="json") for alert in alerts],
    )
    await container.bus.publish(_to_public_event(event))
    return event


@router.get("/locomotives", response_model=list[FleetCard])
def list_locomotives(_: Annotated[dict[str, Any], Depends(require_user)]) -> list[FleetCard]:
    return container.database.fleet_overview()


@router.get("/locomotives/{locomotive_id}/health", response_model=HealthSnapshot)
def locomotive_health(locomotive_id: str, _: Annotated[dict[str, Any], Depends(require_user)]) -> HealthSnapshot:
    health = container.database.latest_health(locomotive_id)
    if health is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Locomotive not found")
    health.trend = container.database.trend(locomotive_id, points=120)
    return health


@router.get("/telemetry", response_model=list[EnrichedTelemetry])
def telemetry_history(
    _: Annotated[dict[str, Any], Depends(require_user)],
    locomotive_id: str | None = None,
    from_ts: Annotated[datetime | None, Query(alias="from")] = None,
    to_ts: Annotated[datetime | None, Query(alias="to")] = None,
    page: int = 1,
    page_size: int = 100,
) -> list[EnrichedTelemetry]:
    return container.database.history(
        locomotive_id=locomotive_id,
        from_ts=from_ts,
        to_ts=to_ts,
        page=page,
        page_size=min(page_size, 500),
    )


@router.get("/alerts")
def list_alerts(
    _: Annotated[dict[str, Any], Depends(require_user)],
    locomotive_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    return [alert.model_dump(mode="json") for alert in container.database.alerts(locomotive_id=locomotive_id, limit=limit)]


@router.get("/export")
def export_history(
    _: Annotated[dict[str, Any], Depends(require_user)],
    format_name: Annotated[Literal["csv", "json"], Query(alias="format")] = "csv",
    locomotive_id: str | None = None,
    from_ts: Annotated[datetime | None, Query(alias="from")] = None,
    to_ts: Annotated[datetime | None, Query(alias="to")] = None,
) -> PlainTextResponse:
    body = container.database.export_history(format_name, locomotive_id, from_ts, to_ts)
    media_type = "application/json" if format_name == "json" else "text/csv"
    return PlainTextResponse(body, media_type=media_type)


async def sse_stream(request: Request) -> AsyncGenerator[bytes, None]:
    async with container.bus.subscribe(channel="sse") as queue:
        if container.bus.last_payload:
            yield f"data: {json.dumps(container.bus.last_payload)}\n\n".encode()
        while True:
            if await request.is_disconnected():
                break
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=10)
                yield f"data: {json.dumps(payload)}\n\n".encode()
            except TimeoutError:
                yield b": keepalive\n\n"


@router.get("/stream")
async def stream(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    token: str | None = None,
) -> StreamingResponse:
    if token:
        raw_token = token
    elif authorization:
        raw_token = authorization.replace("Bearer ", "", 1)
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    try:
        decode_token(raw_token)
    except Exception as exc:  # pragma: no cover - auth library detail
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc
    return StreamingResponse(sse_stream(request), media_type="text/event-stream")


@router.websocket("/ws")
async def websocket_stream(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)
        return
    try:
        decode_token(token)
    except Exception:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    async with container.bus.subscribe(channel="ws") as queue:
        if container.bus.last_payload:
            await websocket.send_json(container.bus.last_payload)
        try:
            while True:
                payload = await queue.get()
                await websocket.send_json(payload)
        except WebSocketDisconnect:
            return


def build_api_router() -> APIRouter:
    return router
