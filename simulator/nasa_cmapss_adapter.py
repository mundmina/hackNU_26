"""
NASA C-MAPSS Dataset Adapter
========================================
Operational Plan v2 — Dataset Integration (§10 / dataset.md)

Converts NASA C-MAPSS turbofan engine degradation data into the
Locomotive Digital Twin telemetry schema, enabling real run-to-failure
patterns to supplement the synthetic simulator.

Why C-MAPSS?
────────────
• Widely cited in PHM/prognostics literature (same research context as plan refs).
• Contains 21 sensor streams across 4 operating conditions (FD001–FD004).
• Provides ground-truth RUL (Remaining Useful Life) for AUROC / F1 evaluation.
• Monotonic degradation patterns validate the HI engine's Trendability metric.

Sensor Mapping  (C-MAPSS → Locomotive Digital Twin)
────────────────────────────────────────────────────
C-MAPSS col  Symbol   Description                      → TelemetryEvent field
──────────── ──────── ────────────────────────────── → ──────────────────────────
s3           T30      HPC outlet temperature (°R)    → engine_oil_temperature_c
s4           T50      LPT outlet temperature (°R)    → exhaust_gas_temperature_c
s7           P30      HPC outlet pressure (psia)     → compressor_discharge_pressure_mpa
s8           Nf       Physical fan speed (rpm)       → turbocharger_rpm  (×30 scale)
s9           Nc       Physical core speed (rpm)      → traction_motor_current_a (×0.15 scale)
s11          Ps30     Static HPC pressure (psia)     → traction_circuit_voltage_v (×2 scale)
s12          phi      Fuel-flow/Ps30 ratio           → fuel_consumption_lph (×1.5 scale)
s14          NRc      Corrected core speed (rpm)     → traction_motor_winding_temp_c (÷40)
s15          BPR      Bypass ratio                   → adhesion_coefficient (÷10 scale)
s20          W31      HPT coolant bleed (lbm/s)      → vibration_amplitude_mms (×0.3)
s21          W32      LPT coolant bleed (lbm/s)      → coolant_temperature_c  (×0.4 + 60)
RUL %        —        Remaining useful life %        → brake_pad_wear_pct_remaining

Usage — with real C-MAPSS data
───────────────────────────────
  1. Download from https://data.nasa.gov/dataset/C-MAPSS-Aircraft-Engine-Simulator-Data/xaut-bemq
     or Kaggle: https://www.kaggle.com/datasets/behrad3d/nasa-cmapss
  2. Place train_FD001.txt in simulator/data/cmapss/
  3. Run:
       python3 simulator/nasa_cmapss_adapter.py --file simulator/data/cmapss/train_FD001.txt

Usage — with built-in synthetic demo (no download needed)
───────────────────────────────────────────────────────────
  python3 simulator/nasa_cmapss_adapter.py --demo
  python3 simulator/nasa_cmapss_adapter.py --demo --db backend/data/digital_twin.db
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

UTC = timezone.utc

# ── Column indices in the raw C-MAPSS text file (0-based) ──────────────────
COL_UNIT  = 0
COL_CYCLE = 1
COL_OP1   = 2  # operational setting 1
COL_OP2   = 3  # operational setting 2
COL_OP3   = 4  # operational setting 3
# Sensors s1..s21 → columns 5..25
SENSOR_OFFSET = 5

# C-MAPSS sensor indices within s1..s21 (0-based from s1)
S3  = 2   # T30 HPC outlet temp
S4  = 3   # T50 LPT outlet temp
S7  = 6   # P30 HPC pressure
S8  = 7   # Nf fan speed
S9  = 8   # Nc core speed
S11 = 10  # Ps30 static pressure
S12 = 11  # phi fuel-flow ratio
S14 = 13  # NRc corrected core speed
S15 = 14  # BPR bypass ratio
S20 = 19  # W31 HPT bleed
S21 = 20  # W32 LPT bleed


# ─────────────────────────────────────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────────────────────────────────────

def parse_cmapss_file(path: Path) -> dict[int, list[list[float]]]:
    """
    Parse a C-MAPSS train/test text file.

    Returns {unit_id: [[col0, col1, ..., col25], ...], ...}
    """
    engines: dict[int, list[list[float]]] = {}
    with open(path) as fh:
        for line in fh:
            parts = line.strip().split()
            if not parts:
                continue
            row = [float(v) for v in parts]
            unit = int(row[COL_UNIT])
            engines.setdefault(unit, []).append(row)
    return engines


# ─────────────────────────────────────────────────────────────────────────────
# Sensor conversion helpers
# ─────────────────────────────────────────────────────────────────────────────

def _rankine_to_celsius(r: float) -> float:
    """Convert Rankine to Celsius."""
    return (r - 491.67) * 5 / 9


def _psia_to_mpa(p: float) -> float:
    """Convert psia to MPa."""
    return p * 0.00689476


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def row_to_telemetry(
    row: list[float],
    unit_id: int,
    loco_id: str,
    cycle: int,
    max_cycle: int,
    ts: datetime,
    previous_score: float | None = None,
) -> dict:
    """
    Convert one C-MAPSS row to a TelemetryEvent-compatible dict.

    RUL % = (max_cycle - cycle) / max_cycle  → mapped to brake_pad_wear_pct_remaining
    so that 100% = brand new and 0% = end-of-life (matching the plan's wear metric).
    """
    s = row[SENSOR_OFFSET:]  # s1..s21 (index 0 = s1)

    rul_pct = _clamp((max_cycle - cycle) / max_cycle * 100, 0.0, 100.0)

    # Thermal conversions
    oil_temp_c  = _clamp(_rankine_to_celsius(s[S3]), 40, 130)
    egt_c       = _clamp(_rankine_to_celsius(s[S4]), 200, 700)
    coolant_c   = _clamp(s[S21] * 0.4 + 60, 40, 110)

    # Pressure
    comp_p_mpa  = _clamp(_psia_to_mpa(s[S7]), 0.5, 1.0)

    # Speed / electrical analogues
    turbo_rpm   = _clamp(s[S8] * 30, 0, 80000)
    motor_cur_a = _clamp(s[S9] * 0.15, 0, 1500)
    circuit_v   = _clamp(s[S11] * 2, 0, 3600)

    # Motion / traction analogues
    fuel_lph    = _clamp(s[S12] * 1.5, 0, 600)
    adhesion    = _clamp(s[S15] / 10, 0.05, 0.40)
    vibration   = _clamp(s[S20] * 0.3, 0, 50)

    # Winding temp from corrected core speed proxy
    winding_t   = _clamp(s[S14] / 40, 20, 180)

    # Reliability fields: degrade as cycle / max_cycle increases
    age_ratio   = cycle / max_cycle
    availability = _clamp(97 - age_ratio * 25, 60, 97)
    mtbf        = _clamp(2400 - age_ratio * 1400, 800, 2400)
    service_h   = _clamp(age_ratio * 2000, 0, 2000)
    overhaul_km = _clamp(age_ratio * 90000, 0, 90000)

    # HI inline (simplified, mirrors health_engine.py logic)
    # We use rul_pct as a direct anchor for brake pad wear —
    # the HI engine will compute the actual score from sensor values.
    payload = {
        "locomotive_id":   loco_id,
        "locomotive_type": "TE33A",   # map to diesel-electric for sensor set
        "timestamp":       ts.isoformat(),
        "speed_kmh":       round(70 + math.sin(cycle / 8) * 15, 2),
        "acceleration_mps2": round(math.sin(cycle / 5) * 0.8, 2),
        "tractive_effort_kn": round(200 + age_ratio * 120, 2),
        "wheel_slip_ratio_pct": round(1.5 + age_ratio * 4.5, 2),
        "adhesion_coefficient": round(adhesion, 3),
        "traction_motor_current_a": round(motor_cur_a, 2),
        "traction_motor_torque_nm": round(1800 + age_ratio * 1800, 2),
        "fuel_level_pct":  round(_clamp(80 - age_ratio * 60, 10, 80), 2),
        "fuel_consumption_lph": round(fuel_lph, 2),
        "catenary_voltage_kv": None,   # TE33A — diesel only
        "traction_circuit_voltage_v": round(circuit_v, 2),
        "electric_power_kw": None,
        "battery_voltage_v": round(_clamp(112 - age_ratio * 18, 90, 114), 2),
        "auxiliary_power_load_kw": round(40 + age_ratio * 25, 2),
        "engine_oil_temperature_c": round(oil_temp_c, 2),
        "coolant_temperature_c":    round(coolant_c, 2),
        "engine_oil_pressure_mpa":  round(_clamp(0.46 - age_ratio * 0.24, 0.22, 0.46), 3),
        "exhaust_gas_temperature_c": round(egt_c, 2),
        "turbocharger_rpm": round(turbo_rpm, 2),
        "compressor_discharge_pressure_mpa": round(comp_p_mpa, 3),
        "traction_motor_winding_temp_c": round(winding_t, 2),
        "transformer_oil_temp_c": None,
        "vibration_amplitude_mms": round(vibration, 2),
        "ambient_temperature_c": round(15 + math.sin(cycle / 20) * 10, 2),
        "main_reservoir_pressure_mpa": round(_clamp(0.84 - age_ratio * 0.22, 0.62, 0.84), 3),
        "brake_cylinder_pressure_mpa": round(0.1 + age_ratio * 0.12, 3),
        "brake_pad_wear_pct_remaining": round(rul_pct, 2),  # RUL % directly
        "solenoid_valve_residual_signal_mv": round(90 + age_ratio * 230, 2),
        "parking_brake_status": False,
        "active_error_codes": 2 if rul_pct < 20 else (1 if rul_pct < 40 else 0),
        "error_code_frequency_per_hour": round(age_ratio * 3.0, 2),
        "operating_hours_since_last_service_h": round(service_h, 2),
        "mtbf_h":  round(mtbf, 2),
        "mttr_h":  round(4 + age_ratio * 12, 2),
        "locomotive_availability_pct": round(availability, 2),
        "distance_since_last_overhaul_km": round(overhaul_km, 2),
        "gps_lat": round(43.2389 + (cycle / max_cycle) * (51.1694 - 43.2389), 6),
        "gps_lon": round(76.8897 + (cycle / max_cycle) * (71.4491 - 76.8897), 6),
        "track_gradient_permille": round(math.sin(cycle / 10) * 8, 2),
        "speed_limit_kmh": 120,
        "vertical_dynamics_coefficient": round(0.45 + age_ratio * 0.75, 2),
        "frame_force_kn": round(120 + age_ratio * 220, 2),
        "rail_surface_state": "oily" if rul_pct < 15 else ("wet" if rul_pct < 40 else "clean"),
        "metadata": {
            "source": "nasa_cmapss",
            "engine_unit": unit_id,
            "cycle": cycle,
            "rul_pct": round(rul_pct, 2),
            "delta_hours": 30 / 3600,
        },
    }
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic C-MAPSS demo data (no download required)
# ─────────────────────────────────────────────────────────────────────────────

def _generate_synthetic_cmapss(n_engines: int = 4, cycles_per_engine: int = 80) -> dict[int, list[list[float]]]:
    """
    Generate a small synthetic C-MAPSS-like dataset that mimics FD001 degradation
    patterns.  This is used when --demo is passed so judges can run the adapter
    without downloading the real dataset.

    Degradation model:
      • Sensors start at nominal values and drift linearly + noise toward failure.
      • 2 engines are healthy (max_cycle = 150), 2 are degraded (max_cycle = 80).
    """
    rng = random.Random(42)
    engines: dict[int, list[list[float]]] = {}

    # (nominal_T30, nominal_T50, nominal_P30, nominal_Nf, nominal_Nc,
    #  nominal_Ps30, nominal_phi, nominal_NRc, nominal_BPR, nominal_W31, nominal_W32)
    #  Typical FD001 ranges from NASA documentation
    NOM = [1590, 1400, 1415, 2388, 9046, 549, 2388, 8138, 8.4219, 14.62, 8.4008]
    DEGRADE = [15, 40, 5, -25, -50, 10, 25, -80, -0.3, 2.0, 1.5]  # drift at failure

    for engine_id in range(1, n_engines + 1):
        is_degraded = engine_id % 2 == 0
        max_cyc = cycles_per_engine if is_degraded else int(cycles_per_engine * 1.8)
        rows: list[list[float]] = []
        for cycle in range(1, max_cyc + 1):
            ratio = cycle / max_cyc
            # Operating conditions (3 columns — kept constant per engine)
            op = [rng.uniform(-0.001, 0.001), rng.uniform(-0.0003, 0.0003), 100.0]
            # 21 sensor values
            sensors: list[float] = []
            for i in range(21):
                if i in (S3, S4, S7, S8, S9, S11, S12, S14, S15, S20, S21):
                    j = [S3, S4, S7, S8, S9, S11, S12, S14, S15, S20, S21].index(i)
                    val = NOM[j] + DEGRADE[j] * (ratio ** 1.5) + rng.gauss(0, abs(NOM[j]) * 0.005)
                    sensors.append(round(val, 4))
                else:
                    sensors.append(round(rng.gauss(500, 5), 4))  # unmapped sensor noise

            row = [float(engine_id), float(cycle)] + op + sensors
            rows.append(row)
        engines[engine_id] = rows

    return engines


# ─────────────────────────────────────────────────────────────────────────────
# Inline HI computation (mirrors health_engine.py exactly)
# ─────────────────────────────────────────────────────────────────────────────

def _clamp_hi(v, lo, hi):
    return max(lo, min(hi, v))


def _hib(val, soft, hard, w):
    if val <= soft:
        return 0.0
    return w * _clamp_hi((val - soft) / max(hard - soft, 1e-6), 0.0, 1.8)


def _lib(val, soft, hard, w):
    if val >= soft:
        return 0.0
    return w * _clamp_hi((soft - val) / max(soft - hard, 1e-6), 0.0, 1.8)


def _compute_hi(p: dict, prev: float | None) -> tuple[float, str, str]:
    M_ld = sum([
        _hib(p["speed_kmh"] / max(p["speed_limit_kmh"], 1), 0.75, 1.0, 0.09),
        _hib(abs(p["acceleration_mps2"]), 1.0, 2.0, 0.07),
        _hib(p["tractive_effort_kn"], 250, 400, 0.10),
        _hib(p.get("fuel_consumption_lph") or 0, 300, 600, 0.08),
        _hib(abs(p["track_gradient_permille"]), 4, 10, 0.05),
    ])
    M_h = sum([
        _hib(p["wheel_slip_ratio_pct"], 2.5, 6, 0.12),
        _lib(p["adhesion_coefficient"], 0.18, 0.10, 0.08),
        _hib(p["engine_oil_temperature_c"], 100, 118, 0.12),
        _hib(p["coolant_temperature_c"], 88, 102, 0.10),
        _lib(p["engine_oil_pressure_mpa"], 0.35, 0.22, 0.08),
        _hib(p["exhaust_gas_temperature_c"], 580, 670, 0.08),
        _hib(p["traction_motor_winding_temp_c"], 120, 160, 0.11),
        _hib(p["vibration_amplitude_mms"], 12, 28, 0.13),
        _hib(p["vertical_dynamics_coefficient"], 0.8, 1.2, 0.05),
        _hib(p["frame_force_kn"], 220, 340, 0.06),
        _hib(p["turbocharger_rpm"], 62000, 78000, 0.06),
        _hib(p["ambient_temperature_c"], 38, 48, 0.04),
    ])
    M_r = sum([
        _hib(float(p["active_error_codes"]), 1, 4, 0.10),
        _hib(p["error_code_frequency_per_hour"], 1.0, 3.5, 0.08),
        _hib(p["operating_hours_since_last_service_h"], 1200, 2200, 0.08),
        _lib(p["mtbf_h"], 1800, 1200, 0.06),
        _hib(p["mttr_h"], 8, 16, 0.05),
        _lib(p["locomotive_availability_pct"], 92, 80, 0.06),
        _hib(p["distance_since_last_overhaul_km"], 40000, 90000, 0.07),
        _lib(p["main_reservoir_pressure_mpa"], 0.72, 0.60, 0.09),
        _lib(p["brake_pad_wear_pct_remaining"], 35, 20, 0.08),
        _hib(p["solenoid_valve_residual_signal_mv"], 180, 320, 0.05),
        _lib(p["battery_voltage_v"], 100, 92, 0.05),
        _lib(p["compressor_discharge_pressure_mpa"], 0.65, 0.52, 0.05),
    ])
    beta = 0.22
    dh = p.get("metadata", {}).get("delta_hours", 1 / 60)
    formula = 100 * math.exp(-(M_ld * beta * dh)) * math.exp(-(M_h + M_r))
    if prev is None:
        score = formula
    elif formula <= prev:
        score = formula
    else:
        score = min(100.0, prev + min(2.0, (formula - prev) * 0.25))
    score = _clamp_hi(score, 0.0, 100.0)
    if score >= 85:
        return round(score, 2), "A", "Normal"
    elif score >= 70:
        return round(score, 2), "B", "Advisory"
    elif score >= 50:
        return round(score, 2), "C", "Caution"
    elif score >= 30:
        return round(score, 2), "D", "Warning"
    else:
        return round(score, 2), "E", "Critical"


# ─────────────────────────────────────────────────────────────────────────────
# DB seeding
# ─────────────────────────────────────────────────────────────────────────────

INIT_SQL = """
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


def seed_from_engines(
    engines: dict[int, list[list[float]]],
    db_path: Path,
    max_engines: int = 4,
) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(INIT_SQL)

    base_ts = datetime.now(UTC) - timedelta(hours=max_engines * 3)
    total_events = 0

    for engine_unit, rows in list(engines.items())[:max_engines]:
        loco_id = f"CMAPSS-{engine_unit:03d}"
        max_cycle = int(rows[-1][COL_CYCLE])
        now_str = datetime.now(UTC).isoformat()
        conn.execute(
            "INSERT INTO locomotives VALUES (?,?,?,?) ON CONFLICT(locomotive_id) DO UPDATE SET updated_at=excluded.updated_at",
            (loco_id, "TE33A", now_str, now_str),
        )

        prev_score: float | None = None
        trend: list[float] = []

        print(f"  Seeding {loco_id} — {len(rows)} cycles, max_cycle={max_cycle}")

        for i, row in enumerate(rows):
            cycle = int(row[COL_CYCLE])
            ts = base_ts + timedelta(seconds=i * 30)
            payload = row_to_telemetry(row, engine_unit, loco_id, cycle, max_cycle, ts, prev_score)
            ts_str = ts.isoformat()

            score, grade, band = _compute_hi(payload, prev_score)
            trend.append(score)
            if len(trend) > 120:
                trend = trend[-120:]
            prev_score = score

            health_json = json.dumps({
                "locomotive_id": loco_id,
                "timestamp": ts_str,
                "score": score,
                "grade": grade,
                "band": band,
                "load_modifier": 0.0,
                "health_modifier": 0.0,
                "reliability_modifier": 0.0,
                "formula_score": score,
                "trend": trend[-60:],
                "factors": [],
            })
            event_id = str(uuid4())
            conn.execute(
                "INSERT OR IGNORE INTO telemetry_events VALUES (?,?,?,?,?,?,?,?)",
                (event_id, loco_id, "TE33A", ts_str, score, grade,
                 json.dumps(payload), health_json),
            )
            total_events += 1

    conn.commit()
    conn.close()
    print(f"\nNASA C-MAPSS seed complete: {total_events} events → {db_path}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="NASA C-MAPSS → Locomotive Digital Twin adapter."
    )
    default_db = str(Path(__file__).resolve().parents[1] / "backend" / "data" / "digital_twin.db")
    parser.add_argument("--file", help="Path to C-MAPSS train_FDxxx.txt file.")
    parser.add_argument("--demo", action="store_true", help="Use built-in synthetic C-MAPSS demo data.")
    parser.add_argument("--db", default=default_db, help="SQLite DB path.")
    parser.add_argument("--engines", type=int, default=4, help="Max engines to import (default: 4).")
    parser.add_argument("--cycles", type=int, default=80, help="Cycles per engine in demo mode (default: 80).")
    args = parser.parse_args()

    if args.demo:
        print("Generating synthetic C-MAPSS demo dataset...")
        engines = _generate_synthetic_cmapss(n_engines=args.engines, cycles_per_engine=args.cycles)
    elif args.file:
        print(f"Parsing C-MAPSS file: {args.file}")
        engines = parse_cmapss_file(Path(args.file))
    else:
        parser.error("Provide --file <path> or --demo")
        return

    print(f"Loaded {len(engines)} engine(s). Seeding into {args.db}...")
    seed_from_engines(engines, Path(args.db), max_engines=args.engines)


if __name__ == "__main__":
    main()
