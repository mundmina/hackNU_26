from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import build_api_router
from app.core.settings import settings


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_router = build_api_router()
    app.include_router(api_router, prefix=settings.api_prefix)

    # Expose health and metrics at root level too (standard ops convention)
    @app.get("/health", include_in_schema=False)
    def root_health():
        from app.api.routes import container
        return container.database.ping()

    return app


app = create_app()
