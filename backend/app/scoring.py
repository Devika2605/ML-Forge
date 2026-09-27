"""
Deterministic, deduction-based scoring engine.

Every team starts at 100 points per round. Every deduction below is computed
from logged, server-side state — never from client-reported claims — so
scores are reproducible and defensible after the event.
"""
from .content import DATASETS

REQUIRED_PANELS = ["missing_values", "class_distribution", "feature_preview"]


def _metric_band_deduction(metric_value: float) -> float:
    """Weak final performance: up to -20, banded by the achieved value of
    the team's chosen primary metric (0..1 scale)."""
    if metric_value is None:
        return 20.0
    if metric_value >= 0.90:
        return 0.0
    if metric_value >= 0.80:
        return 5.0
    if metric_value >= 0.70:
        return 10.0
    if metric_value >= 0.50:
        return 15.0
    return 20.0


def score_round1(state, dataset_cfg, twist_released_at, submitted_at):
    """
    state: TeamRoundState ORM object (already loaded)
    Returns (total, breakdown[list of {label, delta}])
    """
    breakdown = []
    total = 100.0

    # 1. Skipped investigation (-10, split across 3 panels)
    opened = set(state.panels_opened or [])
    missing_panels = [p for p in REQUIRED_PANELS if p not in opened]
    if missing_panels:
        per_panel = 10.0 / len(REQUIRED_PANELS)
        delta = -round(per_panel * len(missing_panels), 2)
        total += delta
        breakdown.append({"label": f"Skipped investigation panels: {', '.join(missing_panels)}", "delta": delta})

    # 2. Wrong preprocessing method (-15)
    acceptable = dataset_cfg.get("acceptable_imputation_set", [])
    if state.imputation not in acceptable:
        total -= 15
        breakdown.append({"label": "Preprocessing method not appropriate for missing data", "delta": -15})

    # 3. Missed hidden issue (-20): leakage or irrelevant ID still in final feature set
    flags = state.feature_flags or {}
    leakage_kept = any(flags.get(f, False) for f in dataset_cfg.get("leakage_features", []))
    irrelevant_kept = any(flags.get(f, False) for f in dataset_cfg.get("irrelevant_features", []))
    if leakage_kept or irrelevant_kept:
        issues = []
        if leakage_kept:
            issues.append("target leakage feature retained")
        if irrelevant_kept:
            issues.append("irrelevant identifier retained")
        total -= 20
        breakdown.append({"label": f"Missed hidden issue: {', '.join(issues)}", "delta": -20})

    # 4. Wrong metric after twist (-15)
    twist_required_metric = None
    if twist_released_at is not None:
        from .content import TWISTS
        twist_required_metric = TWISTS[1]["required_metric"]
        if state.primary_metric != twist_required_metric:
            total -= 15
            breakdown.append({"label": "Primary metric does not match post-twist priority", "delta": -15})

    # 5. Weak final performance (up to -20), banded on the chosen primary metric's achieved value
    metric_value = None
    if state.last_run_result and state.primary_metric:
        metric_value = state.last_run_result.get(state.primary_metric)
    perf_delta = -_metric_band_deduction(metric_value)
    if perf_delta != 0:
        total += perf_delta
        breakdown.append({"label": f"Final performance ({state.primary_metric or 'no metric'}={metric_value})", "delta": perf_delta})

    # 6. Slow to adapt to twist (up to -10)
    if twist_released_at is not None:
        if state.twist_seen_at is None or not state.twist_metric_switched:
            total -= 10
            breakdown.append({"label": "Did not adapt to twist in time", "delta": -10})
        else:
            elapsed = (state.twist_seen_at - twist_released_at).total_seconds()
            if elapsed > 0:
                # scale 0 at <=60s, up to -10 at >=600s (10 min)
                scaled = min(10.0, max(0.0, (elapsed - 60) / 540 * 10))
                if scaled > 0:
                    total -= scaled
                    breakdown.append({"label": "Slow to respond to twist", "delta": -round(scaled, 2)})

    # 7. Twist feature-check skipped or wrong (-5)
    if twist_released_at is not None and state.twist_metric_switched and not state.twist_feature_check_done:
        total -= 5
        breakdown.append({"label": "Skipped post-twist feature sanity check", "delta": -5})

    total = max(0.0, min(100.0, total))
    return round(total, 2), breakdown


def score_round2(state, dataset_cfg, twist_released_at, blackbox_correct):
    breakdown = []
    total = 100.0

    # Misdiagnosis proxy: reuse investigation-panel completeness as the
    # "diagnosis" check for this simplified system. Round 2 logs the same
    # three investigation panels as Round 1 (missing_values,
    # class_distribution, feature_preview) — not confusion_matrix /
    # client_requirement, which the frontend never logs — so this now
    # checks against REQUIRED_PANELS like Round 1 does.
    opened = set(state.panels_opened or [])
    missing_panels = [p for p in REQUIRED_PANELS if p not in opened]
    if missing_panels:
        total -= 15
        breakdown.append({"label": f"Misdiagnosis: skipped investigation panels: {', '.join(missing_panels)}", "delta": -15})

    # Poor rebuild / weak final performance (up to -20)
    metric_value = None
    if state.last_run_result and state.primary_metric:
        metric_value = state.last_run_result.get(state.primary_metric)
    perf_delta = -min(20.0, _metric_band_deduction(metric_value))
    if perf_delta != 0:
        total += perf_delta
        breakdown.append({"label": f"Weak final performance ({state.primary_metric or 'no metric'}={metric_value})", "delta": perf_delta})

    # Failed to adapt to live incident (up to -20)
    if twist_released_at is not None:
        if state.twist_seen_at is None or not state.twist_metric_switched:
            total -= 20
            breakdown.append({"label": "Did not adapt to live incident", "delta": -20})
        else:
            elapsed = (state.twist_seen_at - twist_released_at).total_seconds()
            if elapsed > 0:
                scaled = min(20.0, max(0.0, (elapsed - 30) / 270 * 20))
                if scaled > 0:
                    total -= scaled
                    breakdown.append({"label": "Slow to respond to incident", "delta": -round(scaled, 2)})

    # Bad model/evaluation decision (-15): leakage/irrelevant still present
    flags = state.feature_flags or {}
    leakage_kept = any(flags.get(f, False) for f in dataset_cfg.get("leakage_features", []))
    irrelevant_kept = any(flags.get(f, False) for f in dataset_cfg.get("irrelevant_features", []))
    if leakage_kept or irrelevant_kept:
        total -= 15
        breakdown.append({"label": "Flaw retained in final Round 2 submission", "delta": -15})

    # Black Box wrong answer (-10)
    if blackbox_correct is False:
        total -= 10
        breakdown.append({"label": "Black Box challenge answered incorrectly", "delta": -10})
    elif blackbox_correct is None:
        total -= 10
        breakdown.append({"label": "Black Box challenge not answered", "delta": -10})

    total = max(0.0, min(100.0, total))
    return round(total, 2), breakdown
