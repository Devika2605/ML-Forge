from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, core
from ..database import get_db

router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])


@router.get("/{room_key}")
def leaderboard(
    room_key: str,
    round_number: int = Query(1, ge=1, le=2),
    db: Session = Depends(get_db),
):
    """Round 1 and Round 2 are scored independently — this returns a single
    round's ranking, never a blended score. Pass round_number=1 or 2
    (defaults to 1)."""
    room = core.get_room_or_404(db, room_key)
    teams = db.query(models.Team).filter(models.Team.room_id == room.id).all()

    rows = []
    for t in teams:
        if round_number == 2 and not t.qualified_round2:
            continue

        score_row = db.query(models.Score).filter(
            models.Score.team_id == t.id, models.Score.round_number == round_number
        ).first()
        state = db.query(models.TeamRoundState).filter(
            models.TeamRoundState.team_id == t.id, models.TeamRoundState.round_number == round_number
        ).first()

        rows.append({
            "team_name": t.name,
            "score": score_row.total if score_row else None,
            "scored": score_row is not None,
            "submitted": bool(state.submitted) if state else False,
            "qualified_round2": t.qualified_round2,
        })

    scored_rows = [r for r in rows if r["score"] is not None]
    unscored_rows = [r for r in rows if r["score"] is None]
    scored_rows.sort(key=lambda r: -r["score"])

    for i, r in enumerate(scored_rows):
        r["rank"] = i + 1
    for r in unscored_rows:
        r["rank"] = None

    return {
        "round_number": round_number,
        "rows": scored_rows + unscored_rows,
        "top_score": scored_rows[0]["score"] if scored_rows else None,
        "team_count": len(rows),
        "scored_count": len(scored_rows),
    }
