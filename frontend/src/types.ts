export type LocomotiveType = "KZ8A" | "TE33A";

export interface TelemetryEvent {
  locomotive_id: string;
  locomotive_type: LocomotiveType;
  timestamp: string;
  speed_kmh: number;
  acceleration_mps2: number;
  tractive_effort_kn: number;
  wheel_slip_ratio_pct: number;
  adhesion_coefficient: number;
  traction_motor_current_a: number;
  traction_motor_torque_nm: number;
  fuel_level_pct?: number | null;
  fuel_consumption_lph?: number | null;
  catenary_voltage_kv?: number | null;
  traction_circuit_voltage_v?: number | null;
  electric_power_kw?: number | null;
  battery_voltage_v: number;
  auxiliary_power_load_kw: number;
  engine_oil_temperature_c: number;
  coolant_temperature_c: number;
  engine_oil_pressure_mpa: number;
  exhaust_gas_temperature_c: number;
  turbocharger_rpm: number;
  compressor_discharge_pressure_mpa: number;
  traction_motor_winding_temp_c: number;
  transformer_oil_temp_c?: number | null;
  vibration_amplitude_mms: number;
  ambient_temperature_c: number;
  main_reservoir_pressure_mpa: number;
  brake_cylinder_pressure_mpa: number;
  brake_pad_wear_pct_remaining: number;
  solenoid_valve_residual_signal_mv: number;
  parking_brake_status: boolean;
  active_error_codes: number;
  error_code_frequency_per_hour: number;
  operating_hours_since_last_service_h: number;
  mtbf_h: number;
  mttr_h: number;
  locomotive_availability_pct: number;
  distance_since_last_overhaul_km: number;
  gps_lat: number;
  gps_lon: number;
  track_gradient_permille: number;
  speed_limit_kmh: number;
  vertical_dynamics_coefficient: number;
  frame_force_kn: number;
  rail_surface_state: string;
  metadata: Record<string, unknown>;
}

export interface HealthFactor {
  key: string;
  label: string;
  category: string;
  penalty: number;
  detail: string;
}

export interface HealthSnapshot {
  locomotive_id: string;
  timestamp: string;
  score: number;
  grade: string;
  band: string;
  load_modifier: number;
  health_modifier: number;
  reliability_modifier: number;
  formula_score: number;
  trend: number[];
  factors: HealthFactor[];
}

export interface AlertItem {
  alert_id: string;
  locomotive_id: string;
  timestamp: string;
  severity: "warning" | "critical" | "info";
  code: string;
  message: string;
  status: string;
  source: string;
  details: Record<string, unknown>;
  recommendation: string;
}

export interface EnrichedTelemetry {
  event_id: string;
  telemetry: TelemetryEvent;
  health: HealthSnapshot;
  alerts: AlertItem[];
}

export interface FleetCard {
  locomotive_id: string;
  locomotive_type: LocomotiveType;
  last_seen: string;
  health_score: number;
  health_grade: string;
  alert_count: number;
  speed_kmh: number;
  location: [number, number];
}
