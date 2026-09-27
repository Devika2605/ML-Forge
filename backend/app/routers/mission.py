import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, core, ml_lookup
from ..database import get_db
from ..content import DATASETS, TWISTS, BLACKBOX_QUESTIONS

router = APIRouter(prefix="/api/mission", tags=["mission"])


def _load(db, payload_room_key, payload_team_name, payload_round_number, payload_team_token):
    room = core.get_room_or_404(db, payload_room_key)
    team = core.get_authenticated_team(db, room, payload_team_name, payload_team_token)
    state = core.get_or_create_round_state(db, team, payload_round_number)
    return room, team, state


@router.get("/{room_key}/{team_name}/{round_number}/investigate")
def investigate(room_key: str, team_name: str, round_number: int, team_token: str, db: Session = Depends(get_db)):
    room = core.get_room_or_404(db, room_key)
    team = core.get_authenticated_team(db, room, team_name, team_token)
    state = core.get_or_create_round_state(db, team, round_number)
    cfg = DATASETS[state.dataset_key]
    df = ml_lookup.get_dataframe(state.dataset_key, cfg["csv"])

    # public/train view only — matches what the precompute script trained on
    # conceptually; for investigation purposes we show summary stats over
    # the full public CSV (labels included, since this is training data).
    missing_pct = (df.isna().mean() * 100).round(1).to_dict()
    class_counts = df[cfg["target"]].value_counts(normalize=True).round(3).to_dict()
    class_dist = {cfg["target_labels"].get(str(k), str(k)): v for k, v in class_counts.items()}
    sample_df = df.sample(min(10, len(df)), random_state=1)
    sample_records = sample_df.to_dict(orient="records")
    sample = [
        {k: (None if isinstance(v, float) and pd.isna(v) else v) for k, v in row.items()}
        for row in sample_records
    ]

    return {
        "rows": len(df),
        "columns": list(df.columns),
        "target": cfg["target"],
        "dtypes": {c: str(df[c].dtype) for c in df.columns},
        "missing_values_pct": missing_pct,
        "class_distribution": class_dist,
        "sample_records": sample,
    }


@router.post("/panel-open")
def panel_open(payload: schemas.PanelOpen, db: Session = Depends(get_db)):
    room, team, state = _load(db, payload.room_key, payload.team_name, payload.round_number, payload.team_token)
    core.assert_round_active_and_unlocked(db, room, payload.round_number, state)
    opened = set(state.panels_opened or [])
    opened.add(payload.panel)
    state.panels_opened = list(opened)
    db.commit()
    return {"panels_opened": state.panels_opened}


@router.post("/preprocess")
def preprocess(payload: schemas.PreprocessUpdate, db: Session = Depends(get_db)):
    room, team, state = _load(db, payload.room_key, payload.team_name, payload.round_number, payload.team_token)
    core.assert_round_active_and_unlocked(db, room, payload.round_number, state)

    if payload.imputation is not None:
        state.imputation = payload.imputation
    if payload.scaling is not None:
        state.scaling = payload.scaling
    if payload.duplicates_removed is not None:
        state.duplicates_removed = payload.duplicates_removed
    if payload.feature_flags is not None:
        flags = dict(state.feature_flags or {})
        flags.update(payload.feature_flags)
        state.feature_flags = flags
        # mark that they touched features after a twist, for the feature-check deduction
        if core.is_twist_released(room, payload.round_number) and state.twist_metric_switched:
            state.twist_feature_check_done = True

    db.commit()
    return {
        "imputation": state.imputation,
        "scaling": state.scaling,
        "duplicates_removed": state.duplicates_removed,
        "feature_flags": state.feature_flags,
    }


@router.post("/run-model")
def run_model(payload: schemas.RunModelRequest, db: Session = Depends(get_db)):
    room, team, state = _load(db, payload.room_key, payload.team_name, payload.round_number, payload.team_token)
    core.assert_round_active_and_unlocked(db, room, payload.round_number, state)

    if not state.imputation or not state.scaling:
        raise HTTPException(400, "Choose an imputation and scaling method before running a model.")

    cfg = DATASETS[state.dataset_key]
    flags = {f: (state.feature_flags or {}).get(f, False) for f in cfg["toggle_features"]}

    result = ml_lookup.lookup_result(state.dataset_key, state.imputation, state.scaling, flags, payload.model)
    if result is None:
        raise HTTPException(400, "No precomputed result for this exact configuration. Try a different combination.")

    state.model = payload.model
    state.primary_metric = payload.primary_metric
    state.last_run_result = result
    db.commit()

    experiment = models.Experiment(
        team_id=team.id,
        round_number=payload.round_number,
        config={
            "imputation": state.imputation, "scaling": state.scaling,
            "feature_flags": flags, "model": payload.model, "primary_metric": payload.primary_metric,
        },
        result=result,
    )
    db.add(experiment)
    db.commit()

    return {"result": result, "experiment_id": experiment.id}


@router.post("/threshold")
def adjust_threshold(payload: schemas.ThresholdRequest, db: Session = Depends(get_db)):
    """Live recompute of precision/recall/F1 at a chosen decision threshold,
    against the team's last run. Reads only the cached probability array
    from precompute — no model is trained or touched here, so this is safe
    to call on every slider drag from many teams at once."""
    room, team, state = _load(db, payload.room_key, payload.team_name, payload.round_number, payload.team_token)
    core.assert_round_active_and_unlocked(db, room, payload.round_number, state)

    if not (0.0 <= payload.threshold <= 1.0):
        raise HTTPException(400, "Threshold must be between 0 and 1.")
    if not state.last_run_result or "test_probs" not in state.last_run_result:
        raise HTTPException(400, "Run a model before adjusting the threshold.")

    recomputed = ml_lookup.recompute_at_threshold(state.last_run_result, payload.threshold)
    if recomputed is None:
        raise HTTPException(400, "This result has no stored probabilities to recompute from.")
    return {"result": recomputed}


@router.get("/{room_key}/{team_name}/{round_number}/experiments")
def experiment_history(room_key: str, team_name: str, round_number: int, team_token: str, db: Session = Depends(get_db)):
    room = core.get_room_or_404(db, room_key)
    team = core.get_authenticated_team(db, room, team_name, team_token)
    exps = db.query(models.Experiment).filter(
        models.Experiment.team_id == team.id, models.Experiment.round_number == round_number
    ).order_by(models.Experiment.created_at).all()
    return [{"id": e.id, "config": e.config, "result": e.result, "created_at": e.created_at} for e in exps]


@router.get("/{room_key}/{team_name}/{round_number}/twist")
def get_twist(room_key: str, team_name: str, round_number: int, db: Session = Depends(get_db)):
    room = core.get_room_or_404(db, room_key)
    released = core.is_twist_released(room, round_number)
    if not released:
        return {"released": False}
    twist = TWISTS[round_number]
    return {"released": True, "headline": twist["headline"], "detail": twist["detail"]}


@router.post("/twist-ack")
def twist_ack(payload: schemas.TwistAckRequest, db: Session = Depends(get_db)):
    room, team, state = _load(db, payload.room_key, payload.team_name, payload.round_number, payload.team_token)
    core.assert_round_active_and_unlocked(db, room, payload.round_number, state)

    if not core.is_twist_released(room, payload.round_number):
        raise HTTPException(400, "Twist has not been released yet")

    if state.twist_seen_at is None:
        state.twist_seen_at = core.now()
    if payload.switched_metric:
        state.twist_metric_switched = True
    if payload.did_feature_check:
        state.twist_feature_check_done = True
    db.commit()
    return {"twist_seen_at": state.twist_seen_at, "twist_metric_switched": state.twist_metric_switched}


@router.get("/{room_key}/{team_name}/{round_number}/blackbox")
def get_blackbox(room_key: str, team_name: str, round_number: int, team_token: str, db: Session = Depends(get_db)):
    room = core.get_room_or_404(db, room_key)
    team = core.get_authenticated_team(db, room, team_name, team_token)
    state = core.get_or_create_round_state(db, team, round_number)
    if round_number != 2:
        raise HTTPException(400, "Black Box challenge only applies to Round 2")

    if state.blackbox_question_id is None:
        # deterministic assignment based on team id, so it's stable across reloads
        q = BLACKBOX_QUESTIONS[team.id % len(BLACKBOX_QUESTIONS)]
        state.blackbox_question_id = q["id"]
        db.commit()
    q = next(x for x in BLACKBOX_QUESTIONS if x["id"] == state.blackbox_question_id)
    return {"id": q["id"], "prompt": q["prompt"], "options": q["options"], "answered": state.blackbox_answer is not None}


@router.post("/blackbox-answer")
def blackbox_answer(payload: schemas.BlackBoxAnswerRequest, db: Session = Depends(get_db)):
    room, team, state = _load(db, payload.room_key, payload.team_name, payload.round_number, payload.team_token)
    core.assert_round_active_and_unlocked(db, room, payload.round_number, state)

    q = next((x for x in BLACKBOX_QUESTIONS if x["id"] == payload.question_id), None)
    if q is None:
        raise HTTPException(404, "Unknown question")

    state.blackbox_answer = payload.selected_option
    state.blackbox_correct = (payload.selected_option == q["correct_option"])
    db.commit()
    return {"correct": state.blackbox_correct, "concept": q["concept"]}


@router.post("/submit")
def submit(payload: schemas.SubmitRequest, db: Session = Depends(get_db)):
    room, team, state = _load(db, payload.room_key, payload.team_name, payload.round_number, payload.team_token)
    core.assert_round_active_and_unlocked(db, room, payload.round_number, state)

    state.submitted = True
    state.submitted_at = core.now()
    state.locked = True
    db.commit()
    return {"submitted": True, "submitted_at": state.submitted_at}