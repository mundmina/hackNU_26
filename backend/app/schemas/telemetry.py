from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


LocomotiveType = Literal["KZ8A", "TE33A"]
RailSurfaceState = Literal["clean", "wet", "oily", "sanded", "unknown"]


class TelemetryEvent(BaseModel):
    locomotive_id: str = Field(..., examples=["KZ8A-001"])
    locomotive_type: LocomotiveType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    speed_kmh: float = 0
    acceleration_mps2: float = 0
    tractive_effort_kn: float = 0
    wheel_slip_ratio_pct: float = 0
    adhesion_coefficient: float = 0.25
    traction_motor_current_a: float = 0
    traction_motor_torque_nm: float = 0
    fuel_level_pct: float | None = None
    fuel_consumption_lph: float | None = None
    catenary_voltage_kv: float | None = None
    traction_circuit_voltage_v: float | None = None
    electric_power_kw: float | None = None
    battery_voltage_v: float = 110
    auxiliary_power_load_kw: float = 40
    engine_oil_temperature_c: float = 85
    coolant_temperature_c: float = 75
    engine_oil_pressure_mpa: float = 0.45
    exhaust_gas_temperature_c: float = 430
    turbocharger_rpm: float = 25000
    compressor_discharge_pressure_mpa: float = 0.75
    traction_motor_winding_temp_c: float = 85
    transformer_oil_temp_c: float | None = None
    vibration_amplitude_mms: float = 7
    ambient_temperature_c: float = 20
    main_reservoir_pressure_mpa: float = 0.82
    brake_cylinder_pressure_mpa: float = 0.1
    brake_pad_wear_pct_remaining: float = 92
    solenoid_valve_residual_signal_mv: float = 80
    parking_brake_status: bool = False
    active_error_codes: int = 0
    error_code_frequency_per_hour: float = 0
    operating_hours_since_last_service_h: float = 500
    mtbf_h: float = 2000
    mttr_h: float = 5
    locomotive_availability_pct: float = 96
    distance_since_last_overhaul_km: float = 12000
    gps_lat: float = 43.238949
    gps_lon: float = 76.889709
    track_gradient_permille: float = 2
    speed_limit_kmh: float = 120
    vertical_dynamics_coefficient: float = 0.4
    frame_force_kn: float = 100
    rail_surface_state: RailSurfaceState = "clean"
    metadata: dict[str, Any] = Field(default_factory=dict)


class EnrichedTelemetry(BaseModel):
    event_id: str
    telemetry: TelemetryEvent
    health: dict[str, Any]
    alerts: list[dict[str, Any]]


class FleetCard(BaseModel):
    locomotive_id: str
    locomotive_type: LocomotiveType
    last_seen: datetime
    health_score: float
    health_grade: str
    alert_count: int
    speed_kmh: float
    location: tuple[float, float]
