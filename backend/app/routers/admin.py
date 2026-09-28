import csv
import io
import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from .. import models, schemas, core, security
from ..database import get_db
from ..content import DATASETS
from ..scoring import score_round1, score_round2

router = APIRouter(prefix="/api/admin", tags=["admin"])


# Team-password tools are the one part of admin that can hand out access to a
# team's account, so unlike the rest of this router they require a key.
# Set ADMIN_KEY in the backend environment; the fallback below is only so it
# works out of the box — change it before a real event.
ADMIN_KEY = os.environ.get("ADMIN_KEY", "changeme-admin")


def require_admin_key(x_admin_key: str = Header(default="")):
    if not secrets.compare_digest(x_admin_key.encode(), ADMIN_KEY.encode()):
        raise HTTPException(403, "Wrong or missing admin key.")


def _log(db: Session, room: models.Room, action: str, detail=None):
    db.add(models.AdminEvent(room_id=room.id, action=action, detail=detail))
    db.commit()


@router.post("/{room_key}/start-round1")
def start_round1(room_key: str, db: Session = Depends(get_db)):
    room = core.get_room_or_404(db, room_key)
    if room.round1_started_at is not None:
        raise HTTPException(400, "Round 1 has already started")
    room.round1_started_at = core.now()
    room.status = "ROUND1"
    db.commit()
    _log(db, room, "START_ROUND1")
    return {"round1_started_at": room.round1_started_at}


@router.post("/{room_key}/release-twist")
def release_twist_round1(room_key: str, db: Session = Depends(get_db)):
    room = core.get_room_or_404(db, room_key)
    if room.round1_started_at is None:
        raise HTTPException(400, "Round 1 has not started")
    room.round1_twist_at = core.now()
    db.commit()
    _log(db, room, "RELEASE_TWIST_ROUND1")
    return {"round1_twist_at": room.round1_twist_at}


@router.post("/{room_key}/lock-submissions")
def lock_round1(room_key: str, db: Session = Depends(get_db)):
    room = core.get_room_or_404(db, room_key)
    room.round1_locked = True
    db.commit()
    states = db.query(models.TeamRoundState).join(models.Team).filter(
        models.Team.room_id == room.id, models.TeamRoundState.round_number == 1
    ).all()
    for s in states:
        s.locked = True
    db.commit()
    _log(db, room, "LOCK_ROUND1")
    return {"locked": True, "teams_locked": len(states)}


@router.post("/{room_key}/calculate-scores")
def calculate_scores_round1(room_key: str, db: Session = Depends(get_db)):
    room = core.get_room_or_404(db, room_key)
    teams = db.query(models.Team).filter(models.Team.room_id == room.id).all()
    twist_at = room.round1_twist_at
    results = []
    for t in teams:
        state = db.query(models.TeamRoundState).filter(
            models.TeamRoundState.team_id == t.id, models.TeamRoundState.round_number == 1
        ).first()
        if state is None:
            continue
        cfg = DATASETS[state.dataset_key]
        total, breakdown = score_round1(state, cfg, twist_at, state.submitted_at)

        score_row = db.query(models.Score).filter(
            models.Score.team_id == t.id, models.Score.round_number == 1
        ).first()
        if score_row is None:
            score_row = models.Score(team_id=t.id, round_number=1)
            db.add(score_row)
        score_row.total = total
        score_row.breakdown = breakdown
        db.commit()
        results.append({"team_name": t.name, "total": total})

    _log(db, room, "CALCULATE_SCORES_ROUND1", {"count": len(results)})
    return {"scored_teams": len(results)}


def _auto_qualify_top10_if_needed(db: Session, room: models.Room):
    """Ensures the Round-1-based Top-10 qualification has run before Round 2
    scoring depends on it. ADVANCE TOP 10 and START ROUND 2 are two separate
    buttons in the Admin UI with no enforced order — if START ROUND 2 (or
    worse, CALC SCORES R2) gets clicked first, no team is ever flagged
    qualified_round2, and every Round 2 submission silently scores zero
    teams even though the room genuinely played the round. This makes that
    impossible: if nobody in the room is qualified yet, compute the
    Round-1 Top 10 automatically before proceeding. It only ever fires once
    per room (as soon as any team is qualified, it's a no-op), so it never
    overrides a qualification an admin has already run or hand-adjusted.
    """
    already_qualified = db.query(models.Team).filter(
        models.Team.room_id == room.id, models.Team.qualified_round2 == True  # noqa: E712
    ).first()
    if already_qualified:
        return None
    teams = db.query(models.Team).filter(models.Team.room_id == room.id).all()
    scored = []
    for t in teams:
        s = db.query(models.Score).filter(models.Score.team_id == t.id, models.Score.round_number == 1).first()
        if s:
            scored.append((t, s.total))
    if not scored:
        return None  # round 1 scores haven't been calculated yet — nothing to qualify from
    scored.sort(key=lambda x: x[1], reverse=True)
    top10 = scored[:10]
    for t, _ in top10:
        t.qualified_round2 = True
    db.commit()
    _log(db, room, "AUTO_ADVANCE_TOP10", {"teams": [t.name for t, _ in top10]})
    return top10


@router.post("/{room_key}/advance-top10")
def advance_top10(room_key: str, db: Session = Depends(get_db)):
    room = core.get_room_or_404(db, room_key)
    teams = db.query(models.Team).filter(models.Team.room_id == room.id).all()
    scored = []
    for t in teams:
        s = db.query(models.Score).filter(models.Score.team_id == t.id, models.Score.round_number == 1).first()
        if s:
            scored.append((t, s.total))
    scored.sort(key=lambda x: x[1], reverse=True)
    top10 = scored[:10]
    for t, _ in top10:
        t.qualified_round2 = True
    db.commit()
    _log(db, room, "ADVANCE_TOP10", {"teams": [t.name for t, _ in top10]})
    return {"advanced": [{"team_name": t.name, "round1_score": s} for t, s in top10]}


@router.post("/{room_key}/start-round2")
def start_round2(room_key: str, db: Session = Depends(get_db)):
    room = core.get_room_or_404(db, room_key)
    if room.round2_started_at is not None:
        raise HTTPException(400, "Round 2 has already started")
    _auto_qualify_top10_if_needed(db, room)
    room.round2_started_at = core.now()
    room.status = "ROUND2"
    db.commit()
    _log(db, room, "START_ROUND2")
    return {"round2_started_at": room.round2_started_at}


@router.post("/{room_key}/release-incident")
def release_incident_round2(room_key: str, db: Session = Depends(get_db)):
    room = core.get_room_or_404(db, room_key)
    if room.round2_started_at is None:
        raise HTTPException(400, "Round 2 has not started")
    room.round2_twist_at = core.now()
    db.commit()
    _log(db, room, "RELEASE_INCIDENT_ROUND2")
    return {"round2_twist_at": room.round2_twist_at}


@router.post("/{room_key}/lock-final-submissions")
def lock_round2(room_key: str, db: Session = Depends(get_db)):
    room = core.get_room_or_404(db, room_key)
    room.round2_locked = True
    db.commit()
    states = db.query(models.TeamRoundState).join(models.Team).filter(
        models.Team.room_id == room.id, models.TeamRoundState.round_number == 2
    ).all()
    for s in states:
        s.locked = True
    db.commit()
    _log(db, room, "LOCK_ROUND2")
    return {"locked": True, "teams_locked": len(states)}


@router.post("/{room_key}/calculate-scores-round2")
def calculate_scores_round2(room_key: str, db: Session = Depends(get_db)):
    room = core.get_room_or_404(db, room_key)
    _auto_qualify_top10_if_needed(db, room)
    teams = db.query(models.Team).filter(models.Team.room_id == room.id, models.Team.qualified_round2 == True).all()  # noqa: E712
    twist_at = room.round2_twist_at
    results = []
    for t in teams:
        state = db.query(models.TeamRoundState).filter(
            models.TeamRoundState.team_id == t.id, models.TeamRoundState.round_number == 2
        ).first()
        if state is None:
            continue
        cfg = DATASETS[state.dataset_key]
        total, breakdown = score_round2(state, cfg, twist_at, state.blackbox_correct)

        score_row = db.query(models.Score).filter(
            models.Score.team_id == t.id, models.Score.round_number == 2
        ).first()
        if score_row is None:
            score_row = models.Score(team_id=t.id, round_number=2)
            db.add(score_row)
        score_row.total = total
        score_row.breakdown = breakdown
        db.commit()
        results.append({"team_name": t.name, "total": total})

    _log(db, room, "CALCULATE_SCORES_ROUND2", {"count": len(results)})
    return {"scored_teams": len(results)}


@router.get("/{room_key}/winner")
def show_winner(room_key: str, db: Session = Depends(get_db)):
    """Round 1 and Round 2 are independent, separately-scored rounds — there
    is no blended "overall" score. Round 2 is the final round the Top 10
    play, so the winner is whoever ranks highest on the Round 2 score alone;
    Round 1 score is still returned for context but is not part of ranking."""
    room = core.get_room_or_404(db, room_key)
    teams = db.query(models.Team).filter(models.Team.room_id == room.id, models.Team.qualified_round2 == True).all()  # noqa: E712
    ranked = []
    for t in teams:
        r1 = db.query(models.Score).filter(models.Score.team_id == t.id, models.Score.round_number == 1).first()
        r2 = db.query(models.Score).filter(models.Score.team_id == t.id, models.Score.round_number == 2).first()
        if not r2:
            continue
        ranked.append({
            "team_name": t.name,
            "round1_score": r1.total if r1 else None,
            "round2_score": r2.total,
        })
    ranked.sort(key=lambda r: -r["round2_score"])
    for i, r in enumerate(ranked):
        r["rank"] = i + 1
    _log(db, room, "SHOW_WINNER")
    return ranked


@router.get("/{room_key}/tab-switches")
def tab_switches(room_key: str, db: Session = Depends(get_db)):
    """Per-team tab-switch counts for this room, most-flagged first, plus
    the running total shown on the Live View panel."""
    room = core.get_room_or_404(db, room_key)
    events = db.query(models.AdminEvent).filter(
        models.AdminEvent.room_id == room.id, models.AdminEvent.action == "TAB_SWITCH"
    ).all()
    counts = {}
    for e in events:
        name = (e.detail or {}).get("team_name", "unknown")
        counts[name] = counts.get(name, 0) + 1
    by_team = sorted(
        [{"team_name": k, "count": v} for k, v in counts.items()],
        key=lambda r: -r["count"],
    )
    return {"total": len(events), "by_team": by_team}


@router.get("/{room_key}/report/{round_number}")
def download_report(room_key: str, round_number: int, db: Session = Depends(get_db)):
    """CSV validation report for a round: one row per team with their final
    score, every scoring deduction (what they got wrong), and the raw
    decisions they made (what they chose), plus tab-switch count."""
    room = core.get_room_or_404(db, room_key)
    teams = db.query(models.Team).filter(models.Team.room_id == room.id).all()
    if round_number == 2:
        teams = [t for t in teams if t.qualified_round2]
    twist_at = room.round1_twist_at if round_number == 1 else room.round2_twist_at

    tab_events = db.query(models.AdminEvent).filter(
        models.AdminEvent.room_id == room.id, models.AdminEvent.action == "TAB_SWITCH"
    ).all()
    tab_counts = {}
    for e in tab_events:
        d = e.detail or {}
        if d.get("round_number") == round_number:
            tab_counts[d.get("team_name")] = tab_counts.get(d.get("team_name"), 0) + 1

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "team_name", "score", "submitted", "submitted_at", "dataset",
        "imputation", "scaling", "model", "primary_metric", "final_metric_value",
        "features_removed", "blackbox_correct", "tab_switches", "deductions",
    ])

    for t in teams:
        state = db.query(models.TeamRoundState).filter(
            models.TeamRoundState.team_id == t.id, models.TeamRoundState.round_number == round_number
        ).first()
        if state is None:
            continue
        cfg = DATASETS[state.dataset_key]
        if round_number == 1:
            total, breakdown = score_round1(state, cfg, twist_at, state.submitted_at)
        else:
            total, breakdown = score_round2(state, cfg, twist_at, state.blackbox_correct)

        flags = state.feature_flags or {}
        features_removed = [f for f, kept in flags.items() if not kept]
        metric_value = None
        if state.last_run_result and state.primary_metric:
            metric_value = state.last_run_result.get(state.primary_metric)
        deductions = "; ".join(f"{b['label']} ({b['delta']})" for b in breakdown) or "None — clean run"

        writer.writerow([
            t.name, total, state.submitted, state.submitted_at, state.dataset_key,
            state.imputation, state.scaling, state.model, state.primary_metric, metric_value,
            ", ".join(features_removed) or "none",
            state.blackbox_correct if round_number == 2 else "",
            tab_counts.get(t.name, 0),
            deductions,
        ])

    _log(db, room, "DOWNLOAD_REPORT", {"round_number": round_number})
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=round{round_number}_report_{room_key}.csv"},
    )


@router.get("/{room_key}/live-view")
def live_view(room_key: str, db: Session = Depends(get_db)):
    room = core.get_room_or_404(db, room_key)
    teams = db.query(models.Team).filter(models.Team.room_id == room.id).all()
    round1_states = db.query(models.TeamRoundState).join(models.Team).filter(
        models.Team.room_id == room.id, models.TeamRoundState.round_number == 1
    ).all()
    submitted = sum(1 for s in round1_states if s.submitted)
    working = len(round1_states) - submitted

    scores = db.query(models.Score).join(models.Team).filter(
        models.Team.room_id == room.id, models.Score.round_number == 1
    ).all()
    top_score = max((s.total for s in scores), default=None)
    low_score = min((s.total for s in scores), default=None)

    return {
        "room_status": room.status,
        "teams_registered": len(teams),
        "round1_time_remaining": core.time_remaining_seconds(room, 1),
        "round1_twist_released": core.is_twist_released(room, 1),
        "round1_submitted": submitted,
        "round1_working": working,
        "top_score": top_score,
        "lowest_score": low_score,
        "round2_time_remaining": core.time_remaining_seconds(room, 2),
        "round2_twist_released": core.is_twist_released(room, 2),
    }


@router.get("/{room_key}/teams", dependencies=[Depends(require_admin_key)])
def list_teams(room_key: str, db: Session = Depends(get_db)):
    """Who is registered, for the password-reset panel. Never returns any
    password data — only whether one has been set."""
    room = core.get_room_or_404(db, room_key)
    teams = db.query(models.Team).filter(models.Team.room_id == room.id).order_by(models.Team.name).all()
    return [
        {
            "team_id": t.id,
            "team_name": t.name,
            "team_code": t.team_code,
            "has_password": bool(t.password_hash),
            "qualified_round2": t.qualified_round2,
            "last_seen_at": t.last_seen_at,
        }
        for t in teams
    ]


@router.post("/{room_key}/teams/{team_id}/reset-password", dependencies=[Depends(require_admin_key)])
def reset_team_password(room_key: str, team_id: int, db: Session = Depends(get_db)):
    """For a team that forgot its password: issues a temporary one, shown to
    the organizer exactly once. The old password is never stored or shown
    (only a hash is kept), so it can't be recovered — only replaced. Existing
    sessions are signed out."""
    room = core.get_room_or_404(db, room_key)
    team = db.query(models.Team).filter(models.Team.id == team_id, models.Team.room_id == room.id).first()
    if not team:
        raise HTTPException(404, "Team not found in this room")
    temp = security.new_temp_password()
    team.password_hash, team.password_salt = security.make_password_hash(temp)
    team.token = None
    db.commit()
    _log(db, room, "RESET_PASSWORD", {"team_name": team.name})
    return {"team_name": team.name, "temporary_password": temp}