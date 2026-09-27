from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, core
from ..database import get_db

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


@router.post("")
def create_room(payload: schemas.RoomCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Room).filter(models.Room.room_key == payload.room_key).first()
    if existing:
        raise HTTPException(400, f"Room '{payload.room_key}' already exists")
    room = models.Room(room_key=payload.room_key, name=payload.name)
    db.add(room)
    db.commit()
    db.refresh(room)
    return {"room_key": room.room_key, "name": room.name, "status": room.status}


@router.get("/{room_key}")
def get_room(room_key: str, db: Session = Depends(get_db)):
    room = core.get_room_or_404(db, room_key)
    team_count = db.query(models.Team).filter(models.Team.room_id == room.id).count()
    return {
        "room_key": room.room_key,
        "name": room.name,
        "status": room.status,
        "team_count": team_count,
        "round1": {
            "started_at": room.round1_started_at,
            "locked": room.round1_locked,
            "duration_seconds": room.round1_duration_seconds,
            "twist_offset_seconds": room.round1_twist_offset_seconds,
            "time_remaining": core.time_remaining_seconds(room, 1),
            "twist_released": core.is_twist_released(room, 1),
        },
        "round2": {
            "started_at": room.round2_started_at,
            "locked": room.round2_locked,
            "duration_seconds": room.round2_duration_seconds,
            "twist_offset_seconds": room.round2_twist_offset_seconds,
            "time_remaining": core.time_remaining_seconds(room, 2),
            "twist_released": core.is_twist_released(room, 2),
        },
    }


@router.get("")
def list_rooms(db: Session = Depends(get_db)):
    rooms = db.query(models.Room).all()
    return [{"room_key": r.room_key, "name": r.name, "status": r.status} for r in rooms]
