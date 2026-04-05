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
from app.schemas.analytics import (
    AlertBreakdownRow,
    AlertTrendRow,
    BreakdownRow,
    FactorBreakdownRow,
    KpiRow,
    ReportingEventRow,
    TrendRow,
)
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

    def _query_event_snapshots(
        self,
        locomotive_id: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
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

        query = f"""
            SELECT event_id, locomotive_id, locomotive_type, timestamp, payload_json, health_json
            FROM telemetry_events
            WHERE {' AND '.join(clauses)}
            ORDER BY timestamp ASC
        """
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()

        event_alerts = self._event_alert_summary(locomotive_id=locomotive_id, from_ts=from_ts, to_ts=to_ts)
        snapshots: list[dict[str, Any]] = []
        for row in rows:
            telemetry = TelemetryEvent.model_validate_json(row["payload_json"])
            health = HealthSnapshot.model_validate_json(row["health_json"])
            alert_summary = event_alerts.get((row["locomotive_id"], row["timestamp"]), {"alerts": 0, "critical_alerts": 0})
            snapshots.append(
                {
                    "event_id": row["event_id"],
                    "timestamp": datetime.fromisoformat(row["timestamp"]),
                    "locomotive_id": row["locomotive_id"],
                    "locomotive_type": row["locomotive_type"],
                    "telemetry": telemetry,
                    "health": health,
                    "alerts": alert_summary["alerts"],
                    "critical_alerts": alert_summary["critical_alerts"],
                }
            )
        return snapshots

    def _event_alert_summary(
        self,
        locomotive_id: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
    ) -> dict[tuple[str, str], dict[str, int]]:
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

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT locomotive_id, timestamp, severity, COUNT(*) AS count
                FROM alerts
                WHERE {' AND '.join(clauses)}
                GROUP BY locomotive_id, timestamp, severity
                """,
                params,
            ).fetchall()

        summary: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"alerts": 0, "critical_alerts": 0})
        for row in rows:
            key = (row["locomotive_id"], row["timestamp"])
            summary[key]["alerts"] += row["count"]
            if row["severity"] == "critical":
                summary[key]["critical_alerts"] += row["count"]
        return summary

    def _filtered_alerts(
        self,
        locomotive_id: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
    ) -> list[Alert]:
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

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM alerts
                WHERE {' AND '.join(clauses)}
                ORDER BY timestamp ASC
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

    def _avg(self, values: list[float]) -> float:
        return round(sum(values) / len(values), 2) if values else 0.0

    def _bucket_timestamp(self, value: datetime, bucket: str) -> datetime:
        normalized = value.astimezone(UTC).replace(second=0, microsecond=0)
        if bucket == "15min":
            return normalized.replace(minute=(normalized.minute // 15) * 15)
        if bucket == "day":
            return normalized.replace(hour=0, minute=0)
        return normalized.replace(minute=0)

    def analytics_reporting_rows(
        self,
        locomotive_id: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
        limit: int = 5000,
    ) -> list[ReportingEventRow]:
        snapshots = self._query_event_snapshots(locomotive_id=locomotive_id, from_ts=from_ts, to_ts=to_ts, limit=limit)
        rows: list[ReportingEventRow] = []
        for item in snapshots:
            telemetry: TelemetryEvent = item["telemetry"]
            health: HealthSnapshot = item["health"]
            top_factor = health.factors[0] if health.factors else None
            rows.append(
                ReportingEventRow(
                    event_id=item["event_id"],
                    timestamp=item["timestamp"].isoformat(),
                    event_date=item["timestamp"].date().isoformat(),
                    locomotive_id=item["locomotive_id"],
                    locomotive_type=item["locomotive_type"],
                    health_score=round(health.score, 2),
                    health_grade=health.grade,
                    health_band=health.band,
                    speed_kmh=round(telemetry.speed_kmh, 2),
                    speed_limit_kmh=round(telemetry.speed_limit_kmh, 2),
                    speed_limit_utilization_pct=round(telemetry.speed_kmh / max(telemetry.speed_limit_kmh, 1) * 100, 2),
                    tractive_effort_kn=round(telemetry.tractive_effort_kn, 2),
                    wheel_slip_ratio_pct=round(telemetry.wheel_slip_ratio_pct, 2),
                    adhesion_coefficient=round(telemetry.adhesion_coefficient, 3),
                    battery_voltage_v=round(telemetry.battery_voltage_v, 2),
                    electric_power_kw=round(float(telemetry.electric_power_kw or 0), 2),
                    fuel_level_pct=round(float(telemetry.fuel_level_pct or 0), 2),
                    fuel_consumption_lph=round(float(telemetry.fuel_consumption_lph or 0), 2),
                    engine_oil_temperature_c=round(telemetry.engine_oil_temperature_c, 2),
                    coolant_temperature_c=round(telemetry.coolant_temperature_c, 2),
                    engine_oil_pressure_mpa=round(telemetry.engine_oil_pressure_mpa, 3),
                    exhaust_gas_temperature_c=round(telemetry.exhaust_gas_temperature_c, 2),
                    traction_motor_winding_temp_c=round(telemetry.traction_motor_winding_temp_c, 2),
                    vibration_amplitude_mms=round(telemetry.vibration_amplitude_mms, 2),
                    main_reservoir_pressure_mpa=round(telemetry.main_reservoir_pressure_mpa, 3),
                    brake_pad_wear_pct_remaining=round(telemetry.brake_pad_wear_pct_remaining, 2),
                    active_error_codes=telemetry.active_error_codes,
                    alert_count=item["alerts"],
                    critical_alert_count=item["critical_alerts"],
                    locomotive_availability_pct=round(telemetry.locomotive_availability_pct, 2),
                    mtbf_h=round(telemetry.mtbf_h, 2),
                    mttr_h=round(telemetry.mttr_h, 2),
                    distance_since_last_overhaul_km=round(telemetry.distance_since_last_overhaul_km, 2),
                    track_gradient_permille=round(telemetry.track_gradient_permille, 2),
                    rail_surface_state=telemetry.rail_surface_state,
                    top_factor_label=top_factor.label if top_factor else "Nominal",
                    top_factor_category=top_factor.category if top_factor else "none",
                    top_factor_penalty_points=round(top_factor.penalty, 2) if top_factor else 0.0,
                )
            )
        return rows

    def analytics_kpis(
        self,
        locomotive_id: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
    ) -> list[KpiRow]:
        rows = self.analytics_reporting_rows(locomotive_id=locomotive_id, from_ts=from_ts, to_ts=to_ts)
        if not rows:
            return []
        alerts = self._filtered_alerts(locomotive_id=locomotive_id, from_ts=from_ts, to_ts=to_ts)
        return [
            KpiRow(
                generated_at=datetime.now(UTC).isoformat(),
                scope_locomotive_id=locomotive_id or "ALL",
                events=len(rows),
                locomotives=len({row.locomotive_id for row in rows}),
                avg_health_score=self._avg([row.health_score for row in rows]),
                min_health_score=round(min(row.health_score for row in rows), 2),
                critical_event_rate_pct=round(
                    (sum(1 for row in rows if row.health_grade in {"D", "E"}) / len(rows)) * 100,
                    2,
                ),
                avg_speed_kmh=self._avg([row.speed_kmh for row in rows]),
                avg_speed_limit_utilization_pct=self._avg([row.speed_limit_utilization_pct for row in rows]),
                avg_alerts_per_event=self._avg([float(row.alert_count) for row in rows]),
                alert_events_pct=round((sum(1 for row in rows if row.alert_count > 0) / len(rows)) * 100, 2),
                alerts_total=len(alerts),
                critical_alerts_total=sum(1 for alert in alerts if alert.severity == "critical"),
                avg_availability_pct=self._avg([row.locomotive_availability_pct for row in rows]),
                avg_mtbf_h=self._avg([row.mtbf_h for row in rows]),
                avg_mttr_h=self._avg([row.mttr_h for row in rows]),
                avg_fuel_level_pct=self._avg([row.fuel_level_pct for row in rows if row.fuel_level_pct > 0]),
                avg_electric_power_kw=self._avg([row.electric_power_kw for row in rows if row.electric_power_kw > 0]),
                avg_wheel_slip_ratio_pct=self._avg([row.wheel_slip_ratio_pct for row in rows]),
                avg_vibration_mms=self._avg([row.vibration_amplitude_mms for row in rows]),
                avg_brake_pad_remaining_pct=self._avg([row.brake_pad_wear_pct_remaining for row in rows]),
                avg_reservoir_pressure_mpa=self._avg([row.main_reservoir_pressure_mpa for row in rows]),
            )
        ]

    def analytics_trends(
        self,
        bucket: str = "hour",
        locomotive_id: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
    ) -> list[TrendRow]:
        rows = self.analytics_reporting_rows(locomotive_id=locomotive_id, from_ts=from_ts, to_ts=to_ts)
        grouped: dict[datetime, list[ReportingEventRow]] = defaultdict(list)
        for row in rows:
            grouped[self._bucket_timestamp(datetime.fromisoformat(row.timestamp), bucket)].append(row)

        results: list[TrendRow] = []
        for bucket_start in sorted(grouped):
            items = grouped[bucket_start]
            results.append(
                TrendRow(
                    bucket_start=bucket_start.isoformat(),
                    scope_locomotive_id=locomotive_id or "ALL",
                    events=len(items),
                    avg_health_score=self._avg([item.health_score for item in items]),
                    min_health_score=round(min(item.health_score for item in items), 2),
                    critical_event_count=sum(1 for item in items if item.health_grade in {"D", "E"}),
                    avg_speed_kmh=self._avg([item.speed_kmh for item in items]),
                    max_speed_kmh=round(max(item.speed_kmh for item in items), 2),
                    avg_speed_limit_utilization_pct=self._avg([item.speed_limit_utilization_pct for item in items]),
                    avg_alerts_per_event=self._avg([float(item.alert_count) for item in items]),
                    avg_engine_oil_temperature_c=self._avg([item.engine_oil_temperature_c for item in items]),
                    avg_coolant_temperature_c=self._avg([item.coolant_temperature_c for item in items]),
                    avg_wheel_slip_ratio_pct=self._avg([item.wheel_slip_ratio_pct for item in items]),
                    avg_vibration_mms=self._avg([item.vibration_amplitude_mms for item in items]),
                    avg_reservoir_pressure_mpa=self._avg([item.main_reservoir_pressure_mpa for item in items]),
                    avg_availability_pct=self._avg([item.locomotive_availability_pct for item in items]),
                )
            )
        return results

    def analytics_breakdown(
        self,
        dimension: str = "health_grade",
        locomotive_id: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
    ) -> list[BreakdownRow]:
        rows = self.analytics_reporting_rows(locomotive_id=locomotive_id, from_ts=from_ts, to_ts=to_ts)
        supported_dimensions = {
            "health_grade",
            "health_band",
            "locomotive_type",
            "rail_surface_state",
            "top_factor_category",
            "top_factor_label",
        }
        if dimension not in supported_dimensions:
            raise ValueError(f"Unsupported breakdown dimension: {dimension}")

        grouped: dict[str, list[ReportingEventRow]] = defaultdict(list)
        for row in rows:
            grouped[str(getattr(row, dimension))].append(row)

        results: list[BreakdownRow] = []
        for dimension_value in sorted(grouped):
            items = grouped[dimension_value]
            results.append(
                BreakdownRow(
                    dimension_name=dimension,
                    dimension_value=dimension_value,
                    scope_locomotive_id=locomotive_id or "ALL",
                    events=len(items),
                    locomotives=len({item.locomotive_id for item in items}),
                    avg_health_score=self._avg([item.health_score for item in items]),
                    critical_event_rate_pct=round(
                        (sum(1 for item in items if item.health_grade in {"D", "E"}) / len(items)) * 100,
                        2,
                    ),
                    avg_alerts_per_event=self._avg([float(item.alert_count) for item in items]),
                    avg_speed_kmh=self._avg([item.speed_kmh for item in items]),
                    avg_wheel_slip_ratio_pct=self._avg([item.wheel_slip_ratio_pct for item in items]),
                    avg_vibration_mms=self._avg([item.vibration_amplitude_mms for item in items]),
                )
            )
        return results

    def analytics_factor_breakdown(
        self,
        locomotive_id: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
    ) -> list[FactorBreakdownRow]:
        snapshots = self._query_event_snapshots(locomotive_id=locomotive_id, from_ts=from_ts, to_ts=to_ts)
        grouped: dict[tuple[str, str], list[tuple[str, float]]] = defaultdict(list)
        for item in snapshots:
            health: HealthSnapshot = item["health"]
            for factor in health.factors:
                grouped[(factor.label, factor.category)].append((item["locomotive_id"], factor.penalty))

        results: list[FactorBreakdownRow] = []
        for (label, category), entries in sorted(grouped.items(), key=lambda entry: sum(item[1] for item in entry[1]), reverse=True):
            penalties = [penalty for _, penalty in entries]
            results.append(
                FactorBreakdownRow(
                    factor_label=label,
                    factor_category=category,
                    scope_locomotive_id=locomotive_id or "ALL",
                    occurrences=len(entries),
                    affected_locomotives=len({locomotive for locomotive, _ in entries}),
                    avg_penalty_points=self._avg(penalties),
                    max_penalty_points=round(max(penalties), 2),
                )
            )
        return results

    def analytics_alert_trends(
        self,
        bucket: str = "hour",
        locomotive_id: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
    ) -> list[AlertTrendRow]:
        alerts = self._filtered_alerts(locomotive_id=locomotive_id, from_ts=from_ts, to_ts=to_ts)
        grouped: dict[datetime, list[Alert]] = defaultdict(list)
        for alert in alerts:
            grouped[self._bucket_timestamp(alert.timestamp, bucket)].append(alert)

        results: list[AlertTrendRow] = []
        for bucket_start in sorted(grouped):
            items = grouped[bucket_start]
            results.append(
                AlertTrendRow(
                    bucket_start=bucket_start.isoformat(),
                    scope_locomotive_id=locomotive_id or "ALL",
                    alerts_total=len(items),
                    critical_alerts_total=sum(1 for item in items if item.severity == "critical"),
                    warning_alerts_total=sum(1 for item in items if item.severity == "warning"),
                    locomotives_affected=len({item.locomotive_id for item in items}),
                )
            )
        return results

    def analytics_alert_breakdown(
        self,
        dimension: str = "source",
        locomotive_id: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
    ) -> list[AlertBreakdownRow]:
        alerts = self._filtered_alerts(locomotive_id=locomotive_id, from_ts=from_ts, to_ts=to_ts)
        supported_dimensions = {"source", "severity", "code", "status"}
        if dimension not in supported_dimensions:
            raise ValueError(f"Unsupported alert breakdown dimension: {dimension}")
        grouped: dict[str, list[Alert]] = defaultdict(list)
        for alert in alerts:
            grouped[str(getattr(alert, dimension))].append(alert)

        results: list[AlertBreakdownRow] = []
        for dimension_value in sorted(grouped):
            items = grouped[dimension_value]
            results.append(
                AlertBreakdownRow(
                    dimension_name=dimension,
                    dimension_value=dimension_value,
                    scope_locomotive_id=locomotive_id or "ALL",
                    alerts_total=len(items),
                    critical_share_pct=round((sum(1 for item in items if item.severity == "critical") / len(items)) * 100, 2),
                    locomotives_affected=len({item.locomotive_id for item in items}),
                )
            )
        return results

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
