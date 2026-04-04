from __future__ import annotations

import argparse
import json
import math
import random
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime


BASE_LOCATIONS = {
    "KZ8A": (43.238949, 76.889709),
    "TE33A": (51.169392, 71.449074),
}


def build_event(locomotive_id: str, locomotive_type: str, tick: int, degraded: bool) -> dict[str, object]:
    lat, lon = BASE_LOCATIONS[locomotive_type]
    phase = tick / 8
    speed = 70 + math.sin(phase) * 18 + (12 if degraded else 0)
    slip = 1.2 + abs(math.sin(phase * 1.5)) * (4.6 if degraded else 1.1)
    oil_temp = 88 + abs(math.sin(phase * 1.1)) * (30 if degraded else 8)
    coolant = 78 + abs(math.cos(phase * 0.9)) * (22 if degraded else 6)
    vibration = 6 + abs(math.sin(phase * 1.8)) * (20 if degraded else 4)
    reservoir = 0.84 - abs(math.cos(phase * 1.3)) * (0.23 if degraded else 0.05)
    brake_remaining = max(12 if degraded else 72, 92 - tick * (0.05 if degraded else 0.01))

    payload = {
        "locomotive_id": locomotive_id,
        "locomotive_type": locomotive_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "speed_kmh": round(speed, 2),
        "acceleration_mps2": round(math.sin(phase) * 1.8, 2),
        "tractive_effort_kn": round(250 + abs(math.sin(phase)) * (180 if degraded else 90), 2),
        "wheel_slip_ratio_pct": round(slip, 2),
        "adhesion_coefficient": round(0.26 - (0.13 if degraded else 0.05) * abs(math.sin(phase)), 3),
        "traction_motor_current_a": round(650 + abs(math.sin(phase)) * 420, 2),
        "traction_motor_torque_nm": round(2200 + abs(math.sin(phase)) * 1800, 2),
        "fuel_level_pct": round(58 - tick * 0.02, 2) if locomotive_type == "TE33A" else None,
        "fuel_consumption_lph": round(210 + abs(math.sin(phase)) * 260, 2) if locomotive_type == "TE33A" else None,
        "catenary_voltage_kv": round(24.5 + math.sin(phase) * 1.2, 2) if locomotive_type == "KZ8A" else None,
        "traction_circuit_voltage_v": round(2800 + math.sin(phase) * 280, 2),
        "electric_power_kw": round(4100 + abs(math.cos(phase)) * 2200, 2) if locomotive_type == "KZ8A" else None,
        "battery_voltage_v": round(112 + math.sin(phase) * 5, 2),
        "auxiliary_power_load_kw": round(45 + abs(math.cos(phase)) * 20, 2),
        "engine_oil_temperature_c": round(oil_temp, 2),
        "coolant_temperature_c": round(coolant, 2),
        "engine_oil_pressure_mpa": round(0.46 - abs(math.sin(phase)) * (0.18 if degraded else 0.05), 3),
        "exhaust_gas_temperature_c": round(440 + abs(math.sin(phase)) * (230 if degraded else 100), 2),
        "turbocharger_rpm": round(27000 + abs(math.cos(phase)) * 18000, 2),
        "compressor_discharge_pressure_mpa": round(0.74 + abs(math.sin(phase)) * 0.08, 3),
        "traction_motor_winding_temp_c": round(86 + abs(math.sin(phase)) * (72 if degraded else 20), 2),
        "transformer_oil_temp_c": round(58 + abs(math.cos(phase)) * (30 if degraded else 12), 2)
        if locomotive_type == "KZ8A"
        else None,
        "vibration_amplitude_mms": round(vibration, 2),
        "ambient_temperature_c": round(-8 + math.sin(phase / 2) * 20, 2),
        "main_reservoir_pressure_mpa": round(reservoir, 3),
        "brake_cylinder_pressure_mpa": round(0.1 + abs(math.sin(phase)) * 0.18, 3),
        "brake_pad_wear_pct_remaining": round(brake_remaining, 2),
        "solenoid_valve_residual_signal_mv": round(90 + abs(math.sin(phase)) * (240 if degraded else 80), 2),
        "parking_brake_status": False,
        "active_error_codes": 2 if degraded and tick % 6 == 0 else 0,
        "error_code_frequency_per_hour": round(2.8 if degraded else 0.2, 2),
        "operating_hours_since_last_service_h": 1900 if degraded else 620,
        "mtbf_h": 1180 if degraded else 2300,
        "mttr_h": 14 if degraded else 4,
        "locomotive_availability_pct": 83 if degraded else 97,
        "distance_since_last_overhaul_km": 82000 if degraded else 15000,
        "gps_lat": round(lat + tick * 0.0008, 6),
        "gps_lon": round(lon + tick * 0.0011, 6),
        "track_gradient_permille": round(math.sin(phase / 2) * 9, 2),
        "speed_limit_kmh": 120,
        "vertical_dynamics_coefficient": round(0.45 + abs(math.sin(phase)) * (1.05 if degraded else 0.28), 2),
        "frame_force_kn": round(120 + abs(math.cos(phase)) * (260 if degraded else 90), 2),
        "rail_surface_state": random.choice(["wet", "oily", "clean"]) if degraded else random.choice(["clean", "clean", "wet"]),
        "metadata": {"scenario": "degraded" if degraded else "normal"},
    }
    return payload


def post_event(base_url: str, token: str, payload: dict[str, object]) -> None:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/telemetry",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()


def login(base_url: str, username: str, password: str) -> str:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/auth/login",
        data=json.dumps({"username": username, "password": password}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        body = json.loads(response.read().decode())
        return body["access_token"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Telemetry simulator for the locomotive digital twin.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin123")
    parser.add_argument("--locomotive-id", default="KZ8A-001")
    parser.add_argument("--locomotive-type", choices=["KZ8A", "TE33A"], default="KZ8A")
    parser.add_argument("--interval", type=float, default=0.75)
    parser.add_argument("--events", type=int, default=0, help="0 means run forever")
    parser.add_argument("--spike-mode", action="store_true")
    parser.add_argument("--degraded", action="store_true")
    args = parser.parse_args()

    token = login(args.base_url, args.username, args.password)
    sent = 0
    batch_size = 10 if args.spike_mode else 1

    while args.events == 0 or sent < args.events:
        for _ in range(batch_size):
            degraded = args.degraded or (args.spike_mode and sent % 15 > 8)
            payload = build_event(args.locomotive_id, args.locomotive_type, sent, degraded)
            try:
                post_event(args.base_url, token, payload)
            except urllib.error.URLError as exc:
                print(f"failed to send event {sent}: {exc}")
                time.sleep(2)
                break
            sent += 1
            print(f"sent event {sent} for {args.locomotive_id} degraded={degraded}")
            if args.events and sent >= args.events:
                break
        time.sleep(max(args.interval, 0.05))


if __name__ == "__main__":
    main()
