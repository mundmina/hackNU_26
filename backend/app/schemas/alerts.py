from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Alert(BaseModel):
    alert_id: str
    locomotive_id: str
    timestamp: datetime
    severity: str
    code: str
    message: str
    status: str = "open"
    source: str
    details: dict[str, Any] = Field(default_factory=dict)
