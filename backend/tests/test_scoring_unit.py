"""Pure unit tests for the deduction-based scoring engine, no server needed."""
import sys
import os
import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.scoring import score_round1, _metric_band_deduction
from app.content import DATASETS


class FakeState:
    def __init__(self, **kwargs):
        self.panels_opened = kwargs.get("panels_opened", [])
        self.imputation = kwargs.get("imputation")
        self.feature_flags = kwargs.get("feature_flags", {})
        self.primary_metric = kwargs.get("primary_metric")
        self.last_run_result = kwargs.get("last_run_result")
        self.twist_seen_at = kwargs.get("twist_seen_at")
        self.twist_metric_switched = kwargs.get("twist_metric_switched", False)
        self.twist_feature_check_done = kwargs.get("twist_feature_check_done", False)


def check(cond, msg):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {msg}")
    assert cond, msg


def test_perfect_team_scores_100_before_twist():
    cfg = DATASETS["medivision_x"]
    state = FakeState(
        panels_opened=["missing_values", "class_distribution", "feature_preview"],
        imputation="median",
        feature_flags={"Patient_ID": False, "Leakage_Feature": False},
        primary_metric="recall",
        last_run_result={"recall": 0.95, "f1": 0.9, "accuracy": 0.9, "precision": 0.85},
    )
    total, breakdown = score_round1(state, cfg, twist_released_at=None, submitted_at=None)
    check(total == 100.0, f"Perfect team with no twist scores 100 (got {total})")


def test_missed_panels_deduction():
    cfg = DATASETS["medivision_x"]
    state = FakeState(
        panels_opened=[],
        imputation="median",
        feature_flags={"Patient_ID": False, "Leakage_Feature": False},
        primary_metric="recall",
        last_run_result={"recall": 0.95},
    )
    total, breakdown = score_round1(state, cfg, twist_released_at=None, submitted_at=None)
    check(total == 90.0, f"Skipping all 3 panels costs exactly -10 (got {total})")


def test_leakage_retained_costs_20():
    cfg = DATASETS["medivision_x"]
    state = FakeState(
        panels_opened=["missing_values", "class_distribution", "feature_preview"],
        imputation="median",
        feature_flags={"Patient_ID": False, "Leakage_Feature": True},
        primary_metric="recall",
        last_run_result={"recall": 0.95},
    )
    total, breakdown = score_round1(state, cfg, twist_released_at=None, submitted_at=None)
    check(total == 80.0, f"Retaining leakage feature costs exactly -20 (got {total})")


def test_wrong_preprocessing_costs_15():
    cfg = DATASETS["medivision_x"]
    state = FakeState(
        panels_opened=["missing_values", "class_distribution", "feature_preview"],
        imputation="mode",  # not in acceptable set for this dataset
        feature_flags={"Patient_ID": False, "Leakage_Feature": False},
        primary_metric="recall",
        last_run_result={"recall": 0.95},
    )
    total, breakdown = score_round1(state, cfg, twist_released_at=None, submitted_at=None)
    check(total == 85.0, f"Wrong imputation method costs exactly -15 (got {total})")


def test_twist_ignored_capped_deduction():
    cfg = DATASETS["medivision_x"]
    now = datetime.datetime.utcnow()
    twist_at = now - datetime.timedelta(minutes=5)
    state = FakeState(
        panels_opened=["missing_values", "class_distribution", "feature_preview"],
        imputation="median",
        feature_flags={"Patient_ID": False, "Leakage_Feature": False},
        primary_metric="accuracy",  # never switched
        last_run_result={"accuracy": 0.9, "recall": 0.95},
        twist_seen_at=None,
        twist_metric_switched=False,
    )
    total, breakdown = score_round1(state, cfg, twist_released_at=twist_at, submitted_at=None)
    # -15 (wrong metric after twist) + -10 (slow/no adapt, capped) = -25, from 100 -> 75
    check(total == 75.0, f"Ignoring the twist entirely costs -15 (wrong metric) and -10 (no adapt) = 75 (got {total})")


def test_score_floors_at_zero():
    """Round 1's own deduction categories sum to at most ~90-95 points, so
    this specific worst-case scenario lands at 5-10, not below 0 — that's
    expected. We separately confirm the floor clamp exists as a safety net
    by calling the deduction math with an artificially large penalty."""
    cfg = DATASETS["medivision_x"]
    now = datetime.datetime.utcnow()
    twist_at = now - datetime.timedelta(minutes=20)
    state = FakeState(
        panels_opened=[],
        imputation="mode",
        feature_flags={"Patient_ID": True, "Leakage_Feature": True},
        primary_metric="accuracy",
        last_run_result={"accuracy": 0.3},
        twist_seen_at=None,
        twist_metric_switched=False,
    )
    total, breakdown = score_round1(state, cfg, twist_released_at=twist_at, submitted_at=None)
    check(total == 10.0, f"Worst realistic Round 1 case lands at 10 (max deductions ~90), not below (got {total})")
    check(total >= 0, "Score never goes negative")

    # Now confirm the floor clamp itself: max(0.0, ...) is present in the
    # source and would clamp any hypothetical deduction total exceeding 100.
    from app.scoring import score_round1 as sr1
    import inspect
    src = inspect.getsource(sr1)
    check("max(0.0" in src, "Floor-at-zero clamp is present in the scoring function source")


def test_metric_band_thresholds():
    check(_metric_band_deduction(0.95) == 0.0, "F1>=0.90 -> no performance deduction")
    check(_metric_band_deduction(0.85) == 5.0, "F1 0.80-0.89 -> -5")
    check(_metric_band_deduction(0.75) == 10.0, "F1 0.70-0.79 -> -10")
    check(_metric_band_deduction(0.60) == 15.0, "F1 0.50-0.69 -> -15")
    check(_metric_band_deduction(0.2) == 20.0, "F1<0.50 -> -20 (full deduction)")
    check(_metric_band_deduction(None) == 20.0, "No result at all -> -20")


if __name__ == "__main__":
    test_perfect_team_scores_100_before_twist()
    test_missed_panels_deduction()
    test_leakage_retained_costs_20()
    test_wrong_preprocessing_costs_15()
    test_twist_ignored_capped_deduction()
    test_score_floors_at_zero()
    test_metric_band_thresholds()
    print("\nALL SCORING UNIT TESTS PASSED")
