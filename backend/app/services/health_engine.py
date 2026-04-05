from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC

from app.schemas.health import HealthFactor, HealthSnapshot
from app.schemas.telemetry import TelemetryEvent


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(slots=True)
class RuleResult:
    penalty: float
    factor: HealthFactor | None


class HealthIndexEngine:
    def evaluate(self, telemetry: TelemetryEvent, previous_health: float | None = None) -> HealthSnapshot:
        load_results = [
            self._high_is_bad(
                telemetry.speed_kmh / max(telemetry.speed_limit_kmh, 1),
                0.75,
                1.0,
                0.09,
                "speed",
                "Speed utilization",
                "load",
                "speed ratio to segment limit",
                suffix="x of limit",
            ),
            self._high_is_bad(
                abs(telemetry.acceleration_mps2),
                1.0,
                2.0,
                0.07,
                "acceleration",
                "Acceleration",
                "load",
                "aggressive acceleration or braking",
                suffix="m/s²",
            ),
            self._high_is_bad(
                telemetry.tractive_effort_kn,
                250,
                400,
                0.1,
                "tractive_effort",
                "Tractive effort",
                "load",
                "sustained traction load",
                suffix="kN",
            ),
            self._high_is_bad(
                telemetry.fuel_consumption_lph or telemetry.electric_power_kw or 0,
                5000 if telemetry.locomotive_type == "KZ8A" else 300,
                7000 if telemetry.locomotive_type == "KZ8A" else 600,
                0.08,
                "resource_burn",
                "Resource burn",
                "load",
                "fuel or electric power draw",
                suffix="kW/Lh",
            ),
            self._high_is_bad(
                telemetry.traction_motor_current_a,
                900,
                1300,
                0.07,
                "motor_current",
                "Traction motor current",
                "load",
                "traction motor current above norm",
                suffix="A",
            ),
            self._high_is_bad(
                telemetry.traction_motor_torque_nm,
                3000,
                4500,
                0.06,
                "motor_torque",
                "Traction motor torque",
                "load",
                "traction motor torque above norm",
                suffix="N·m",
            ),
            self._high_is_bad(
                abs(telemetry.track_gradient_permille),
                4,
                10,
                0.05,
                "track_gradient",
                "Track gradient",
                "load",
                "route gradient stress",
                suffix="‰",
            ),
            self._high_is_bad(
                telemetry.auxiliary_power_load_kw,
                120,
                180,
                0.04,
                "auxiliary_load",
                "Auxiliary power load",
                "load",
                "auxiliary systems drawing excessive power",
                suffix="kW",
            ),
        ]

        health_results = [
            self._high_is_bad(
                telemetry.wheel_slip_ratio_pct,
                2.5,
                6,
                0.12,
                "wheel_slip",
                "Wheel slip ratio",
                "health",
                "loss of adhesion",
                suffix="%",
            ),
            self._low_is_bad(
                telemetry.adhesion_coefficient,
                0.18,
                0.1,
                0.08,
                "adhesion",
                "Adhesion coefficient",
                "health",
                "reduced wheel-rail adhesion",
                suffix="µ",
            ),
            self._high_is_bad(
                telemetry.engine_oil_temperature_c,
                100,
                118,
                0.12,
                "oil_temp",
                "Engine oil temperature",
                "health",
                "oil temperature above norm",
                suffix="°C",
            ),
            self._high_is_bad(
                telemetry.coolant_temperature_c,
                88,
                102,
                0.1,
                "coolant_temp",
                "Coolant temperature",
                "health",
                "coolant temperature above norm",
                suffix="°C",
            ),
            self._low_is_bad(
                telemetry.engine_oil_pressure_mpa,
                0.35,
                0.22,
                0.08,
                "oil_pressure",
                "Engine oil pressure",
                "health",
                "lubrication pressure below norm",
                suffix="MPa",
            ),
            self._high_is_bad(
                telemetry.exhaust_gas_temperature_c,
                580,
                670,
                0.08,
                "egt",
                "Exhaust gas temperature",
                "health",
                "exhaust temperature above norm",
                suffix="°C",
            ),
            self._high_is_bad(
                telemetry.turbocharger_rpm,
                62000,
                78000,
                0.06,
                "turbo_rpm",
                "Turbocharger speed",
                "health",
                "turbocharger speed above norm",
                suffix="rpm",
            ),
            self._high_is_bad(
                telemetry.traction_motor_winding_temp_c,
                120,
                160,
                0.11,
                "motor_temp",
                "Traction motor winding temp",
                "health",
                "motor winding overheating",
                suffix="°C",
            ),
            self._high_is_bad(
                telemetry.transformer_oil_temp_c or 40,
                70,
                95,
                0.08,
                "transformer_temp",
                "Transformer oil temp",
                "health",
                "transformer oil overheating",
                suffix="°C",
            ),
            self._high_is_bad(
                telemetry.vibration_amplitude_mms,
                12,
                28,
                0.13,
                "vibration",
                "Wheelset vibration",
                "health",
                "vibration above norm",
                suffix="mm/s",
            ),
            self._range_is_bad(
                telemetry.catenary_voltage_kv,
                20,
                28,
                19,
                28.5,
                0.08,
                "catenary_voltage",
                "Catenary voltage",
                "health",
                "catenary voltage outside nominal window",
                suffix="kV",
            ),
            self._low_is_bad(
                telemetry.traction_circuit_voltage_v if telemetry.traction_circuit_voltage_v is not None else 2400,
                2400,
                1800,
                0.08,
                "traction_voltage",
                "Traction circuit voltage",
                "health",
                "traction circuit voltage below norm",
                suffix="V",
            ),
            self._low_is_bad(
                telemetry.battery_voltage_v,
                100,
                92,
                0.07,
                "battery_voltage",
                "Battery voltage",
                "health",
                "battery voltage below norm",
                suffix="V",
            ),
            self._high_is_bad(
                max(telemetry.ambient_temperature_c, 0),
                38,
                48,
                0.04,
                "ambient_temp",
                "Ambient temperature",
                "health",
                "ambient temperature above norm",
                suffix="°C",
            ),
            self._high_is_bad(
                telemetry.vertical_dynamics_coefficient,
                0.8,
                1.2,
                0.05,
                "vertical_dynamics",
                "Vertical dynamics coefficient",
                "health",
                "dynamic instability",
                suffix="coef",
            ),
            self._high_is_bad(
                telemetry.frame_force_kn,
                220,
                340,
                0.06,
                "frame_force",
                "Frame force",
                "health",
                "high frame force",
                suffix="kN",
            ),
            self._categorical_penalty(
                telemetry.rail_surface_state,
                penalties={
                    "wet": (0.04, "rail surface wet"),
                    "oily": (0.09, "rail surface oily"),
                },
                key="rail_surface_state",
                label="Rail surface state",
                category="health",
                suffix="state",
            ),
        ]

        reliability_results = [
            self._high_is_bad(
                float(telemetry.active_error_codes),
                1,
                5,
                0.1,
                "error_codes",
                "Active error codes",
                "reliability",
                "active onboard fault codes",
                suffix="codes",
            ),
            self._high_is_bad(
                telemetry.error_code_frequency_per_hour,
                1.0,
                3.5,
                0.08,
                "error_frequency",
                "Error code frequency",
                "reliability",
                "frequent control-system faults",
                suffix="events/h",
            ),
            self._low_is_bad(
                telemetry.compressor_discharge_pressure_mpa,
                0.65,
                0.52,
                0.05,
                "compressor_pressure",
                "Compressor discharge pressure",
                "reliability",
                "compressor discharge pressure below norm",
                suffix="MPa",
            ),
            self._high_is_bad(
                telemetry.operating_hours_since_last_service_h,
                1200,
                2200,
                0.08,
                "service_hours",
                "Hours since service",
                "reliability",
                "extended runtime since last service",
                suffix="h",
            ),
            self._low_is_bad(
                telemetry.mtbf_h,
                1800,
                1200,
                0.06,
                "mtbf",
                "MTBF",
                "reliability",
                "lower than expected reliability",
                suffix="h",
            ),
            self._high_is_bad(
                telemetry.mttr_h,
                8,
                16,
                0.05,
                "mttr",
                "MTTR",
                "reliability",
                "long repair windows",
                suffix="h",
            ),
            self._low_is_bad(
                telemetry.locomotive_availability_pct,
                92,
                80,
                0.06,
                "availability",
                "Locomotive availability",
                "reliability",
                "availability below target",
                suffix="%",
            ),
            self._high_is_bad(
                telemetry.distance_since_last_overhaul_km,
                40000,
                90000,
                0.07,
                "overhaul_distance",
                "Distance since overhaul",
                "reliability",
                "overhaul interval drift",
                suffix="km",
            ),
            self._low_is_bad(
                telemetry.main_reservoir_pressure_mpa,
                0.72,
                0.6,
                0.09,
                "reservoir_pressure",
                "Main reservoir pressure",
                "reliability",
                "air reservoir pressure below norm",
                suffix="MPa",
            ),
            self._low_is_bad(
                telemetry.brake_pad_wear_pct_remaining,
                35,
                20,
                0.08,
                "brake_pad_remaining",
                "Brake pad remaining life",
                "reliability",
                "brake pads near replacement threshold",
                suffix="%",
            ),
            self._high_is_bad(
                telemetry.solenoid_valve_residual_signal_mv,
                180,
                320,
                0.05,
                "solenoid_signal",
                "Solenoid valve residual signal",
                "reliability",
                "brake solenoid residual signal elevated",
                suffix="mV",
            ),
            self._high_is_bad(
                telemetry.brake_cylinder_pressure_mpa,
                0.15,
                0.3,
                0.06,
                "brake_cylinder_pressure",
                "Brake cylinder pressure",
                "reliability",
                "brake cylinder pressure above norm",
                suffix="MPa",
            ),
        ]

        if telemetry.parking_brake_status and telemetry.speed_kmh > 1:
            reliability_results.append(
                RuleResult(
                    0.12,
                    HealthFactor(
                        key="parking_brake",
                        label="Parking brake status",
                        category="reliability",
                        penalty=12.0,
                        detail="parking brake engaged while locomotive is moving",
                    ),
                )
            )

        load_modifier = sum(result.penalty for result in load_results)
        health_modifier = sum(result.penalty for result in health_results)
        reliability_modifier = sum(result.penalty for result in reliability_results)

        beta = 0.22 if telemetry.locomotive_type == "TE33A" else 0.18
        time_delta_hours = max(1 / 60, telemetry.metadata.get("delta_hours", 1 / 60))
        formula_score = 100 * math.exp(-(load_modifier * beta * time_delta_hours)) * math.exp(
            -(health_modifier + reliability_modifier)
        )

        if previous_health is None:
            score = formula_score
        elif formula_score <= previous_health:
            score = formula_score
        else:
            score = min(100.0, previous_health + min(2.0, (formula_score - previous_health) * 0.25))

        score = clamp(score, 0.0, 100.0)
        grade, band = self._classify(score)
        factors = sorted(
            [result.factor for result in load_results + health_results + reliability_results if result.factor],
            key=lambda item: item.penalty,
            reverse=True,
        )[:6]

        return HealthSnapshot(
            locomotive_id=telemetry.locomotive_id,
            timestamp=telemetry.timestamp.astimezone(UTC),
            score=round(score, 2),
            grade=grade,
            band=band,
            load_modifier=round(load_modifier, 4),
            health_modifier=round(health_modifier, 4),
            reliability_modifier=round(reliability_modifier, 4),
            formula_score=round(formula_score, 2),
            factors=factors,
        )

    def _classify(self, score: float) -> tuple[str, str]:
        if score >= 85:
            return "A", "Normal"
        if score >= 70:
            return "B", "Advisory"
        if score >= 50:
            return "C", "Caution"
        if score >= 30:
            return "D", "Warning"
        return "E", "Critical"

    def _high_is_bad(
        self,
        value: float,
        soft_limit: float,
        hard_limit: float,
        weight: float,
        key: str,
        label: str,
        category: str,
        detail: str,
        suffix: str,
    ) -> RuleResult:
        if value <= soft_limit:
            return RuleResult(0.0, None)
        span = max(hard_limit - soft_limit, 0.0001)
        normalized = clamp((value - soft_limit) / span, 0.0, 1.8)
        penalty = weight * normalized
        factor = HealthFactor(
            key=key,
            label=label,
            category=category,
            penalty=round(penalty * 100, 2),
            detail=f"{detail} -> {round(value, 2)} {suffix}",
        )
        return RuleResult(penalty, factor)

    def _range_is_bad(
        self,
        value: float | None,
        normal_min: float,
        normal_max: float,
        warn_min: float,
        warn_max: float,
        weight: float,
        key: str,
        label: str,
        category: str,
        detail: str,
        suffix: str,
    ) -> RuleResult:
        if value is None:
            return RuleResult(0.0, None)
        if normal_min <= value <= normal_max:
            return RuleResult(0.0, None)

        if value < warn_min:
            span = max(normal_min - warn_min, 0.0001)
            normalized = 1 + clamp((normal_min - value) / span, 0.0, 1.8)
        elif value > warn_max:
            span = max(warn_max - normal_max, 0.0001)
            normalized = 1 + clamp((value - normal_max) / span, 0.0, 1.8)
        elif value < normal_min:
            span = max(normal_min - warn_min, 0.0001)
            normalized = clamp((normal_min - value) / span, 0.0, 1.0)
        else:
            span = max(warn_max - normal_max, 0.0001)
            normalized = clamp((value - normal_max) / span, 0.0, 1.0)

        penalty = weight * normalized
        factor = HealthFactor(
            key=key,
            label=label,
            category=category,
            penalty=round(penalty * 100, 2),
            detail=f"{detail} -> {round(value, 2)} {suffix}",
        )
        return RuleResult(penalty, factor)

    def _categorical_penalty(
        self,
        value: str,
        penalties: dict[str, tuple[float, str]],
        key: str,
        label: str,
        category: str,
        suffix: str,
    ) -> RuleResult:
        match = penalties.get(value)
        if match is None:
            return RuleResult(0.0, None)
        penalty, detail = match
        factor = HealthFactor(
            key=key,
            label=label,
            category=category,
            penalty=round(penalty * 100, 2),
            detail=f"{detail} -> {value} {suffix}",
        )
        return RuleResult(penalty, factor)

    def _low_is_bad(
        self,
        value: float,
        soft_limit: float,
        hard_limit: float,
        weight: float,
        key: str,
        label: str,
        category: str,
        detail: str,
        suffix: str,
    ) -> RuleResult:
        if value >= soft_limit:
            return RuleResult(0.0, None)
        span = max(soft_limit - hard_limit, 0.0001)
        normalized = clamp((soft_limit - value) / span, 0.0, 1.8)
        penalty = weight * normalized
        factor = HealthFactor(
            key=key,
            label=label,
            category=category,
            penalty=round(penalty * 100, 2),
            detail=f"{detail} -> {round(value, 2)} {suffix}",
        )
        return RuleResult(penalty, factor)
