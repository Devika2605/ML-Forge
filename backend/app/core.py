import datetime
from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import models
from .content import DATASETS

ROUND_DATASET = {1: "medivision_x", 2: "fraudnet_x"}


def now():
    return datetime.datetime.utcnow()


def get_room_or_404(db: Session, room_key: str) -> models.Room:
    room = db.query(models.Room).filter(models.Room.room_key == room_key).first()
    if not room:
        raise HTTPException(404, f"Room '{room_key}' not found")
    return room


def get_team_or_404(db: Session, room: models.Room, team_name: str) -> models.Team:
    team = db.query(models.Team).filter(
        models.Team.room_id == room.id, models.Team.name == team_name
    ).first()
    if not team:
        raise HTTPException(404, f"Team '{team_name}' not found in this room")
    return team


def get_authenticated_team(db: Session, room: models.Room, team_name: str, team_token: str) -> models.Team:
    """Like get_team_or_404, but also proves the caller is the same team
    that registered (holds the session token issued at login) — this is
    what stops someone from acting as a team just by typing its name."""
    team = get_team_or_404(db, room, team_name)
    if not team_token or not team.token or team_token != team.token:
        raise HTTPException(401, "Your session for this team has expired or is invalid. Please re-enter your team name and password.")
    return team


def get_or_create_round_state(db: Session, team: models.Team, round_number: int) -> models.TeamRoundState:
    state = db.query(models.TeamRoundState).filter(
        models.TeamRoundState.team_id == team.id,
        models.TeamRoundState.round_number == round_number,
    ).first()
    if state:
        return state
    state = models.TeamRoundState(
        team_id=team.id,
        round_number=round_number,
        dataset_key=ROUND_DATASET[round_number],
        panels_opened=[],
        feature_flags={f: False for f in DATASETS[ROUND_DATASET[round_number]]["toggle_features"]},
    )
    db.add(state)
    db.commit()
    db.refresh(state)
    return state


def round_timing(room: models.Room, round_number: int):
    """Returns (started_at, duration_seconds, twist_offset_seconds, locked, twist_at)"""
    if round_number == 1:
        return (room.round1_started_at, room.round1_duration_seconds,
                room.round1_twist_offset_seconds, room.round1_locked, room.round1_twist_at)
    else:
        return (room.round2_started_at, room.round2_duration_seconds,
                room.round2_twist_offset_seconds, room.round2_locked, room.round2_twist_at)


def time_remaining_seconds(room: models.Room, round_number: int):
    started_at, duration, _, locked, _ = round_timing(room, round_number)
    if started_at is None:
        return None
    if locked:
        return 0
    elapsed = (now() - started_at).total_seconds()
    remaining = duration - elapsed
    return max(0, round(remaining))


def is_twist_released(room: models.Room, round_number: int):
    _, _, twist_offset, _, twist_at = round_timing(room, round_number)
    if twist_at is not None:
        return True
    started_at, _, _, _, _ = round_timing(room, round_number)
    if started_at is None:
        return False
    elapsed = (now() - started_at).total_seconds()
    return elapsed >= twist_offset


def get_twist_released_at(room: models.Room, round_number: int):
    started_at, _, twist_offset, _, twist_at = round_timing(room, round_number)
    if twist_at is not None:
        return twist_at
    if started_at is None:
        return None
    if is_twist_released(room, round_number):
        return started_at + datetime.timedelta(seconds=twist_offset)
    return None


def assert_round_active_and_unlocked(db: Session, room: models.Room, round_number: int, state: models.TeamRoundState):
    started_at, duration, _, locked, _ = round_timing(room, round_number)
    if started_at is None:
        raise HTTPException(400, f"Round {round_number} has not started yet")
    if locked or state.locked or state.submitted:
        raise HTTPException(423, "This round is locked. No further changes are possible.")
    remaining = time_remaining_seconds(room, round_number)
    if remaining is not None and remaining <= 0:
        # auto-lock this team's state
        state.locked = True
        db.commit()
        raise HTTPException(423, "Time is up. This round has been automatically locked.")
