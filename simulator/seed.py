"""
Seed script: generates synthetic telemetry dataset and writes it directly
into the SQLite database (no HTTP server required). Runs on Python 3.8+.

Usage:
    python3 simulator/seed.py
    python3 simulator/seed.py --events 500 --db backend/data/digital_twin.db

Generates:
    - KZ8A-001: nominal electric (Almaty -> Astana)
    - KZ8A-002: degraded electric (heat buildup + brake wear)
    - TE33A-009: nominal diesel-electric (Astana -> Almaty)

Data strategy: GPS positions are real KTZ Almaty-Astana corridor waypoints.
All telemetry values are synthetic (per instructor guidance).
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

# ---------------------------------------------------------------------------
# Real KTZ Almaty-Astana corridor waypoints (~1,200 km)
# ---------------------------------------------------------------------------
ALMATY_ASTANA_CORRIDOR = [
    (43.2389, 76.8897),   # Almaty-1
    (43.3012, 76.7245),
    (43.4567, 76.2134),   # Kapshagai
    (43.5890, 75.5423),
    (43.6012, 73.7561),   # Shu junction
    (44.0523, 72.8734),
    (45.2345, 71.4312),
    (47.1234, 70.2345),
    (49.8047, 73.0856),   # Karaganda
    (50.2834, 72.0912),
    (50.9234, 71.6234),
    (51.1694, 71.4491),   # Astana
]
ASTANA_ALMATY_CORRIDOR = list(reversed(ALMATY_ASTANA_CORRIDOR))
CORRIDOR_BY_TYPE = {"KZ8A": ALMATY_ASTANA_CORRIDOR, "TE33A": ASTANA_ALMATY_CORRIDOR}


def _interpolate(corridor, tick, total=400):
    progress = (tick % total) / total
    n = len(corridor) - 1
    exact = progress * n
    idx = int(exact)
    frac = exact - idx
    if idx >= n:
        return corridor[-1]
    lat = corridor[idx][0] + (corridor[idx + 1][0] - corridor[idx][0]) * frac
    lon = corridor[idx][1] + (corridor[idx + 1][1] - corridor[idx][1]) * frac
    return (round(lat, 6), round(lon, 6))


# ---------------------------------------------------------------------------
# Inline HI engine (simplified, matches backend logic)
# ---------------------------------------------------------------------------
def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _high_is_bad(value, soft, hard, weight):
    if value <= soft:
        return 0.0
    span = max(hard - soft, 1e-6)
    return weight * _clamp((value - soft) / span, 0.0, 1.8)


def _low_is_bad(value, soft, hard, weight):
    if value >= soft:
        return 0.0
    span = max(soft - hard, 1e-6)
    return weight * _clamp((soft - value) / span, 0.0, 1.8)


def compute_hi(payload, loco_type, previous_score=None):
    p = payload
    M_ld = sum([
        _high_is_bad(p["speed_kmh"] / max(p["speed_limit_kmh"], 1), 0.75, 1.0, 0.09),
        _high_is_bad(abs(p["acceleration_mps2"]), 1.0, 2.0, 0.07),
        _high_is_bad(p["tractive_effort_kn"], 250, 400, 0.10),
        _high_is_bad(p.get("fuel_consumption_lph") or p.get("electric_power_kw") or 0, 300, 600 if loco_type == "TE33A" else 7000, 0.08),
        _high_is_bad(abs(p["track_gradient_permille"]), 4, 10, 0.05),
    ])
    M_h = sum([
        _high_is_bad(p["wheel_slip_ratio_pct"], 2.5, 6, 0.12),
        _low_is_bad(p["adhesion_coefficient"], 0.18, 0.10, 0.08),
        _high_is_bad(p["engine_oil_temperature_c"], 100, 118, 0.12),
        _high_is_bad(p["coolant_temperature_c"], 88, 102, 0.10),
        _low_is_bad(p["engine_oil_pressure_mpa"], 0.35, 0.22, 0.08),
        _high_is_bad(p["exhaust_gas_temperature_c"], 580, 670, 0.08),
        _high_is_bad(p["traction_motor_winding_temp_c"], 120, 160, 0.11),
        _high_is_bad(p.get("transformer_oil_temp_c") or 40, 70, 95, 0.08),
        _high_is_bad(p["vibration_amplitude_mms"], 12, 28, 0.13),
        _high_is_bad(p["vertical_dynamics_coefficient"], 0.8, 1.2, 0.05),
        _high_is_bad(p["frame_force_kn"], 220, 340, 0.06),
        # New sensors synced with health_engine.py
        _high_is_bad(p["turbocharger_rpm"], 62000, 78000, 0.06),
        _high_is_bad(p["ambient_temperature_c"], 38, 48, 0.04),
        _low_is_bad(p["catenary_voltage_kv"] if loco_type == "KZ8A" and p.get("catenary_voltage_kv") else 25.0, 20.0, 19.0, 0.07) if loco_type == "KZ8A" else 0.0,
    ])
    M_r = sum([
        _high_is_bad(float(p["active_error_codes"]), 1, 4, 0.10),
        _high_is_bad(p["error_code_frequency_per_hour"], 1.0, 3.5, 0.08),
        _high_is_bad(p["operating_hours_since_last_service_h"], 1200, 2200, 0.08),
        _low_is_bad(p["mtbf_h"], 1800, 1200, 0.06),
        _high_is_bad(p["mttr_h"], 8, 16, 0.05),
        _low_is_bad(p["locomotive_availability_pct"], 92, 80, 0.06),
        _high_is_bad(p["distance_since_last_overhaul_km"], 40000, 90000, 0.07),
        _low_is_bad(p["main_reservoir_pressure_mpa"], 0.72, 0.60, 0.09),
        _low_is_bad(p["brake_pad_wear_pct_remaining"], 35, 20, 0.08),
        _high_is_bad(p["solenoid_valve_residual_signal_mv"], 180, 320, 0.05),
        # New sensors synced with health_engine.py
        _low_is_bad(p["battery_voltage_v"], 100, 92, 0.05),
        _low_is_bad(p["compressor_discharge_pressure_mpa"], 0.65, 0.52, 0.05),
    ])

    beta = 0.22 if loco_type == "TE33A" else 0.18
    delta_h = p.get("metadata", {}).get("delta_hours", 1 / 60)
    formula = 100 * math.exp(-(M_ld * beta * delta_h)) * math.exp(-(M_h + M_r))

    if previous_score is None:
        score = formula
    elif formula <= previous_score:
        score = formula
    else:
        score = min(100.0, previous_score + min(2.0, (formula - previous_score) * 0.25))

    score = _clamp(score, 0.0, 100.0)

    if score >= 85:
        grade, band = "A", "Normal"
    elif score >= 70:
        grade, band = "B", "Advisory"
    elif score >= 50:
        grade, band = "C", "Caution"
    elif score >= 30:
        grade, band = "D", "Warning"
    else:
        grade, band = "E", "Critical"

    return round(score, 2), grade, band, round(M_ld, 4), round(M_h, 4), round(M_r, 4)


# ---------------------------------------------------------------------------
# Alert recommendations (must match alerts.py RECOMMENDATIONS dict)
# ---------------------------------------------------------------------------
RECOMMENDATIONS = {
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


# ---------------------------------------------------------------------------
# Alert logic (simplified)
# ---------------------------------------------------------------------------
def compute_alerts(loco_id, payload, health_score, health_grade, ts_str):
    alerts = []
    ts = ts_str

    def emit(code, severity, message, source, details):
        alerts.append({
            "alert_id": str(uuid4()),
            "locomotive_id": loco_id,
            "timestamp": ts,
            "severity": severity,
            "code": code,
            "message": message,
            "status": "active",
            "source": source,
            "details_json": json.dumps(details),
            "recommendation": RECOMMENDATIONS.get(code, ""),
        })

    if payload["wheel_slip_ratio_pct"] > 3:
        emit("WHEEL_SLIP", "critical" if payload["wheel_slip_ratio_pct"] >= 6 else "warning",
             "Wheel slip above 3%", "traction", {"value": payload["wheel_slip_ratio_pct"]})
    if payload["engine_oil_temperature_c"] > 110:
        emit("OIL_TEMP_HIGH", "critical" if payload["engine_oil_temperature_c"] > 120 else "warning",
             "Engine oil temperature above safe threshold", "engine", {"value": payload["engine_oil_temperature_c"]})
    if payload["main_reservoir_pressure_mpa"] < 0.7:
        emit("BRAKE_PRESSURE_LOW", "critical" if payload["main_reservoir_pressure_mpa"] < 0.62 else "warning",
             "Main reservoir pressure below safe range", "brakes", {"value": payload["main_reservoir_pressure_mpa"]})
    if payload["brake_pad_wear_pct_remaining"] < 25:
        emit("BRAKE_PAD_LOW", "warning", "Brake pad life below threshold", "brakes",
             {"remaining_pct": payload["brake_pad_wear_pct_remaining"]})
    if payload["active_error_codes"] > 0:
        emit("ERROR_CODES_ACTIVE", "warning", "Active onboard error codes", "control",
             {"count": payload["active_error_codes"]})
    if health_score < 50:
        emit("HEALTH_INDEX_LOW", "critical" if health_score < 30 else "warning",
             f"Health Index degraded to {health_grade} ({health_score})", "health-index",
             {"score": health_score, "grade": health_grade})
    return alerts


# ---------------------------------------------------------------------------
# Telemetry builder
# ---------------------------------------------------------------------------
def build_event(loco_id, loco_type, tick, degraded, ts):
    corridor = CORRIDOR_BY_TYPE[loco_type]
    lat, lon = _interpolate(corridor, tick)
    phase = tick / 8.0

    speed = 80 + math.sin(phase) * 20 + (10 if degraded else 0)
    slip = 1.2 + abs(math.sin(phase * 1.5)) * (5.0 if degraded else 1.1)
    oil_temp = 88 + abs(math.sin(phase * 1.1)) * (35 if degraded else 8)
    coolant = 78 + abs(math.cos(phase * 0.9)) * (24 if degraded else 6)
    vibration = 6 + abs(math.sin(phase * 1.8)) * (22 if degraded else 4)
    reservoir = 0.84 - abs(math.cos(phase * 1.3)) * (0.25 if degraded else 0.05)
    brake_rem = max(10 if degraded else 70, 92 - tick * (0.06 if degraded else 0.01))

    return {
        "locomotive_id": loco_id,
        "locomotive_type": loco_type,
        "timestamp": ts.isoformat(),
        "speed_kmh": round(speed, 2),
        "acceleration_mps2": round(math.sin(phase) * 1.8, 2),
        "tractive_effort_kn": round(250 + abs(math.sin(phase)) * (190 if degraded else 90), 2),
        "wheel_slip_ratio_pct": round(slip, 2),
        "adhesion_coefficient": round(0.26 - (0.14 if degraded else 0.05) * abs(math.sin(phase)), 3),
        "traction_motor_current_a": round(650 + abs(math.sin(phase)) * 420, 2),
        "traction_motor_torque_nm": round(2200 + abs(math.sin(phase)) * 1800, 2),
        "fuel_level_pct": round(60 - tick * 0.02, 2) if loco_type == "TE33A" else None,
        "fuel_consumption_lph": round(220 + abs(math.sin(phase)) * 260, 2) if loco_type == "TE33A" else None,
        "catenary_voltage_kv": round(24.5 + math.sin(phase) * 1.2, 2) if loco_type == "KZ8A" else None,
        "traction_circuit_voltage_v": round(2800 + math.sin(phase) * 280, 2),
        "electric_power_kw": round(4200 + abs(math.cos(phase)) * 2200, 2) if loco_type == "KZ8A" else None,
        "battery_voltage_v": round(112 + math.sin(phase) * 5, 2),
        "auxiliary_power_load_kw": round(45 + abs(math.cos(phase)) * 20, 2),
        "engine_oil_temperature_c": round(oil_temp, 2),
        "coolant_temperature_c": round(coolant, 2),
        "engine_oil_pressure_mpa": round(0.46 - abs(math.sin(phase)) * (0.19 if degraded else 0.05), 3),
        "exhaust_gas_temperature_c": round(440 + abs(math.sin(phase)) * (240 if degraded else 100), 2),
        "turbocharger_rpm": round(27000 + abs(math.cos(phase)) * 18000, 2),
        "compressor_discharge_pressure_mpa": round(0.74 + abs(math.sin(phase)) * 0.08, 3),
        "traction_motor_winding_temp_c": round(86 + abs(math.sin(phase)) * (75 if degraded else 20), 2),
        "transformer_oil_temp_c": round(58 + abs(math.cos(phase)) * (32 if degraded else 12), 2) if loco_type == "KZ8A" else None,
        "vibration_amplitude_mms": round(vibration, 2),
        "ambient_temperature_c": round(-5 + math.sin(phase / 2) * 18, 2),
        "main_reservoir_pressure_mpa": round(reservoir, 3),
        "brake_cylinder_pressure_mpa": round(0.1 + abs(math.sin(phase)) * 0.18, 3),
        "brake_pad_wear_pct_remaining": round(brake_rem, 2),
        "solenoid_valve_residual_signal_mv": round(90 + abs(math.sin(phase)) * (250 if degraded else 80), 2),
        "parking_brake_status": False,
        "active_error_codes": 2 if degraded and tick % 6 == 0 else 0,
        "error_code_frequency_per_hour": round(2.8 if degraded else 0.2, 2),
        "operating_hours_since_last_service_h": 1900 if degraded else 620,
        "mtbf_h": 1180 if degraded else 2300,
        "mttr_h": 14 if degraded else 4,
        "locomotive_availability_pct": 83 if degraded else 97,
        "distance_since_last_overhaul_km": 82000 if degraded else 15000,
        "gps_lat": lat,
        "gps_lon": lon,
        "track_gradient_permille": round(math.sin(phase / 2) * 9, 2),
        "speed_limit_kmh": 120,
        "vertical_dynamics_coefficient": round(0.45 + abs(math.sin(phase)) * (1.1 if degraded else 0.28), 2),
        "frame_force_kn": round(120 + abs(math.cos(phase)) * (270 if degraded else 90), 2),
        "rail_surface_state": random.choice(["wet", "oily", "clean"]) if degraded else random.choice(["clean", "clean", "wet"]),
        "metadata": {"scenario": "degraded" if degraded else "nominal", "seeded": True, "delta_hours": 30 / 3600},
    }


# ---------------------------------------------------------------------------
# Fleet to seed
# ---------------------------------------------------------------------------
DEMO_FLEET = [
    ("KZ8A-001", "KZ8A", False),    # Nominal electric — Almaty -> Astana
    ("KZ8A-002", "KZ8A", True),     # Degraded electric — heat + wear
    ("TE33A-009", "TE33A", False),  # Nominal diesel-electric — Astana -> Almaty
    ("TE33A-010", "TE33A", True),   # Degraded diesel-electric — fuel + brake wear scenario
]

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
    details_json TEXT NOT NULL,
    recommendation TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_alerts_locomotive_time
    ON alerts (locomotive_id, timestamp DESC);
"""


def seed(db_path: Path, events_per_loco: int) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(INIT_SQL)

    base_ts = datetime.now(UTC) - timedelta(seconds=events_per_loco * 30)
    total_events = 0
    total_alerts = 0

    for loco_id, loco_type, degraded in DEMO_FLEET:
        tag = "degraded" if degraded else "nominal"
        print(f"Seeding {loco_id} ({loco_type}, {tag}) — {events_per_loco} events...")
        now_str = datetime.now(UTC).isoformat()
        conn.execute(
            "INSERT INTO locomotives VALUES (?,?,?,?) ON CONFLICT(locomotive_id) DO UPDATE SET updated_at=excluded.updated_at",
            (loco_id, loco_type, now_str, now_str),
        )

        prev_score = None
        trend = []

        for tick in range(events_per_loco):
            ts = base_ts + timedelta(seconds=tick * 30)
            payload = build_event(loco_id, loco_type, tick, degraded, ts)
            ts_str = ts.isoformat()

            score, grade, band, M_ld, M_h, M_r = compute_hi(payload, loco_type, prev_score)
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
                "load_modifier": M_ld,
                "health_modifier": M_h,
                "reliability_modifier": M_r,
                "formula_score": score,
                "trend": trend[-60:],
                "factors": [],
            })

            event_id = str(uuid4())
            conn.execute(
                "INSERT INTO telemetry_events VALUES (?,?,?,?,?,?,?,?)",
                (event_id, loco_id, loco_type, ts_str, score, grade,
                 json.dumps(payload), health_json),
            )

            for alert in compute_alerts(loco_id, payload, score, grade, ts_str):
                conn.execute(
                    "INSERT OR IGNORE INTO alerts VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (alert["alert_id"], loco_id, alert["timestamp"], alert["severity"],
                     alert["code"], alert["message"], alert["status"], alert["source"],
                     alert["details_json"], alert.get("recommendation", "")),
                )
                total_alerts += 1

            total_events += 1

    conn.commit()
    conn.close()

    print(f"\nDone: {total_events} events, {total_alerts} alerts -> {db_path}")
    for loco_id, loco_type, degraded in DEMO_FLEET:
        print(f"  {loco_id} ({loco_type}) — {'degraded' if degraded else 'nominal'} — {events_per_loco} events")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the digital twin SQLite database with synthetic telemetry.")
    default_db = str(Path(__file__).resolve().parents[1] / "backend" / "data" / "digital_twin.db")
    parser.add_argument("--db", default=default_db)
    parser.add_argument("--events", type=int, default=200, help="Events per locomotive (default: 200).")
    args = parser.parse_args()
    seed(Path(args.db), args.events)


if __name__ == "__main__":
    main()
