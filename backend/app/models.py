import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, JSON,
    UniqueConstraint
)
from sqlalchemy.orm import relationship
from .database import Base


def now():
    return datetime.datetime.utcnow()


class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True)
    room_key = Column(String, unique=True, index=True)  # e.g. "LIVE_2026"
    name = Column(String)
    status = Column(String, default="PREPARATION")  # PREPARATION, ROUND1, ROUND2, FINISHED, CLOSED
    round1_started_at = Column(DateTime, nullable=True)
    round1_twist_at = Column(DateTime, nullable=True)
    round1_locked = Column(Boolean, default=False)
    round1_duration_seconds = Column(Integer, default=30 * 60)
    round1_twist_offset_seconds = Column(Integer, default=15 * 60)

    round2_started_at = Column(DateTime, nullable=True)
    round2_twist_at = Column(DateTime, nullable=True)
    round2_locked = Column(Boolean, default=False)
    round2_duration_seconds = Column(Integer, default=20 * 60)
    round2_twist_offset_seconds = Column(Integer, default=10 * 60)

    created_at = Column(DateTime, default=now)

    teams = relationship("Team", back_populates="room")


class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey("rooms.id"))
    name = Column(String, index=True)
    created_at = Column(DateTime, default=now)
    last_seen_at = Column(DateTime, default=now)

    # --- auth: added so a team name can't be "taken over" by anyone who
    # simply types it in. A team sets a password the first time they
    # register; after that, resuming under the same name requires it.
    password_hash = Column(String, nullable=True)
    password_salt = Column(String, nullable=True)
    team_code = Column(String, index=True, nullable=True)  # short public ID, e.g. "MLF-7K2QDN"
    token = Column(String, index=True, nullable=True)       # session secret returned after login

    qualified_round2 = Column(Boolean, default=False)

    room = relationship("Room", back_populates="teams")
    round_states = relationship("TeamRoundState", back_populates="team")
    experiments = relationship("Experiment", back_populates="team")
    scores = relationship("Score", back_populates="team")

    __table_args__ = (UniqueConstraint("room_id", "name", name="uq_room_team_name"),)


class TeamRoundState(Base):
    """One row per (team, round). Holds live workspace state so a
    disconnect/reconnect can resume exactly where the team left off."""
    __tablename__ = "team_round_states"
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"))
    round_number = Column(Integer)  # 1 or 2

    dataset_key = Column(String)

    panels_opened = Column(JSON, default=list)  # ["missing_values","class_distribution","feature_preview"]

    imputation = Column(String, nullable=True)  # mean/median/mode/remove_rows
    scaling = Column(String, nullable=True)      # none/standardize/normalize
    duplicates_removed = Column(Boolean, default=False)
    feature_flags = Column(JSON, default=dict)  # {"Patient_ID": false, "Leakage_Feature": false}
    model = Column(String, nullable=True)
    primary_metric = Column(String, nullable=True)  # accuracy/precision/recall/f1

    last_run_result = Column(JSON, nullable=True)

    twist_seen_at = Column(DateTime, nullable=True)
    twist_metric_switched = Column(Boolean, default=False)
    twist_feature_check_done = Column(Boolean, default=False)

    blackbox_question_id = Column(String, nullable=True)
    blackbox_answer = Column(String, nullable=True)
    blackbox_correct = Column(Boolean, nullable=True)

    defense_question_id = Column(String, nullable=True)
    defense_score = Column(JSON, nullable=True)  # {"issue":0-4,"justify":0-3,"followup":0-3,"notes":""}

    submitted = Column(Boolean, default=False)
    submitted_at = Column(DateTime, nullable=True)
    locked = Column(Boolean, default=False)

    updated_at = Column(DateTime, default=now, onupdate=now)

    team = relationship("Team", back_populates="round_states")
    __table_args__ = (UniqueConstraint("team_id", "round_number", name="uq_team_round"),)


class Experiment(Base):
    __tablename__ = "experiments"
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"))
    round_number = Column(Integer)
    config = Column(JSON)
    result = Column(JSON)
    created_at = Column(DateTime, default=now)

    team = relationship("Team", back_populates="experiments")


class Score(Base):
    __tablename__ = "scores"
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"))
    round_number = Column(Integer)
    breakdown = Column(JSON)  # list of {label, delta}
    total = Column(Float)
    created_at = Column(DateTime, default=now)

    team = relationship("Team", back_populates="scores")
    __table_args__ = (UniqueConstraint("team_id", "round_number", name="uq_team_round_score"),)


class AdminEvent(Base):
    __tablename__ = "admin_events"
    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey("rooms.id"))
    action = Column(String)
    detail = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=now)
