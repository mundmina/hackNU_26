from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class Settings:
    app_name: str = "Locomotive Digital Twin API"
    api_prefix: str = ""
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173"])
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            f"sqlite:///{Path(__file__).resolve().parents[2] / 'data' / 'digital_twin.db'}",
        )
    )
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://redis:6379/0"))
    jwt_secret: str = field(default_factory=lambda: os.getenv("JWT_SECRET", "change-me-in-production"))
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = field(default_factory=lambda: int(os.getenv("ACCESS_TOKEN_MINUTES", "720")))
    stale_after_seconds: int = field(default_factory=lambda: int(os.getenv("STALE_AFTER_SECONDS", "10")))
    max_stream_queue: int = field(default_factory=lambda: int(os.getenv("MAX_STREAM_QUEUE", "128")))
    telemetry_buffer_size: int = field(default_factory=lambda: int(os.getenv("TELEMETRY_BUFFER_SIZE", "2048")))
    demo_users: dict[str, dict[str, str]] = field(
        default_factory=lambda: json.loads(
            os.getenv(
                "APP_USERS_JSON",
                json.dumps(
                    {
                        "operator": {"password": "demo123", "role": "operator"},
                        "admin": {"password": "admin123", "role": "admin"},
                    }
                ),
            )
        )
    )


settings = Settings()
