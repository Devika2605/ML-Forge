from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, core, security
from ..database import get_db
from ..content import DATASETS

router = APIRouter(prefix="/api/teams", tags=["teams"])


def _unique_team_code(db: Session) -> str:
    for _ in range(20):
        code = security.new_team_code()
        exists = db.query(models.Team).filter(models.Team.team_code == code).first()
        if not exists:
            return code
    # astronomically unlikely, but never loop forever
    raise HTTPException(500, "Could not allocate a team code, please try again.")


def _serialize_state(state: models.TeamRoundState):
    if state is None:
        return None
    return {
        "round_number": state.round_number,
        "dataset_key": state.dataset_key,
        "panels_opened": state.panels_opened or [],
        "imputation": state.imputation,
        "scaling": state.scaling,
        "duplicates_removed": state.duplicates_removed,
        "feature_flags": state.feature_flags or {},
        "model": state.model,
        "primary_metric": state.primary_metric,
        "last_run_result": state.last_run_result,
        "twist_seen_at": state.twist_seen_at,
        "twist_metric_switched": state.twist_metric_switched,
        "twist_feature_check_done": state.twist_feature_check_done,
        "blackbox_question_id": state.blackbox_question_id,
        "blackbox_answer": state.blackbox_answer,
        "blackbox_correct": state.blackbox_correct,
        "submitted": state.submitted,
        "submitted_at": state.submitted_at,
        "locked": state.locked,
    }


@router.post("/register")
def register_or_resume(payload: schemas.TeamRegister, db: Session = Depends(get_db)):
    """Registers a new team, OR resumes an existing team with the same name
    in this room — but now gated by a password, so typing someone else's
    team name doesn't let you act as them or see their progress.

    - Brand-new team name: creates the team, hashes the given password,
      and issues a session token + a short public team code.
    - Existing team name, correct password: resumes (state lives
      server-side, so nothing is lost) and issues a fresh session token.
    - Existing team name, wrong password: rejected.
    - Existing team name registered before this feature existed (no
      password on file yet): the given password is adopted as that team's
      password going forward — first person back in sets it.
    """
    room = core.get_room_or_404(db, payload.room_key)

    if len(payload.password) < 4:
        raise HTTPException(400, "Password must be at least 4 characters.")

    team = db.query(models.Team).filter(
        models.Team.room_id == room.id, models.Team.name == payload.team_name
    ).first()

    created = False
    if team is None:
        password_hash, salt = security.make_password_hash(payload.password)
        team = models.Team(
            room_id=room.id,
            name=payload.team_name,
            password_hash=password_hash,
            password_salt=salt,
            team_code=_unique_team_code(db),
            token=security.new_token(),
        )
        db.add(team)
        db.commit()
        db.refresh(team)
        created = True
    else:
        if not team.password_hash:
            # Pre-existing team from before passwords were required.
            password_hash, salt = security.make_password_hash(payload.password)
            team.password_hash = password_hash
            team.password_salt = salt
        elif not security.verify_password(payload.password, team.password_salt, team.password_hash):
            raise HTTPException(401, "Wrong password for this team name.")

        if not team.team_code:
            team.team_code = _unique_team_code(db)
        team.token = security.new_token()  # fresh session each successful login
        team.last_seen_at = core.now()
        db.commit()

    round1_state = core.get_or_create_round_state(db, team, 1)
    round2_state = None
    if team.qualified_round2:
        round2_state = core.get_or_create_round_state(db, team, 2)

    return {
        "created": created,
        "resumed": not created,
        "team_id": team.id,
        "team_code": team.team_code,
        "team_token": team.token,
        "team_name": team.name,
        "room_key": room.room_key,
        "room_status": room.status,
        "qualified_round2": team.qualified_round2,
        "round1_state": _serialize_state(round1_state),
        "round2_state": _serialize_state(round2_state),
    }


@router.get("/{room_key}/{team_name}/state")
def get_state(room_key: str, team_name: str, round_number: int, team_token: str, db: Session = Depends(get_db)):
    room = core.get_room_or_404(db, room_key)
    team = core.get_authenticated_team(db, room, team_name, team_token)
    state = core.get_or_create_round_state(db, team, round_number)
    remaining = core.time_remaining_seconds(room, round_number)
    twist_released = core.is_twist_released(room, round_number)

    dataset_cfg = DATASETS[state.dataset_key]
    return {
        "team_name": team.name,
        "room_status": room.status,
        "time_remaining": remaining,
        "twist_released": twist_released,
        "dataset": {
            "key": state.dataset_key,
            "display_name": dataset_cfg["display_name"],
            "brief": dataset_cfg["brief"],
            "core_features": dataset_cfg["core_features"],
            "toggle_features": dataset_cfg["toggle_features"],
            "target_labels": dataset_cfg["target_labels"],
        },
        "state": _serialize_state(state),
    }
