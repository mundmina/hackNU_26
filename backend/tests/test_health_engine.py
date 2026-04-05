from __future__ import annotations

import unittest
from datetime import UTC, datetime

from app.core.evaluation import (
    compute_auroc,
    compute_full_report,
    compute_mare,
    compute_monotonicity,
    compute_precision_recall_f1,
    compute_rmse,
    compute_trendability,
)
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


    def test_kz8a_nominal_stays_high(self) -> None:
        """KZ8A electric locomotive with nominal catenary voltage should score A."""
        snapshot = self.engine.evaluate(
            self._build_event(
                locomotive_id="KZ8A-001",
                locomotive_type="KZ8A",
                catenary_voltage_kv=24.5,
                transformer_oil_temp_c=60.0,
            )
        )
        self.assertGreaterEqual(snapshot.score, 88)
        self.assertEqual(snapshot.grade, "A")

    def test_monotonicity_under_sustained_stress(self) -> None:
        """HI must decrease (or stay flat) under sustained degradation — plan §8.1 Monotonicity."""
        scores: list[float] = []
        previous: float | None = None
        base = self._build_event(
            wheel_slip_ratio_pct=5.5,
            engine_oil_temperature_c=115,
            traction_motor_winding_temp_c=145,
            vibration_amplitude_mms=24,
            active_error_codes=3,
            error_code_frequency_per_hour=3.2,
            locomotive_availability_pct=81,
            distance_since_last_overhaul_km=85000,
        )
        for _ in range(20):
            snap = self.engine.evaluate(base, previous_health=previous)
            scores.append(snap.score)
            previous = snap.score

        # Scores should be non-increasing (monotonically degrading)
        for i in range(1, len(scores)):
            self.assertLessEqual(
                scores[i],
                scores[i - 1] + 0.01,  # tiny tolerance for float rounding
                msg=f"Score rose unexpectedly at step {i}: {scores[i - 1]:.2f} -> {scores[i]:.2f}",
            )

    def test_mare_within_acceptable_bound(self) -> None:
        """MARE (Mean Absolute Relative Error) between formula score and smoothed score
        should be small for steady-state conditions — plan §8.1 MARE."""
        scores = []
        formula_scores = []
        previous: float | None = None
        normal_event = self._build_event()

        for _ in range(30):
            snap = self.engine.evaluate(normal_event, previous_health=previous)
            scores.append(snap.score)
            formula_scores.append(snap.formula_score)
            previous = snap.score

        # MARE = mean(|score - formula| / max(formula, 1))
        mare = sum(
            abs(s - f) / max(f, 1.0) for s, f in zip(scores, formula_scores)
        ) / len(scores)
        self.assertLess(mare, 0.05, msg=f"MARE too high: {mare:.4f} — smoothing diverged from formula")

    def test_grade_boundaries_correct(self) -> None:
        """Verify all 5 grade bands map to correct letter grades — plan §4.2."""
        boundaries = [
            (90.0, "A"),
            (77.0, "B"),
            (60.0, "C"),
            (40.0, "D"),
            (15.0, "E"),
        ]
        for score, expected_grade in boundaries:
            _, grade = self.engine._classify(score)  # type: ignore[attr-defined]
            self.assertEqual(grade, expected_grade, msg=f"Score {score} should be {expected_grade}")

    def test_factor_breakdown_populated_when_degraded(self) -> None:
        """Factor breakdown list must be non-empty for degraded state — plan §4.2."""
        degraded = self._build_event(
            wheel_slip_ratio_pct=7.0,
            engine_oil_temperature_c=124,
            vibration_amplitude_mms=30,
        )
        snap = self.engine.evaluate(degraded)
        self.assertTrue(snap.factors, "Expected non-empty factor list for degraded state")
        self.assertLessEqual(len(snap.factors), 6, "Factor list must be capped at 6")

    def test_new_sensors_contribute_to_modifiers(self) -> None:
        """Turbocharger overspeed and low battery should increase health/reliability modifiers."""
        baseline = self.engine.evaluate(self._build_event())
        stressed = self.engine.evaluate(
            self._build_event(
                turbocharger_rpm=75000,   # above soft limit 62000
                battery_voltage_v=91,     # below soft limit 100
                compressor_discharge_pressure_mpa=0.50,  # below soft limit 0.65
            )
        )
        self.assertGreater(
            baseline.score, stressed.score,
            msg="New sensors (turbocharger, battery, compressor) should reduce HI under stress",
        )


class EvaluationMetricsTests(unittest.TestCase):
    """§8.1 — Evaluation metric implementations."""

    # ── MARE ────────────────────────────────────────────────────────────────
    def test_mare_perfect(self) -> None:
        self.assertAlmostEqual(compute_mare([80, 70, 60], [80, 70, 60]), 0.0)

    def test_mare_known_value(self) -> None:
        # |90-100|/100 = 0.1, |70-80|/80 = 0.125 → mean = 0.1125
        result = compute_mare([90.0, 70.0], [100.0, 80.0])
        self.assertAlmostEqual(result, 0.1125, places=4)

    def test_mare_empty(self) -> None:
        self.assertEqual(compute_mare([], []), 0.0)

    # ── RMSE ────────────────────────────────────────────────────────────────
    def test_rmse_perfect(self) -> None:
        self.assertAlmostEqual(compute_rmse([50, 60, 70], [50, 60, 70]), 0.0)

    def test_rmse_known_value(self) -> None:
        # errors: 10, 10 → RMSE = 10
        self.assertAlmostEqual(compute_rmse([90.0, 70.0], [100.0, 80.0]), 10.0, places=4)

    # ── AUROC ───────────────────────────────────────────────────────────────
    def test_auroc_perfect_classifier(self) -> None:
        # All degraded engines have lower HI → perfect separation
        scores = [90, 85, 80, 30, 25, 20]
        labels = [0,  0,  0,  1,  1,  1]
        auroc = compute_auroc(scores, labels)
        self.assertGreaterEqual(auroc, 0.95, msg=f"AUROC = {auroc:.3f}, expected ≥ 0.95")

    def test_auroc_random_classifier(self) -> None:
        # Random ordering — AUROC should be near 0.5
        import random as _r
        rng = _r.Random(0)
        scores = [rng.uniform(20, 100) for _ in range(100)]
        labels = [rng.choice([0, 1]) for _ in range(100)]
        auroc = compute_auroc(scores, labels)
        self.assertGreater(auroc, 0.2)
        self.assertLess(auroc, 0.8)

    def test_auroc_degenerate_returns_half(self) -> None:
        self.assertEqual(compute_auroc([80, 60], [0, 0]), 0.5)

    # ── Precision / Recall / F1 ─────────────────────────────────────────────
    def test_f1_perfect_alerts(self) -> None:
        scores = [90, 85, 40, 30, 20]
        labels = [0,  0,  1,  1,  1]
        p, r, f1 = compute_precision_recall_f1(scores, labels, threshold=50.0)
        self.assertAlmostEqual(p, 1.0)
        self.assertAlmostEqual(r, 1.0)
        self.assertAlmostEqual(f1, 1.0)

    def test_f1_no_alerts(self) -> None:
        # All scores above threshold → no alerts fired
        scores = [90, 85, 80, 75]
        labels = [0,  0,  1,  1]
        p, r, f1 = compute_precision_recall_f1(scores, labels, threshold=50.0)
        self.assertEqual(p, 0.0)
        self.assertEqual(r, 0.0)
        self.assertEqual(f1, 0.0)

    # ── Monotonicity ─────────────────────────────────────────────────────────
    def test_monotonicity_perfect(self) -> None:
        # Strictly decreasing
        self.assertAlmostEqual(compute_monotonicity([100, 90, 80, 70, 60]), 1.0)

    def test_monotonicity_random(self) -> None:
        scores = [90, 85, 88, 80, 75, 78, 70]
        result = compute_monotonicity(scores)
        self.assertGreater(result, 0.0)
        self.assertLessEqual(result, 1.0)

    def test_monotonicity_single(self) -> None:
        self.assertEqual(compute_monotonicity([80]), 1.0)

    # ── Trendability ─────────────────────────────────────────────────────────
    def test_trendability_perfect_degradation(self) -> None:
        # Linear 100→0 perfectly matches the default reference
        scores = [100 - i * 10 for i in range(11)]
        result = compute_trendability(scores)
        self.assertGreater(result, 0.95)

    def test_trendability_random_returns_midrange(self) -> None:
        import random as _r
        rng = _r.Random(1)
        scores = [rng.uniform(40, 90) for _ in range(30)]
        result = compute_trendability(scores)
        self.assertGreaterEqual(result, 0.0)
        self.assertLessEqual(result, 1.0)

    # ── Full report ──────────────────────────────────────────────────────────
    def test_full_report_degrading_session(self) -> None:
        """End-to-end §8.1 report on a simulated degrading session."""
        n = 40
        # Simulate smooth degradation 100 → 30
        hi_scores = [100 - i * 1.75 for i in range(n)]
        # Formula scores slightly above (before capping)
        formula_scores = [s + 2.0 for s in hi_scores]
        # First 20 ticks nominal, last 20 degraded
        fault_labels = [0] * 20 + [1] * 20

        report = compute_full_report(hi_scores, formula_scores, fault_labels, threshold=50.0)
        self.assertLess(report.mare, 0.15)
        self.assertGreater(report.auroc, 0.70)
        self.assertGreater(report.f1_score, 0.60)
        self.assertGreater(report.monotonicity, 0.90)
        self.assertGreater(report.trendability, 0.80)
        self.assertIn(report.grade(), ("A", "B", "C"))


if __name__ == "__main__":
    unittest.main()
