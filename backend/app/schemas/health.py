from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class HealthFactor(BaseModel):
    key: str
    label: str
    category: str
    penalty: float
    detail: str


class HealthSnapshot(BaseModel):
    locomotive_id: str
    timestamp: datetime
    score: float
    grade: str
    band: str
    load_modifier: float
    health_modifier: float
    reliability_modifier: float
    formula_score: float
    trend: list[float] = Field(default_factory=list)
    factors: list[HealthFactor] = Field(default_factory=list)
