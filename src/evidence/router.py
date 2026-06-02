"""
Evidence router — three endpoints for Phase 6: Explainability & Evidence.

GET /evidence/{event_id}/explanation       → structured reason breakdown (JSON)
GET /evidence/{event_id}/annotated-snapshot → JPEG with person bbox drawn
GET /evidence/{event_id}/report.pdf        → full PDF evidence report
"""
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from src.auth.dependencies import require_auth
from src.auth.models import User
from src.evidence.annotation import annotate_snapshot, _make_label
from src.evidence.explanation import ExplanationItem, build_explanation
from src.evidence.pdf_export import generate_evidence_pdf
from src.osha.matcher import match_violation
from src.osha.rules import OshaCode
from src.store import EventStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evidence", tags=["evidence"])


# ── Dependency stubs — overridden by main.py ─────────────────────────────────

def _get_event_store() -> EventStore:      # pragma: no cover
    raise NotImplementedError

def _get_snapshot_dir() -> Path:           # pragma: no cover
    raise NotImplementedError


# ── Pydantic response model ───────────────────────────────────────────────────

class ExplanationItemOut(BaseModel):
    category: str
    text: str
    icon: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_event_or_404(event_id: str, store: EventStore) -> dict:
    rows = store.get_events(limit=10_000)
    match = next((r for r in rows if r["event_id"] == event_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id!r} not found")
    return match


def _osha_codes_for_event(event: dict) -> list[OshaCode]:
    return match_violation(
        event_type  = event.get("event_type", ""),
        missing_ppe = event.get("missing_ppe") or [],
        zone_rule   = event.get("zone_rule"),
    )


def _osha_codes_as_dicts(codes: list[OshaCode]) -> list[dict]:
    return [
        {
            "code":               c.code,
            "title":              c.title,
            "description":        c.description,
            "fine_min_usd":       c.fine_min_usd,
            "fine_max_usd":       c.fine_max_usd,
            "willful_max_usd":    c.willful_max_usd,
            "corrective_actions": list(c.corrective_actions),
            "plain_english":      c.plain_english,
            "reference_url":      c.reference_url,
        }
        for c in codes
    ]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/health")
def evidence_health():
    return {"status": "ok"}


@router.get("/{event_id}/explanation", response_model=list[ExplanationItemOut])
def get_explanation(
    event_id: str,
    _: User = Depends(require_auth),
    store: EventStore = Depends(_get_event_store),
) -> list[ExplanationItemOut]:
    """Return a structured reason breakdown for a single event."""
    event = _get_event_or_404(event_id, store)
    items = build_explanation(event)
    return [ExplanationItemOut(category=i.category, text=i.text, icon=i.icon) for i in items]


@router.get("/{event_id}/annotated-snapshot")
def get_annotated_snapshot(
    event_id: str,
    _: User = Depends(require_auth),
    store: EventStore       = Depends(_get_event_store),
    snapshot_dir: Path      = Depends(_get_snapshot_dir),
) -> Response:
    """Return the event snapshot as a JPEG with the person bbox drawn on it."""
    event = _get_event_or_404(event_id, store)

    snap_path = event.get("snapshot_path")
    if not snap_path:
        raise HTTPException(status_code=404, detail="No snapshot for this event")

    snap_file = Path(snap_path)
    if not snap_file.is_absolute():
        snap_file = snapshot_dir / snap_file.name

    bbox_raw = event.get("bbox")
    bbox     = tuple(int(v) for v in bbox_raw) if bbox_raw else None

    jpeg = annotate_snapshot(
        snapshot_path      = snap_file,
        bbox               = bbox,              # type: ignore[arg-type]
        label              = _make_label(event),
        severity           = event.get("severity", "WARNING"),
        person_detections  = event.get("person_detections") or [],
    )
    if jpeg is None:
        raise HTTPException(status_code=404, detail="Snapshot file not found or unreadable")

    return Response(content=jpeg, media_type="image/jpeg")


@router.get("/{event_id}/report.pdf")
def get_evidence_pdf(
    event_id: str,
    _: User = Depends(require_auth),
    store: EventStore  = Depends(_get_event_store),
    snapshot_dir: Path = Depends(_get_snapshot_dir),
) -> Response:
    """Generate and return a full PDF evidence report for an event."""
    event      = _get_event_or_404(event_id, store)
    explanation = build_explanation(event)
    osha_codes  = _osha_codes_for_event(event)
    osha_dicts  = _osha_codes_as_dicts(osha_codes)

    # Try to get the annotated snapshot to embed in the PDF
    snap_path = event.get("snapshot_path")
    annotated_jpeg: bytes | None = None
    if snap_path:
        snap_file = Path(snap_path)
        if not snap_file.is_absolute():
            snap_file = snapshot_dir / snap_file.name
        bbox_raw = event.get("bbox")
        bbox     = tuple(int(v) for v in bbox_raw) if bbox_raw else None
        annotated_jpeg = annotate_snapshot(
            snapshot_path      = snap_file,
            bbox               = bbox,          # type: ignore[arg-type]
            label              = _make_label(event),
            severity           = event.get("severity", "WARNING"),
            person_detections  = event.get("person_detections") or [],
        )

    try:
        pdf_bytes = generate_evidence_pdf(
            event            = event,
            explanation      = explanation,
            osha_codes       = osha_dicts,
            annotated_jpeg   = annotated_jpeg,
        )
    except Exception as exc:
        logger.error("PDF generation failed for event %s: %s", event_id, exc)
        raise HTTPException(status_code=500, detail="PDF generation failed") from exc

    filename = f"safesight-evidence-{event_id[:8]}.pdf"
    return Response(
        content     = pdf_bytes,
        media_type  = "application/pdf",
        headers     = {"Content-Disposition": f'attachment; filename="{filename}"'},
    )
