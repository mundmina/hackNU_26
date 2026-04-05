from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.schemas.telemetry import EnrichedTelemetry, TelemetryEvent


@dataclass(slots=True)
class TelemetryRuntimeDependencies:
    database: Any
    bus: Any
    health_engine: Any
    alert_engine: Any
    metrics: Any


async def process_telemetry_event(
    payload: TelemetryEvent,
    deps: TelemetryRuntimeDependencies,
) -> EnrichedTelemetry:
    previous = deps.database.latest_health(payload.locomotive_id)
    if previous:
        payload.metadata["delta_hours"] = max(
            1 / 3600,
            (payload.timestamp.astimezone(UTC) - previous.timestamp.astimezone(UTC)).total_seconds() / 3600,
        )

    health = deps.health_engine.evaluate(payload, previous_health=previous.score if previous else None)
    health.trend = deps.database.trend(payload.locomotive_id, points=60) + [health.score]
    alerts = deps.alert_engine.evaluate(payload, health)
    event_id = str(uuid4())

    deps.database.upsert_locomotive(payload)
    deps.database.save_event(event_id, payload, health, alerts)
    deps.metrics.increment("total_ingested")
    if alerts:
        deps.metrics.increment("total_alerts", len(alerts))

    event = EnrichedTelemetry(
        event_id=event_id,
        telemetry=payload,
        health=health.model_dump(mode="json"),
        alerts=[alert.model_dump(mode="json") for alert in alerts],
    )
    await deps.bus.publish(event.model_dump(mode="json"))
    return event


class DemoTelemetryAutopilot:
    def __init__(self, deps: TelemetryRuntimeDependencies, cadence_seconds: int = 60) -> None:
        self._deps = deps
        self._cadence_seconds = max(cadence_seconds, 5)
        self._task: asyncio.Task[None] | None = None
        self._tick = 0
        self._started_at = datetime.now(UTC)
        self._profiles = [
            {
                "locomotive_id": "KZ8A-0002",
                "locomotive_type": "KZ8A",
                "base_position": (43.31992, 77.01015),
                "scenario": "nominal",
            },
            {
                "locomotive_id": "TE33A-009",
                "locomotive_type": "TE33A",
                "base_position": (51.16512, 71.43156),
                "scenario": "stressed",
            },
        ]

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name="demo-telemetry-autopilot")

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    async def _run(self) -> None:
        while True:
            await self._emit_cycle()
            self._tick += 1
            await asyncio.sleep(self._cadence_seconds)

    async def _emit_cycle(self) -> None:
        event_time = self._started_at + timedelta(seconds=self._tick * self._cadence_seconds)
        for index, profile in enumerate(self._profiles):
            payload = self._build_event(profile, event_time=event_time + timedelta(seconds=index))
            await process_telemetry_event(payload, self._deps)

    def _build_event(self, profile: dict[str, Any], event_time: datetime) -> TelemetryEvent:
        phase = self._tick / 4
        stressed = profile["scenario"] == "stressed"
        lat, lon = profile["base_position"]
        degradation_boost = 1.0 if stressed else 0.35
        cycle_spike = 1.15 if stressed and self._tick % 6 in {2, 3} else 1.0

        speed = 71 + math.sin(phase) * 8 + (7 if stressed else 0)
        tractive_effort = 215 + abs(math.sin(phase * 0.95)) * 185 * degradation_boost * cycle_spike
        acceleration = math.sin(phase * 1.2) * (0.9 if not stressed else 1.55)
        wheel_slip = 1.2 + abs(math.sin(phase * 1.4)) * 5.5 * degradation_boost * cycle_spike
        adhesion = 0.27 - abs(math.sin(phase * 0.9)) * 0.16 * degradation_boost
        oil_temp = 88 + abs(math.sin(phase * 0.8)) * 34 * degradation_boost * cycle_spike
        coolant_temp = 77 + abs(math.cos(phase * 0.7)) * 28 * degradation_boost * cycle_spike
        oil_pressure = 0.47 - abs(math.sin(phase * 0.9)) * 0.22 * degradation_boost
        exhaust_temp = 445 + abs(math.sin(phase * 1.1)) * 245 * degradation_boost * cycle_spike
        turbo_rpm = 42000 + abs(math.cos(phase * 0.8)) * 27000 * degradation_boost
        compressor_pressure = 0.76 - abs(math.sin(phase * 1.1)) * 0.3 * degradation_boost
        winding_temp = 91 + abs(math.sin(phase * 0.75)) * 78 * degradation_boost * cycle_spike
        transformer_temp = 61 + abs(math.cos(phase * 0.65)) * 42 * (0.7 if stressed else 0.45)
        vibration = 7 + abs(math.sin(phase * 1.5)) * 25 * degradation_boost * cycle_spike
        ambient = 30 + abs(math.sin(phase * 0.4)) * 19 * (0.7 if stressed else 0.4)
        reservoir = 0.83 - abs(math.cos(phase * 1.3)) * 0.24 * degradation_boost
        brake_cylinder = 0.08 + abs(math.sin(phase * 0.9)) * 0.26 * degradation_boost
        brake_pad = 88 - self._tick * (1.9 if stressed else 0.4)
        solenoid_signal = 105 + abs(math.sin(phase * 1.05)) * 250 * degradation_boost * cycle_spike
        error_codes = 0 if not stressed else (2 if self._tick % 6 not in {2, 3} else 5)
        error_freq = 0.2 if not stressed else (2.9 if self._tick % 6 not in {2, 3} else 4.2)
        service_hours = 620 if not stressed else 1860 + self._tick * 15
        mtbf = 2250 if not stressed else 1180
        mttr = 5 if not stressed else 13
        availability = 97 if not stressed else 79
        overhaul_distance = 16000 if not stressed else 91500
        gradient = math.sin(phase * 0.6) * (5 if not stressed else 11)
        vertical_dynamics = 0.46 + abs(math.sin(phase * 1.3)) * 0.95 * degradation_boost
        frame_force = 135 + abs(math.cos(phase * 1.1)) * 235 * degradation_boost * cycle_spike
        rail_surface = "clean" if not stressed else ("wet" if self._tick % 6 in {0, 1, 4} else "oily")

        return TelemetryEvent(
            locomotive_id=profile["locomotive_id"],
            locomotive_type=profile["locomotive_type"],
            timestamp=event_time,
            speed_kmh=round(speed, 2),
            acceleration_mps2=round(acceleration, 2),
            tractive_effort_kn=round(tractive_effort, 2),
            wheel_slip_ratio_pct=round(wheel_slip, 2),
            adhesion_coefficient=round(max(0.05, adhesion), 3),
            traction_motor_current_a=round(740 + abs(math.sin(phase)) * 680 * degradation_boost * cycle_spike, 2),
            traction_motor_torque_nm=round(2400 + abs(math.sin(phase * 0.8)) * 2400 * degradation_boost * cycle_spike, 2),
            fuel_level_pct=round(max(8, 62 - self._tick * 1.6), 2) if profile["locomotive_type"] == "TE33A" else None,
            fuel_consumption_lph=round(240 + abs(math.sin(phase)) * 250 * degradation_boost, 2)
            if profile["locomotive_type"] == "TE33A"
            else None,
            catenary_voltage_kv=round(24.7 + math.sin(phase) * (1.4 if not stressed else 4.9), 2)
            if profile["locomotive_type"] == "KZ8A"
            else None,
            traction_circuit_voltage_v=round(2840 + math.sin(phase) * (260 if not stressed else 1280), 2),
            electric_power_kw=round(4550 + abs(math.sin(phase)) * 3100 * (0.6 if not stressed else 1.0), 2)
            if profile["locomotive_type"] == "KZ8A"
            else None,
            battery_voltage_v=round(111 - abs(math.sin(phase * 0.7)) * 21 * degradation_boost, 2),
            auxiliary_power_load_kw=round(64 + abs(math.cos(phase)) * 140 * degradation_boost, 2),
            engine_oil_temperature_c=round(oil_temp, 2),
            coolant_temperature_c=round(coolant_temp, 2),
            engine_oil_pressure_mpa=round(max(0.16, oil_pressure), 3),
            exhaust_gas_temperature_c=round(exhaust_temp, 2),
            turbocharger_rpm=round(turbo_rpm, 2),
            compressor_discharge_pressure_mpa=round(max(0.38, compressor_pressure), 3),
            traction_motor_winding_temp_c=round(winding_temp, 2),
            transformer_oil_temp_c=round(transformer_temp, 2) if profile["locomotive_type"] == "KZ8A" else None,
            vibration_amplitude_mms=round(vibration, 2),
            ambient_temperature_c=round(ambient, 2),
            main_reservoir_pressure_mpa=round(max(0.44, reservoir), 3),
            brake_cylinder_pressure_mpa=round(brake_cylinder, 3),
            brake_pad_wear_pct_remaining=round(max(12, brake_pad), 2),
            solenoid_valve_residual_signal_mv=round(solenoid_signal, 2),
            parking_brake_status=False,
            active_error_codes=error_codes,
            error_code_frequency_per_hour=round(error_freq, 2),
            operating_hours_since_last_service_h=round(service_hours, 2),
            mtbf_h=round(mtbf, 2),
            mttr_h=round(mttr, 2),
            locomotive_availability_pct=round(availability, 2),
            distance_since_last_overhaul_km=round(overhaul_distance, 2),
            gps_lat=round(lat + self._tick * 0.0045, 6),
            gps_lon=round(lon + self._tick * 0.0028, 6),
            track_gradient_permille=round(gradient, 2),
            speed_limit_kmh=120,
            vertical_dynamics_coefficient=round(vertical_dynamics, 2),
            frame_force_kn=round(frame_force, 2),
            rail_surface_state=rail_surface,
            metadata={"source": "backend-autopilot", "cadence_seconds": self._cadence_seconds},
        )
