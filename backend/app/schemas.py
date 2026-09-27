from pydantic import BaseModel
from typing import Optional, Dict, List, Any


class RoomCreate(BaseModel):
    room_key: str
    name: str


class TeamRegister(BaseModel):
    room_key: str
    team_name: str
    password: str


class PanelOpen(BaseModel):
    room_key: str
    team_name: str
    team_token: str
    round_number: int
    panel: str


class PreprocessUpdate(BaseModel):
    room_key: str
    team_name: str
    team_token: str
    round_number: int
    imputation: Optional[str] = None
    scaling: Optional[str] = None
    duplicates_removed: Optional[bool] = None
    feature_flags: Optional[Dict[str, bool]] = None


class RunModelRequest(BaseModel):
    room_key: str
    team_name: str
    team_token: str
    round_number: int
    model: str
    primary_metric: str


class ThresholdRequest(BaseModel):
    room_key: str
    team_name: str
    team_token: str
    round_number: int
    threshold: float


class TwistAckRequest(BaseModel):
    room_key: str
    team_name: str
    team_token: str
    round_number: int
    switched_metric: bool
    did_feature_check: bool


class BlackBoxAnswerRequest(BaseModel):
    room_key: str
    team_name: str
    team_token: str
    round_number: int
    question_id: str
    selected_option: str


class SubmitRequest(BaseModel):
    room_key: str
    team_name: str
    team_token: str
    round_number: int


class AdminRoundControl(BaseModel):
    room_key: str