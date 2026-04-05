from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.schemas.alerts import Alert
from app.schemas.health import HealthSnapshot
from app.schemas.telemetry import TelemetryEvent

# Driver action recommendations keyed by alert code.
# Shown on the dashboard so the driver knows what to do immediately.
RECOMMENDATIONS: dict[str, str] = {
    "WHEEL_SLIP": (
        "Reduce traction force gradually. Apply sand if available. "
        "Ease off the throttle and allow wheel speed to stabilise before increasing power. "
        "If slip persists above 6%, engage emergency anti-slip mode and notify dispatcher."
    ),
    "OIL_TEMP_HIGH": (
        "Reduce tractive effort and speed to lower engine load. "
        "Check that oil cooling fans are running. "
        "If temperature exceeds 120 °C, bring the locomotive to a scheduled stop and notify maintenance. "
        "Do not shut down the engine abruptly — allow it to idle for 5 minutes to cool."
    ),
    "COOLANT_HIGH": (
        "Reduce engine load immediately. Verify coolant level and fan operation. "
        "If temperature does not drop within 5 minutes, stop at the next safe location. "
        "Do not remove the radiator cap while the system is hot."
    ),
    "BRAKE_PRESSURE_LOW": (
        "Reduce speed and increase stopping distance. "
        "Allow the compressor to rebuild reservoir pressure — avoid repeated full-service applications. "
        "If pressure drops below 0.62 MPa, apply the parking brake and halt. "
        "Contact dispatcher and do not proceed until pressure is restored."
    ),
    "BRAKE_PAD_LOW": (
        "Report pad wear to maintenance at the next stop. "
        "Increase stopping distances by 20% as a precaution. "
        "Avoid emergency braking. Schedule pad replacement before the next duty cycle."
    ),
    "ERROR_CODES_ACTIVE": (
        "Note the error code(s) displayed on the cab panel. "
        "Consult the fault reference card for the specific code. "
        "If the fault is safety-critical (marked red), notify the dispatcher and reduce speed. "
        "Log all active codes in the journey record."
    ),
    "CATENARY_VOLTAGE_ABNORMAL": (
        "Switch to auxiliary power mode if available. "
        "Reduce pantograph current draw by decreasing tractive effort. "
        "If voltage falls below 19 kV or exceeds 29 kV, lower the pantograph and coast to a stop. "
        "Report to the dispatcher and await infrastructure team response."
    ),
    "BATTERY_VOLTAGE_LOW": (
        "Switch non-essential auxiliary systems off (cabin heating, extra lighting). "
        "Check battery charger status on the cab panel. "
        "If voltage drops below 94 V, auxiliary control circuits may fail — "
        "stop at the nearest station and request maintenance."
    ),
    "HEALTH_INDEX_LOW": (
        "Grade D: Reduce speed by 20% and avoid aggressive acceleration or braking. "
        "Notify the dispatcher of degraded health status. "
        "Grade E (Critical): Bring the locomotive to a controlled stop at the nearest safe location. "
        "Do not continue service until a maintenance inspection is completed."
    ),
}


class AlertEngine:
    def __init__(self) -> None:
        self._last_emitted: dict[tuple[str, str], datetime] = {}
        self._dedupe_window = timedelta(seconds=45)

    def evaluate(self, telemetry: TelemetryEvent, health: HealthSnapshot) -> list[Alert]:
        alerts: list[Alert] = []
        now = telemetry.timestamp.astimezone(UTC)

        def maybe_emit(
            code: str,
            severity: str,
            message: str,
            source: str,
            details: dict[str, object],
        ) -> None:
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
                    recommendation=RECOMMENDATIONS.get(code, ""),
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

        if telemetry.coolant_temperature_c > 95:
            maybe_emit(
                "COOLANT_HIGH",
                "critical" if telemetry.coolant_temperature_c > 102 else "warning",
                "Coolant temperature trending high",
                "cooling",
                {"value": telemetry.coolant_temperature_c},
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

        if telemetry.active_error_codes > 0:
            maybe_emit(
                "ERROR_CODES_ACTIVE",
                "warning",
                "Onboard controller reports active error codes",
                "control",
                {"count": telemetry.active_error_codes},
            )

        if (
            telemetry.locomotive_type == "KZ8A"
            and telemetry.catenary_voltage_kv is not None
            and (telemetry.catenary_voltage_kv < 20.0 or telemetry.catenary_voltage_kv > 28.0)
        ):
            maybe_emit(
                "CATENARY_VOLTAGE_ABNORMAL",
                "critical" if (telemetry.catenary_voltage_kv < 19.5 or telemetry.catenary_voltage_kv > 28.5) else "warning",
                "Catenary voltage outside normal operating range (19–29 kV)",
                "power",
                {"value": telemetry.catenary_voltage_kv, "normal_range": "19–29 kV"},
            )

        if telemetry.battery_voltage_v < 98:
            maybe_emit(
                "BATTERY_VOLTAGE_LOW",
                "critical" if telemetry.battery_voltage_v < 94 else "warning",
                "Auxiliary battery voltage below safe threshold",
                "power",
                {"value": telemetry.battery_voltage_v},
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
