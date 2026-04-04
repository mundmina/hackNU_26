from __future__ import annotations

import csv
import io
import json
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from app.schemas.alerts import Alert
from app.schemas.health import HealthSnapshot
from app.schemas.telemetry import EnrichedTelemetry, FleetCard, TelemetryEvent


class Database:
    def __init__(self, database_url: str) -> None:
        raw_path = database_url.replace("sqlite:///", "", 1)
        self._path = Path(raw_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS locomotives (
                    locomotive_id TEXT PRIMARY KEY,
                    locomotive_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS telemetry_events (
                    event_id TEXT PRIMARY KEY,
                    locomotive_id TEXT NOT NULL,
                    locomotive_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    health_score REAL NOT NULL,
                    health_grade TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    health_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_telemetry_locomotive_time
                    ON telemetry_events (locomotive_id, timestamp DESC);

                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id TEXT PRIMARY KEY,
                    locomotive_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    code TEXT NOT NULL,
                    message TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    details_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_alerts_locomotive_time
                    ON alerts (locomotive_id, timestamp DESC);
                """
            )

    def ping(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1")
            return True
        except sqlite3.Error:
            return False

    def upsert_locomotive(self, telemetry: TelemetryEvent) -> None:
        now = telemetry.timestamp.astimezone(UTC).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO locomotives (locomotive_id, locomotive_type, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(locomotive_id)
                DO UPDATE SET locomotive_type=excluded.locomotive_type, updated_at=excluded.updated_at
                """,
                (telemetry.locomotive_id, telemetry.locomotive_type, now, now),
            )

    def save_event(self, event_id: str, telemetry: TelemetryEvent, health: HealthSnapshot, alerts: list[Alert]) -> None:
        payload_json = telemetry.model_dump_json()
        health_json = health.model_dump_json()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO telemetry_events (
                    event_id, locomotive_id, locomotive_type, timestamp, health_score, health_grade, payload_json, health_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    telemetry.locomotive_id,
                    telemetry.locomotive_type,
                    telemetry.timestamp.astimezone(UTC).isoformat(),
                    health.score,
                    health.grade,
                    payload_json,
                    health_json,
                ),
            )
            for alert in alerts:
                connection.execute(
                    """
                    INSERT INTO alerts (
                        alert_id, locomotive_id, timestamp, severity, code, message, status, source, details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        alert.alert_id,
                        alert.locomotive_id,
                        alert.timestamp.astimezone(UTC).isoformat(),
                        alert.severity,
                        alert.code,
                        alert.message,
                        alert.status,
                        alert.source,
                        json.dumps(alert.details),
                    ),
                )

    def latest_health(self, locomotive_id: str) -> HealthSnapshot | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT health_json
                FROM telemetry_events
                WHERE locomotive_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (locomotive_id,),
            ).fetchone()
        if not row:
            return None
        return HealthSnapshot.model_validate_json(row["health_json"])

    def history(
        self,
        locomotive_id: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> list[EnrichedTelemetry]:
        clauses = ["1=1"]
        params: list[Any] = []
        if locomotive_id:
            clauses.append("locomotive_id = ?")
            params.append(locomotive_id)
        if from_ts:
            clauses.append("timestamp >= ?")
            params.append(from_ts.astimezone(UTC).isoformat())
        if to_ts:
            clauses.append("timestamp <= ?")
            params.append(to_ts.astimezone(UTC).isoformat())
        params.extend([page_size, max(0, (page - 1) * page_size)])

        query = f"""
            SELECT event_id, payload_json, health_json
            FROM telemetry_events
            WHERE {' AND '.join(clauses)}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()

        results: list[EnrichedTelemetry] = []
        for row in rows:
            event_id = row["event_id"]
            telemetry = TelemetryEvent.model_validate_json(row["payload_json"])
            health = HealthSnapshot.model_validate_json(row["health_json"])
            alerts = self.alerts(locomotive_id=telemetry.locomotive_id, limit=20, event_time=telemetry.timestamp)
            results.append(
                EnrichedTelemetry(
                    event_id=event_id,
                    telemetry=telemetry,
                    health=health.model_dump(mode="json"),
                    alerts=[alert.model_dump(mode="json") for alert in alerts],
                )
            )
        return results

    def alerts(
        self,
        locomotive_id: str | None = None,
        limit: int = 100,
        event_time: datetime | None = None,
    ) -> list[Alert]:
        clauses = ["1=1"]
        params: list[Any] = []
        if locomotive_id:
            clauses.append("locomotive_id = ?")
            params.append(locomotive_id)
        if event_time:
            clauses.append("timestamp <= ?")
            params.append(event_time.astimezone(UTC).isoformat())
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM alerts
                WHERE {' AND '.join(clauses)}
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [
            Alert(
                alert_id=row["alert_id"],
                locomotive_id=row["locomotive_id"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                severity=row["severity"],
                code=row["code"],
                message=row["message"],
                status=row["status"],
                source=row["source"],
                details=json.loads(row["details_json"]),
            )
            for row in rows
        ]

    def fleet_overview(self) -> list[FleetCard]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT te.event_id, te.locomotive_id, te.locomotive_type, te.timestamp, te.health_score, te.health_grade, te.payload_json
                FROM telemetry_events te
                INNER JOIN (
                    SELECT locomotive_id, MAX(timestamp) AS max_timestamp
                    FROM telemetry_events
                    GROUP BY locomotive_id
                ) latest
                    ON te.locomotive_id = latest.locomotive_id
                   AND te.timestamp = latest.max_timestamp
                ORDER BY te.locomotive_id
                """
            ).fetchall()
        alert_counts = defaultdict(int)
        for alert in self.alerts(limit=500):
            alert_counts[alert.locomotive_id] += 1

        cards: list[FleetCard] = []
        for row in rows:
            payload = TelemetryEvent.model_validate_json(row["payload_json"])
            cards.append(
                FleetCard(
                    locomotive_id=row["locomotive_id"],
                    locomotive_type=row["locomotive_type"],
                    last_seen=datetime.fromisoformat(row["timestamp"]),
                    health_score=row["health_score"],
                    health_grade=row["health_grade"],
                    alert_count=alert_counts[row["locomotive_id"]],
                    speed_kmh=payload.speed_kmh,
                    location=(payload.gps_lat, payload.gps_lon),
                )
            )
        return cards

    def trend(self, locomotive_id: str, points: int = 60) -> list[float]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT health_score
                FROM telemetry_events
                WHERE locomotive_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (locomotive_id, points),
            ).fetchall()
        return [row["health_score"] for row in reversed(rows)]

    def export_history(self, format_name: str, locomotive_id: str | None, from_ts: datetime | None, to_ts: datetime | None) -> str:
        items = self.history(locomotive_id=locomotive_id, from_ts=from_ts, to_ts=to_ts, page=1, page_size=5000)
        if format_name == "json":
            return json.dumps([item.model_dump(mode="json") for item in items], indent=2)

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "event_id",
                "locomotive_id",
                "timestamp",
                "locomotive_type",
                "health_score",
                "health_grade",
                "speed_kmh",
                "tractive_effort_kn",
                "wheel_slip_ratio_pct",
                "engine_oil_temperature_c",
                "coolant_temperature_c",
                "main_reservoir_pressure_mpa",
            ]
        )
        for item in items:
            telemetry = item.telemetry
            health = item.health
            writer.writerow(
                [
                    item.event_id,
                    telemetry.locomotive_id,
                    telemetry.timestamp.isoformat(),
                    telemetry.locomotive_type,
                    health["score"],
                    health["grade"],
                    telemetry.speed_kmh,
                    telemetry.tractive_effort_kn,
                    telemetry.wheel_slip_ratio_pct,
                    telemetry.engine_oil_temperature_c,
                    telemetry.coolant_temperature_c,
                    telemetry.main_reservoir_pressure_mpa,
                ]
            )
        return buffer.getvalue()
