"""
Evaluation Metrics — Operational Plan v2 §8.1
==============================================
Implements all model-accuracy and system-quality metrics required by the plan.

  §8.1 Model & Engine Accuracy
  ─────────────────────────────
  • MARE         — Mean Absolute Relative Error for HI prediction drift.
  • RMSE         — Root Mean Square Error for HI variance analysis.
  • AUROC        — Area Under ROC for fault classification (normal vs. degraded).
  • Precision    — TP / (TP + FP) for alert triggering.
  • Recall       — TP / (TP + FN) for missed faults.
  • F1-Score     — Harmonic mean of precision and recall.
  • Monotonicity — HI should decrease monotonically under sustained stress.
  • Trendability — Correlation between HI trajectory and actual degradation curve.

All implementations are pure-Python (no scipy/sklearn required) so they
run without heavy ML dependencies.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


# ---------------------------------------------------------------------------
# §8.1 Helper type
# ---------------------------------------------------------------------------

@dataclass
class EvaluationReport:
    """Aggregated evaluation results for one locomotive or test run."""
    mare: float
    rmse: float
    auroc: float
    precision: float
    recall: float
    f1_score: float
    monotonicity: float
    trendability: float

    def to_dict(self) -> dict[str, float]:
        return {
            "mare": round(self.mare, 4),
            "rmse": round(self.rmse, 4),
            "auroc": round(self.auroc, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "monotonicity": round(self.monotonicity, 4),
            "trendability": round(self.trendability, 4),
        }

    def grade(self) -> str:
        """Quick quality rating based on composite score."""
        composite = (
            (1 - self.mare) * 0.15
            + (1 - min(self.rmse / 20, 1)) * 0.15
            + self.auroc * 0.20
            + self.f1_score * 0.20
            + self.monotonicity * 0.15
            + self.trendability * 0.15
        )
        if composite >= 0.85:
            return "A"
        if composite >= 0.70:
            return "B"
        if composite >= 0.55:
            return "C"
        return "D"


# ---------------------------------------------------------------------------
# §8.1 — MARE  (Mean Absolute Relative Error)
# ---------------------------------------------------------------------------

def compute_mare(predictions: Sequence[float], actuals: Sequence[float]) -> float:
    """
    MARE = mean( |pred - actual| / max(|actual|, ε) )

    Used for HI prediction drift: how much does the smoothed HI deviate
    from the raw formula output across a session?
    """
    if len(predictions) != len(actuals) or not predictions:
        return 0.0
    total = sum(
        abs(p - a) / max(abs(a), 1e-6)
        for p, a in zip(predictions, actuals)
    )
    return total / len(predictions)


# ---------------------------------------------------------------------------
# §8.1 — RMSE  (Root Mean Square Error)
# ---------------------------------------------------------------------------

def compute_rmse(predictions: Sequence[float], actuals: Sequence[float]) -> float:
    """
    RMSE = sqrt( mean( (pred - actual)^2 ) )

    Used for HI variance analysis across time steps.
    """
    if len(predictions) != len(actuals) or not predictions:
        return 0.0
    mse = sum((p - a) ** 2 for p, a in zip(predictions, actuals)) / len(predictions)
    return math.sqrt(mse)


# ---------------------------------------------------------------------------
# §8.1 — AUROC  (Area Under ROC Curve)
# ---------------------------------------------------------------------------

def compute_auroc(scores: Sequence[float], labels: Sequence[int]) -> float:
    """
    Area Under the Receiver Operating Characteristic curve.

    scores  — continuous HI scores (higher = healthier)
    labels  — binary ground truth: 1 = fault/degraded, 0 = normal

    Since high HI = healthy, we invert scores before computing so that
    higher classifier output = fault (score_fault = 100 - HI).

    Uses trapezoidal rule (no scipy required).
    """
    if len(scores) != len(labels) or not scores:
        return 0.5

    # Invert: fault detector score = 100 - HI
    fault_scores = [100.0 - s for s in scores]
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5  # degenerate case

    # Sort by fault_score descending
    pairs = sorted(zip(fault_scores, labels), key=lambda x: x[0], reverse=True)

    tpr_points: list[float] = [0.0]
    fpr_points: list[float] = [0.0]
    tp = fp = 0

    for _, label in pairs:
        if label == 1:
            tp += 1
        else:
            fp += 1
        tpr_points.append(tp / n_pos)
        fpr_points.append(fp / n_neg)

    # Trapezoidal integration
    auroc = sum(
        (fpr_points[i] - fpr_points[i - 1]) * (tpr_points[i] + tpr_points[i - 1]) / 2
        for i in range(1, len(fpr_points))
    )
    return max(0.0, min(1.0, auroc))


# ---------------------------------------------------------------------------
# §8.1 — Precision, Recall, F1-Score
# ---------------------------------------------------------------------------

def compute_precision_recall_f1(
    scores: Sequence[float],
    labels: Sequence[int],
    threshold: float = 50.0,
) -> tuple[float, float, float]:
    """
    Binary classification metrics.

    An alert is fired when HI drops below `threshold` (default 50 = grade C boundary).
    labels: 1 = actual fault, 0 = normal.

    Returns (precision, recall, f1).
    """
    if len(scores) != len(labels) or not scores:
        return 0.0, 0.0, 0.0

    tp = fp = fn = 0
    for score, label in zip(scores, labels):
        predicted_fault = score < threshold
        if predicted_fault and label == 1:
            tp += 1
        elif predicted_fault and label == 0:
            fp += 1
        elif not predicted_fault and label == 1:
            fn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    return precision, recall, f1


# ---------------------------------------------------------------------------
# §8.1 — Monotonicity
# ---------------------------------------------------------------------------

def compute_monotonicity(scores: Sequence[float]) -> float:
    """
    Fraction of consecutive HI pairs that are non-increasing.

    Monotonicity = #{i : score[i+1] <= score[i]} / (N - 1)

    Perfect monotonic degradation → 1.0.
    Random walk → ~0.5.

    Plan requirement: HI should decrease monotonically under sustained stress
    (no false recoveries).
    """
    if len(scores) < 2:
        return 1.0
    non_increasing = sum(
        1 for i in range(1, len(scores)) if scores[i] <= scores[i - 1] + 0.01
    )
    return non_increasing / (len(scores) - 1)


# ---------------------------------------------------------------------------
# §8.1 — Trendability
# ---------------------------------------------------------------------------

def compute_trendability(
    hi_scores: Sequence[float],
    degradation_curve: Sequence[float] | None = None,
) -> float:
    """
    Spearman rank-order correlation between HI trajectory and the expected
    degradation curve (plan §8.1 Trendability).

    If no reference `degradation_curve` is provided, a linear countdown from
    100 → 0 is used as the ideal degradation baseline.

    Returns a value in [0, 1] where 1 = perfect trendability.
    """
    n = len(hi_scores)
    if n < 3:
        return 1.0

    reference = (
        list(degradation_curve)
        if degradation_curve is not None
        else [100.0 - (100.0 * i / (n - 1)) for i in range(n)]
    )
    if len(reference) != n:
        return 0.0

    def _ranks(values: list[float]) -> list[float]:
        sorted_vals = sorted(enumerate(values), key=lambda x: x[1])
        ranks = [0.0] * len(values)
        for rank, (idx, _) in enumerate(sorted_vals):
            ranks[idx] = float(rank + 1)
        return ranks

    r_hi = _ranks(list(hi_scores))
    r_ref = _ranks(reference)

    # Spearman = 1 - 6 * sum(d²) / (n * (n²-1))
    d_sq_sum = sum((a - b) ** 2 for a, b in zip(r_hi, r_ref))
    spearman = 1.0 - (6.0 * d_sq_sum) / (n * (n ** 2 - 1))

    # Convert [-1, 1] → [0, 1] (plan expects a quality metric)
    return max(0.0, (spearman + 1.0) / 2.0)


# ---------------------------------------------------------------------------
# Convenience: full report from a telemetry session
# ---------------------------------------------------------------------------

def compute_full_report(
    hi_scores: Sequence[float],
    formula_scores: Sequence[float],
    fault_labels: Sequence[int],
    threshold: float = 50.0,
) -> EvaluationReport:
    """
    Compute all §8.1 metrics from a single session.

    Parameters
    ──────────
    hi_scores      — smoothed HI scores recorded over the session.
    formula_scores — raw formula outputs before recovery capping.
    fault_labels   — 1 = known fault/degraded tick, 0 = nominal.
    threshold      — HI score below which an alert is raised.
    """
    mare = compute_mare(hi_scores, formula_scores)
    rmse = compute_rmse(hi_scores, formula_scores)
    auroc = compute_auroc(hi_scores, fault_labels)
    precision, recall, f1 = compute_precision_recall_f1(hi_scores, fault_labels, threshold)
    monotonicity = compute_monotonicity(hi_scores)
    trendability = compute_trendability(hi_scores)

    return EvaluationReport(
        mare=mare,
        rmse=rmse,
        auroc=auroc,
        precision=precision,
        recall=recall,
        f1_score=f1,
        monotonicity=monotonicity,
        trendability=trendability,
    )
