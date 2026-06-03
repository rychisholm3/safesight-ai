"""
Timeline & Compliance Autopilot router — Phase 8.

Endpoints
---------
GET  /timeline                          events for a date, grouped by hour
GET  /timeline/compliance               live status + 7-day history + forecast
POST /timeline/{event_id}/note          add supervisor intervention note
GET  /timeline/{event_id}/notes         get all notes for an event
DELETE /timeline/notes/{note_id}        delete a note
GET  /timeline/export.pdf               PDF of the day's timeline
"""
import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.auth.dependencies import require_auth
from src.auth.models import User
from src.store import EventStore
from src.timeline.compliance import ComplianceEngine
from src.timeline.incidents import detect_incidents
from src.timeline.notes import NotesDB, SupervisorNote
from src.timeline.pdf_export import generate_timeline_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/timeline", tags=["timeline"])


# ── Dependency stubs — overridden by main.py ─────────────────────────────────

def _get_store() -> EventStore:          # pragma: no cover
    raise NotImplementedError

def _get_notes_db() -> NotesDB:          # pragma: no cover
    raise NotImplementedError

def _get_compliance() -> ComplianceEngine:  # pragma: no cover
    raise NotImplementedError


# ── Pydantic models ───────────────────────────────────────────────────────────

class NoteIn(BaseModel):
    note: str = Field(..., min_length=1, max_length=2000)


class NoteOut(BaseModel):
    note_id:    str
    event_id:   str
    user_id:    str
    note:       str
    created_at: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _group_by_hour(events: list[dict]) -> list[dict]:
    """Group events into hour buckets, sorted chronologically."""
    buckets: dict[int, list[dict]] = {}
    for ev in events:
        ts_str = ev.get("created_at") or ""
        try:
            hour = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).hour
        except ValueError:
            hour = 0
        buckets.setdefault(hour, []).append(ev)

    return [
        {
            "hour":        h,
            "label":       f"{h:02d}:00",
            "event_count": len(evs),
            "events":      sorted(evs, key=lambda e: e.get("created_at", "")),
        }
        for h, evs in sorted(buckets.items())
    ]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
def get_timeline(
    _: User = Depends(require_auth),
    store: EventStore    = Depends(_get_store),
    notes_db: NotesDB    = Depends(_get_notes_db),
    date_str: str | None = Query(default=None, alias="date",
                                  description="YYYY-MM-DD (UTC); defaults to today"),
    limit: int           = Query(default=500, ge=1, le=2000),
):
    """Return events for a date grouped by hour, with supervisor notes inline."""
    if date_str is None:
        target = date.today()
    else:
        try:
            target = date.fromisoformat(date_str)
        except ValueError:
            raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD")

    next_day = target + timedelta(days=1)
    since    = datetime(target.year, target.month, target.day, tzinfo=timezone.utc)
    until    = datetime(next_day.year, next_day.month, next_day.day, tzinfo=timezone.utc)

    all_events = store.get_events(limit=limit, since=since)
    events = [e for e in all_events if e.get("created_at", "") < until.isoformat()]

    # Attach notes
    event_ids = [e["event_id"] for e in events]
    notes_map = notes_db.get_notes_bulk(event_ids)
    for ev in events:
        ev["notes"] = [
            {"note_id": n.note_id, "user_id": n.user_id,
             "note": n.note, "created_at": n.created_at}
            for n in notes_map.get(ev["event_id"], [])
        ]

    groups    = _group_by_hour(events)
    incidents = detect_incidents(events)
    return {
        "date":           target.isoformat(),
        "total_events":   len(events),
        "incident_count": len(incidents),
        "hours":          groups,
        "incidents":      incidents,
    }


@router.get("/compliance")
def get_compliance(
    _: User = Depends(require_auth),
    engine: ComplianceEngine = Depends(_get_compliance),
):
    """Return live compliance status, 7-day history, and tomorrow's forecast."""
    history  = engine.daily_history(days=7)
    status   = engine.current_status()
    forecast = engine.forecast(history)

    return {
        "status":   {
            "ppe_pct":             status.ppe_pct,
            "zone_pct":            status.zone_pct,
            "overall_pct":         status.overall_pct,
            "pass_fail":           status.status,
            "tracked_workers_24h": status.tracked_workers_24h,
            "computed_at":         status.computed_at,
        },
        "history": [
            {
                "date":        h.date,
                "ppe_pct":     h.ppe_pct,
                "zone_pct":    h.zone_pct,
                "overall_pct": h.overall_pct,
                "event_count": h.event_count,
            }
            for h in history
        ],
        "forecast": {
            "predicted_pct": forecast.predicted_pct,
            "trend":         forecast.trend,
            "trend_pct":     forecast.trend_pct,
        },
    }


@router.post("/{event_id}/note", response_model=NoteOut)
def add_note(
    event_id: str,
    body: NoteIn,
    current_user: User = Depends(require_auth),
    notes_db: NotesDB  = Depends(_get_notes_db),
    store: EventStore  = Depends(_get_store),
) -> NoteOut:
    """Add a supervisor intervention note to an event."""
    # Validate event exists
    rows = store.get_events(limit=10_000)
    if not any(r["event_id"] == event_id for r in rows):
        raise HTTPException(status_code=404, detail=f"Event {event_id!r} not found")

    note = notes_db.add_note(
        event_id = event_id,
        user_id  = current_user.user_id,
        note     = body.note,
    )
    return NoteOut(**note.__dict__)


@router.get("/{event_id}/notes", response_model=list[NoteOut])
def get_notes(
    event_id: str,
    _: User = Depends(require_auth),
    notes_db: NotesDB = Depends(_get_notes_db),
) -> list[NoteOut]:
    """Get all supervisor notes for an event."""
    return [NoteOut(**n.__dict__) for n in notes_db.get_notes(event_id)]


@router.delete("/notes/{note_id}")
def delete_note(
    note_id: str,
    _: User = Depends(require_auth),
    notes_db: NotesDB = Depends(_get_notes_db),
):
    """Delete a supervisor note."""
    if not notes_db.delete_note(note_id):
        raise HTTPException(status_code=404, detail="Note not found")
    return {"deleted": note_id}


@router.get("/export.pdf")
def export_pdf(
    _: User = Depends(require_auth),
    store: EventStore        = Depends(_get_store),
    notes_db: NotesDB        = Depends(_get_notes_db),
    engine: ComplianceEngine = Depends(_get_compliance),
    date_str: str | None     = Query(default=None, alias="date"),
):
    """Generate and return a PDF of the day's safety timeline."""
    if date_str is None:
        target = date.today()
    else:
        try:
            target = date.fromisoformat(date_str)
        except ValueError:
            raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD")

    next_day = target + timedelta(days=1)
    since    = datetime(target.year, target.month, target.day, tzinfo=timezone.utc)
    until    = datetime(next_day.year, next_day.month, next_day.day, tzinfo=timezone.utc)

    all_events = store.get_events(limit=2000, since=since)
    events = [e for e in all_events if e.get("created_at", "") < until.isoformat()]

    event_ids  = [e["event_id"] for e in events]
    notes_map  = notes_db.get_notes_bulk(event_ids)
    groups     = _group_by_hour(events)
    compliance = engine.current_status()

    try:
        pdf = generate_timeline_pdf(
            date_str       = target.isoformat(),
            hour_groups    = groups,
            notes_by_event = notes_map,
            compliance     = compliance,
            incidents      = detect_incidents(events),
        )
    except Exception as exc:
        logger.error("Timeline PDF generation failed: %s", exc)
        raise HTTPException(status_code=500, detail="PDF generation failed") from exc

    fname = f"safesight-timeline-{target.isoformat()}.pdf"
    return Response(
        content    = pdf,
        media_type = "application/pdf",
        headers    = {"Content-Disposition": f'attachment; filename="{fname}"'},
    )
