from __future__ import annotations

import unittest
from datetime import UTC, datetime

from app.schemas.telemetry import TelemetryEvent
from app.services.health_engine import HealthIndexEngine


class HealthIndexEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = HealthIndexEngine()

    def _build_event(self, **overrides: float | str | bool | dict[str, object]) -> TelemetryEvent:
        payload = {
            "locomotive_id": "TE33A-001",
            "locomotive_type": "TE33A",
            "timestamp": datetime.now(UTC),
            "speed_kmh": 72,
            "acceleration_mps2": 0.8,
            "tractive_effort_kn": 230,
            "wheel_slip_ratio_pct": 1.1,
            "adhesion_coefficient": 0.27,
            "traction_motor_current_a": 650,
            "traction_motor_torque_nm": 2400,
            "fuel_level_pct": 68,
            "fuel_consumption_lph": 220,
            "battery_voltage_v": 113,
            "auxiliary_power_load_kw": 42,
            "engine_oil_temperature_c": 89,
            "coolant_temperature_c": 78,
            "engine_oil_pressure_mpa": 0.47,
            "exhaust_gas_temperature_c": 470,
            "turbocharger_rpm": 28000,
            "compressor_discharge_pressure_mpa": 0.78,
            "traction_motor_winding_temp_c": 82,
            "vibration_amplitude_mms": 7,
            "ambient_temperature_c": 18,
            "main_reservoir_pressure_mpa": 0.83,
            "brake_cylinder_pressure_mpa": 0.11,
            "brake_pad_wear_pct_remaining": 88,
            "solenoid_valve_residual_signal_mv": 90,
            "parking_brake_status": False,
            "active_error_codes": 0,
            "error_code_frequency_per_hour": 0.1,
            "operating_hours_since_last_service_h": 420,
            "mtbf_h": 2400,
            "mttr_h": 4,
            "locomotive_availability_pct": 97,
            "distance_since_last_overhaul_km": 14000,
            "gps_lat": 43.238949,
            "gps_lon": 76.889709,
            "track_gradient_permille": 2,
            "speed_limit_kmh": 120,
            "vertical_dynamics_coefficient": 0.42,
            "frame_force_kn": 110,
            "rail_surface_state": "clean",
            "metadata": {"delta_hours": 1 / 60},
        }
        payload.update(overrides)
        return TelemetryEvent(**payload)

    def test_nominal_operation_stays_high(self) -> None:
        snapshot = self.engine.evaluate(self._build_event())
        self.assertGreaterEqual(snapshot.score, 90)
        self.assertEqual(snapshot.grade, "A")

    def test_degraded_operation_reduces_score(self) -> None:
        degraded = self._build_event(
            wheel_slip_ratio_pct=6.4,
            engine_oil_temperature_c=122,
            coolant_temperature_c=101,
            traction_motor_winding_temp_c=158,
            vibration_amplitude_mms=26,
            main_reservoir_pressure_mpa=0.61,
            brake_pad_wear_pct_remaining=18,
            active_error_codes=3,
            error_code_frequency_per_hour=3.6,
            locomotive_availability_pct=79,
            distance_since_last_overhaul_km=91000,
        )
        snapshot = self.engine.evaluate(degraded)
        self.assertLess(snapshot.score, 50)
        self.assertIn(snapshot.grade, {"D", "E"})
        self.assertTrue(snapshot.factors)


if __name__ == "__main__":
    unittest.main()
