from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import build_api_router, runtime_dependencies
from app.core.settings import settings
from app.services.telemetry_runtime import DemoTelemetryAutopilot


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        autopilot = None
        if settings.enable_demo_autopilot:
            autopilot = DemoTelemetryAutopilot(runtime_dependencies, cadence_seconds=settings.autopilot_interval_seconds)
            await autopilot.start()
            app.state.autopilot = autopilot
        try:
            yield
        finally:
            if autopilot is not None:
                await autopilot.stop()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(build_api_router(), prefix=settings.api_prefix)
    return app


app = create_app()
