from __future__ import annotations

from pydantic import BaseModel


class KpiRow(BaseModel):
    generated_at: str
    scope_locomotive_id: str
    events: int
    locomotives: int
    avg_health_score: float
    min_health_score: float
    critical_event_rate_pct: float
    avg_speed_kmh: float
    avg_speed_limit_utilization_pct: float
    avg_alerts_per_event: float
    alert_events_pct: float
    alerts_total: int
    critical_alerts_total: int
    avg_availability_pct: float
    avg_mtbf_h: float
    avg_mttr_h: float
    avg_fuel_level_pct: float
    avg_electric_power_kw: float
    avg_wheel_slip_ratio_pct: float
    avg_vibration_mms: float
    avg_brake_pad_remaining_pct: float
    avg_reservoir_pressure_mpa: float


class TrendRow(BaseModel):
    bucket_start: str
    scope_locomotive_id: str
    events: int
    avg_health_score: float
    min_health_score: float
    critical_event_count: int
    avg_speed_kmh: float
    max_speed_kmh: float
    avg_speed_limit_utilization_pct: float
    avg_alerts_per_event: float
    avg_engine_oil_temperature_c: float
    avg_coolant_temperature_c: float
    avg_wheel_slip_ratio_pct: float
    avg_vibration_mms: float
    avg_reservoir_pressure_mpa: float
    avg_availability_pct: float


class BreakdownRow(BaseModel):
    dimension_name: str
    dimension_value: str
    scope_locomotive_id: str
    events: int
    locomotives: int
    avg_health_score: float
    critical_event_rate_pct: float
    avg_alerts_per_event: float
    avg_speed_kmh: float
    avg_wheel_slip_ratio_pct: float
    avg_vibration_mms: float


class FactorBreakdownRow(BaseModel):
    factor_label: str
    factor_category: str
    scope_locomotive_id: str
    occurrences: int
    affected_locomotives: int
    avg_penalty_points: float
    max_penalty_points: float


class AlertTrendRow(BaseModel):
    bucket_start: str
    scope_locomotive_id: str
    alerts_total: int
    critical_alerts_total: int
    warning_alerts_total: int
    locomotives_affected: int


class AlertBreakdownRow(BaseModel):
    dimension_name: str
    dimension_value: str
    scope_locomotive_id: str
    alerts_total: int
    critical_share_pct: float
    locomotives_affected: int


class ReportingEventRow(BaseModel):
    event_id: str
    timestamp: str
    event_date: str
    locomotive_id: str
    locomotive_type: str
    health_score: float
    health_grade: str
    health_band: str
    speed_kmh: float
    speed_limit_kmh: float
    speed_limit_utilization_pct: float
    tractive_effort_kn: float
    wheel_slip_ratio_pct: float
    adhesion_coefficient: float
    battery_voltage_v: float
    electric_power_kw: float
    fuel_level_pct: float
    fuel_consumption_lph: float
    engine_oil_temperature_c: float
    coolant_temperature_c: float
    engine_oil_pressure_mpa: float
    exhaust_gas_temperature_c: float
    traction_motor_winding_temp_c: float
    vibration_amplitude_mms: float
    main_reservoir_pressure_mpa: float
    brake_pad_wear_pct_remaining: float
    active_error_codes: int
    alert_count: int
    critical_alert_count: int
    locomotive_availability_pct: float
    mtbf_h: float
    mttr_h: float
    distance_since_last_overhaul_km: float
    track_gradient_permille: float
    rail_surface_state: str
    top_factor_label: str
    top_factor_category: str
    top_factor_penalty_points: float
