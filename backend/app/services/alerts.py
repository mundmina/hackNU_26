from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.schemas.alerts import Alert
from app.schemas.health import HealthSnapshot
from app.schemas.telemetry import TelemetryEvent


class AlertEngine:
    def __init__(self) -> None:
        self._last_emitted: dict[tuple[str, str], datetime] = {}
        self._dedupe_window = timedelta(seconds=45)

    def evaluate(self, telemetry: TelemetryEvent, health: HealthSnapshot) -> list[Alert]:
        alerts: list[Alert] = []
        now = telemetry.timestamp.astimezone(UTC)

        def maybe_emit(code: str, severity: str, message: str, source: str, details: dict[str, object]) -> None:
            key = (telemetry.locomotive_id, code)
            previous = self._last_emitted.get(key)
            if previous and now - previous < self._dedupe_window:
                return
            alerts.append(
                Alert(
                    alert_id=str(uuid4()),
                    locomotive_id=telemetry.locomotive_id,
                    timestamp=now,
                    severity=severity,
                    code=code,
                    message=message,
                    source=source,
                    details=details,
                )
            )
            self._last_emitted[key] = now

        if telemetry.wheel_slip_ratio_pct > 3:
            maybe_emit(
                "WHEEL_SLIP",
                "warning" if telemetry.wheel_slip_ratio_pct < 6 else "critical",
                "Wheel slip ratio above 3%",
                "traction",
                {"value": telemetry.wheel_slip_ratio_pct},
            )
        if telemetry.engine_oil_temperature_c > 110:
            maybe_emit(
                "OIL_TEMP_HIGH",
                "critical" if telemetry.engine_oil_temperature_c > 120 else "warning",
                "Engine oil temperature above safe threshold",
                "engine",
                {"value": telemetry.engine_oil_temperature_c},
            )
        if telemetry.catenary_voltage_kv is not None and (telemetry.catenary_voltage_kv < 20 or telemetry.catenary_voltage_kv > 28):
            maybe_emit(
                "CATENARY_VOLTAGE",
                "critical" if telemetry.catenary_voltage_kv < 19 or telemetry.catenary_voltage_kv > 28.5 else "warning",
                "Catenary voltage outside nominal range",
                "power",
                {"value": telemetry.catenary_voltage_kv},
            )
        if telemetry.traction_circuit_voltage_v is not None and telemetry.traction_circuit_voltage_v < 2400:
            maybe_emit(
                "TRACTION_VOLTAGE_LOW",
                "critical" if telemetry.traction_circuit_voltage_v < 1800 else "warning",
                "Traction circuit voltage below nominal range",
                "power",
                {"value": telemetry.traction_circuit_voltage_v},
            )
        if telemetry.battery_voltage_v < 100:
            maybe_emit(
                "BATTERY_LOW",
                "critical" if telemetry.battery_voltage_v < 92 else "warning",
                "Battery voltage below nominal range",
                "power",
                {"value": telemetry.battery_voltage_v},
            )
        if telemetry.coolant_temperature_c > 95:
            maybe_emit(
                "COOLANT_HIGH",
                "critical" if telemetry.coolant_temperature_c > 102 else "warning",
                "Coolant temperature trending high",
                "cooling",
                {"value": telemetry.coolant_temperature_c},
            )
        if telemetry.vibration_amplitude_mms > 12:
            maybe_emit(
                "VIBRATION_HIGH",
                "critical" if telemetry.vibration_amplitude_mms > 28 else "warning",
                "Wheelset vibration above nominal range",
                "running-gear",
                {"value": telemetry.vibration_amplitude_mms},
            )
        if telemetry.main_reservoir_pressure_mpa < 0.7:
            maybe_emit(
                "BRAKE_PRESSURE_LOW",
                "critical" if telemetry.main_reservoir_pressure_mpa < 0.62 else "warning",
                "Main reservoir pressure below safe range",
                "brakes",
                {"value": telemetry.main_reservoir_pressure_mpa},
            )
        if telemetry.brake_pad_wear_pct_remaining < 25:
            maybe_emit(
                "BRAKE_PAD_LOW",
                "warning",
                "Brake pad life below maintenance threshold",
                "brakes",
                {"remaining_pct": telemetry.brake_pad_wear_pct_remaining},
            )
        if telemetry.parking_brake_status and telemetry.speed_kmh > 1:
            maybe_emit(
                "PARKING_BRAKE_ENGAGED",
                "critical",
                "Parking brake engaged while locomotive is moving",
                "brakes",
                {"speed_kmh": telemetry.speed_kmh},
            )
        if telemetry.active_error_codes > 0:
            maybe_emit(
                "ERROR_CODES_ACTIVE",
                "critical" if telemetry.active_error_codes > 4 else "warning",
                "Onboard controller reports active error codes",
                "control",
                {"count": telemetry.active_error_codes},
            )
        if health.score < 50:
            maybe_emit(
                "HEALTH_INDEX_LOW",
                "critical" if health.score < 30 else "warning",
                f"Health Index degraded to {health.grade} ({health.score})",
                "health-index",
                {"score": health.score, "grade": health.grade},
            )

        return alerts
