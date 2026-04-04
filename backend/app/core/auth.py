from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

from app.core.settings import settings


def create_access_token(username: str, role: str) -> str:
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_minutes)
    payload = {"sub": username, "role": role, "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, str]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
