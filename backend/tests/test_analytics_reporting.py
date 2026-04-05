from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.schemas.telemetry import TelemetryEvent
from app.services.alerts import AlertEngine
from app.services.health_engine import HealthIndexEngine
from app.storage.database import Database


class AnalyticsReportingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "analytics.db"
        self.db = Database(f"sqlite:///{db_path}")
        self.health_engine = HealthIndexEngine()
        self.alert_engine = AlertEngine()

        base_time = datetime(2026, 4, 4, 10, 0, tzinfo=UTC)
        self._save_event(
            event_id="evt-1",
            payload=self._event(
                timestamp=base_time,
                locomotive_id="KZ8A-001",
                locomotive_type="KZ8A",
                speed_kmh=82,
                wheel_slip_ratio_pct=1.4,
                engine_oil_temperature_c=90,
                vibration_amplitude_mms=7,
                main_reservoir_pressure_mpa=0.82,
            ),
        )
        self._save_event(
            event_id="evt-2",
            payload=self._event(
                timestamp=base_time + timedelta(hours=1),
                locomotive_id="TE33A-007",
                locomotive_type="TE33A",
                speed_kmh=97,
                wheel_slip_ratio_pct=5.8,
                engine_oil_temperature_c=120,
                coolant_temperature_c=101,
                vibration_amplitude_mms=24,
                main_reservoir_pressure_mpa=0.62,
                active_error_codes=2,
                error_code_frequency_per_hour=3.1,
                brake_pad_wear_pct_remaining=21,
                locomotive_availability_pct=82,
            ),
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _event(self, **overrides) -> TelemetryEvent:
        payload = {
            "locomotive_id": "KZ8A-001",
            "locomotive_type": "KZ8A",
            "timestamp": datetime.now(UTC),
            "speed_kmh": 70,
            "acceleration_mps2": 0.6,
            "tractive_effort_kn": 220,
            "wheel_slip_ratio_pct": 1.2,
            "adhesion_coefficient": 0.26,
            "traction_motor_current_a": 620,
            "traction_motor_torque_nm": 2300,
            "fuel_level_pct": None,
            "fuel_consumption_lph": None,
            "catenary_voltage_kv": 24.8,
            "traction_circuit_voltage_v": 2800,
            "electric_power_kw": 4600,
            "battery_voltage_v": 113,
            "auxiliary_power_load_kw": 45,
            "engine_oil_temperature_c": 88,
            "coolant_temperature_c": 78,
            "engine_oil_pressure_mpa": 0.47,
            "exhaust_gas_temperature_c": 470,
            "turbocharger_rpm": 27000,
            "compressor_discharge_pressure_mpa": 0.77,
            "traction_motor_winding_temp_c": 86,
            "transformer_oil_temp_c": 60,
            "vibration_amplitude_mms": 6,
            "ambient_temperature_c": 15,
            "main_reservoir_pressure_mpa": 0.83,
            "brake_cylinder_pressure_mpa": 0.11,
            "brake_pad_wear_pct_remaining": 88,
            "solenoid_valve_residual_signal_mv": 85,
            "parking_brake_status": False,
            "active_error_codes": 0,
            "error_code_frequency_per_hour": 0.1,
            "operating_hours_since_last_service_h": 500,
            "mtbf_h": 2300,
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

    def _save_event(self, event_id: str, payload: TelemetryEvent) -> None:
        self.db.upsert_locomotive(payload)
        health = self.health_engine.evaluate(payload)
        alerts = self.alert_engine.evaluate(payload, health)
        self.db.save_event(event_id, payload, health, alerts)

    def test_kpis_and_breakdowns_return_rows(self) -> None:
        kpis = self.db.analytics_kpis()
        self.assertEqual(len(kpis), 1)
        self.assertEqual(kpis[0].events, 2)
        self.assertGreaterEqual(kpis[0].alerts_total, 1)

        breakdown = self.db.analytics_breakdown(dimension="locomotive_type")
        values = {row.dimension_value for row in breakdown}
        self.assertEqual(values, {"KZ8A", "TE33A"})

    def test_trends_and_factor_breakdown_capture_degraded_behavior(self) -> None:
        trends = self.db.analytics_trends(bucket="hour")
        self.assertEqual(len(trends), 2)

        factors = self.db.analytics_factor_breakdown()
        self.assertTrue(any(row.factor_category == "health" for row in factors))

        event_rows = self.db.analytics_reporting_rows()
        degraded = next(row for row in event_rows if row.locomotive_id == "TE33A-007")
        self.assertGreater(degraded.alert_count, 0)
        self.assertNotEqual(degraded.top_factor_label, "Nominal")


if __name__ == "__main__":
    unittest.main()
