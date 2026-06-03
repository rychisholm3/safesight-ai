"""
Timeline PDF export — generates a daily safety summary report.

Layout:
  1. Header: SafeSight AI branding + date + compliance summary
  2. Hour-by-hour event list with supervisor notes inline
  3. Footer with generation timestamp
"""
import io
import logging
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from src.timeline.compliance import ComplianceStatus
from src.timeline.notes import SupervisorNote

logger = logging.getLogger(__name__)

_DARK   = colors.HexColor("#1a1a2e")
_BLUE   = colors.HexColor("#3b82f6")
_GREEN  = colors.HexColor("#059669")
_RED    = colors.HexColor("#dc2626")
_AMBER  = colors.HexColor("#d97706")
_PURPLE = colors.HexColor("#a855f7")
_LIGHT  = colors.HexColor("#f8fafc")
_BORDER = colors.HexColor("#e2e8f0")
_TEXT   = colors.HexColor("#1f2937")
_MUTED  = colors.HexColor("#6b7280")

_TYPE_COLOR = {
    "missing_ppe":    _AMBER,
    "zone_intrusion": _RED,
    "near_miss":      _PURPLE,
}
_TYPE_LABEL = {
    "missing_ppe":    "Missing PPE",
    "zone_intrusion": "Zone Intrusion",
    "near_miss":      "Near Miss",
}


def _s() -> dict:
    base = getSampleStyleSheet()
    return {
        "body":  ParagraphStyle("body",  parent=base["Normal"], fontSize=9,  textColor=_TEXT,  leading=13),
        "small": ParagraphStyle("small", parent=base["Normal"], fontSize=7.5, textColor=_MUTED, leading=10),
        "h2":    ParagraphStyle("h2",    parent=base["Heading2"], fontSize=11, textColor=_DARK, spaceBefore=8, spaceAfter=3),
        "note":  ParagraphStyle("note",  parent=base["Normal"], fontSize=8.5, textColor=colors.HexColor("#374151"), leading=12, leftIndent=12),
    }


def generate_timeline_pdf(
    date_str: str,
    hour_groups: list[dict],
    notes_by_event: dict[str, list[SupervisorNote]],
    compliance: ComplianceStatus | None,
) -> bytes:
    buf = io.BytesIO()
    w   = letter[0] - 1.3 * inch
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        rightMargin=0.65*inch, leftMargin=0.65*inch,
        topMargin=0.65*inch,   bottomMargin=0.65*inch,
        title=f"SafeSight AI — Daily Safety Timeline {date_str}",
    )
    s     = _s()
    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    hdr = Table([[
        Paragraph("SafeSight AI", ParagraphStyle("brand", fontSize=14, textColor=colors.white, fontName="Helvetica-Bold")),
        Paragraph(f"Daily Safety Timeline — {date_str}", ParagraphStyle("sub", fontSize=10, textColor=colors.HexColor("#94a3b8"))),
    ]], colWidths=[w * 0.45, w * 0.55])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _DARK),
        ("TOPPADDING",    (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (1, 0), (1, 0), "RIGHT"),
    ]))
    story.append(hdr)

    # ── Compliance summary ────────────────────────────────────────────────────
    if compliance:
        status_color = _GREEN if compliance.status == "PASS" else _RED
        cmp_data = [[
            Paragraph(f"PPE Compliance: <b>{compliance.ppe_pct}%</b>", s["body"]),
            Paragraph(f"Zone Compliance: <b>{compliance.zone_pct}%</b>", s["body"]),
            Paragraph(f"Workers tracked: <b>{compliance.tracked_workers_24h}</b>", s["body"]),
            Paragraph(f"<b>{compliance.status}</b>", ParagraphStyle("st", fontSize=11, textColor=colors.white, fontName="Helvetica-Bold")),
        ]]
        cmp = Table(cmp_data, colWidths=[w*0.28, w*0.28, w*0.24, w*0.20])
        cmp.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (2, 0), _LIGHT),
            ("BACKGROUND",    (3, 0), (3, 0), status_color),
            ("BOX",           (0, 0), (-1, -1), 0.5, _BORDER),
            ("INNERGRID",     (0, 0), (-1, -1), 0.3, _BORDER),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN",         (3, 0), (3, 0), "CENTER"),
        ]))
        story.append(cmp)
    story.append(Spacer(1, 10))

    # ── Hour groups ───────────────────────────────────────────────────────────
    total_events = sum(len(g.get("events", [])) for g in hour_groups)
    if total_events == 0:
        story.append(Paragraph("No events recorded for this date.", s["body"]))
    else:
        for group in hour_groups:
            hour_label = group.get("label", "")
            events     = group.get("events", [])
            if not events:
                continue

            story.append(Paragraph(f"{hour_label} — {len(events)} event{'s' if len(events) != 1 else ''}", s["h2"]))
            story.append(HRFlowable(width=w, thickness=0.4, color=_BORDER, spaceAfter=4))

            for ev in events:
                etype     = ev.get("event_type", "")
                ev_color  = _TYPE_COLOR.get(etype, _MUTED)
                ev_label  = _TYPE_LABEL.get(etype, etype)
                sev       = ev.get("severity", "")
                tid       = ev.get("track_id", "?")
                zone      = ev.get("zone_id") or "—"
                ts        = (ev.get("created_at") or "")[:16].replace("T", " ")
                ppe_items = ev.get("missing_ppe") or []
                ppe_str   = ", ".join(ppe_items) if ppe_items else "—"

                row_data = [[
                    Paragraph(f"<b>{ev_label}</b>", ParagraphStyle("et", fontSize=9, textColor=ev_color, fontName="Helvetica-Bold")),
                    Paragraph(f"Worker #{tid}", s["body"]),
                    Paragraph(f"Zone: {zone}", s["body"]),
                    Paragraph(sev, ParagraphStyle("sv", fontSize=8, textColor=ev_color, fontName="Helvetica-Bold")),
                    Paragraph(ts, s["small"]),
                ]]
                row_tbl = Table(row_data, colWidths=[w*0.20, w*0.14, w*0.22, w*0.12, w*0.32])
                row_tbl.setStyle(TableStyle([
                    ("BACKGROUND",    (0, 0), (-1, -1), _LIGHT),
                    ("BOX",           (0, 0), (-1, -1), 0.3, _BORDER),
                    ("TOPPADDING",    (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING",   (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
                    ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                ]))
                story.append(row_tbl)

                if ppe_items:
                    story.append(Paragraph(f"Missing PPE: {ppe_str}", s["small"]))

                ev_id = ev.get("event_id", "")
                for note in notes_by_event.get(ev_id, []):
                    note_ts = note.created_at[:16].replace("T", " ")
                    story.append(Paragraph(
                        f'<font color="#6b7280">📝 {note_ts}</font> — {note.note}', s["note"],
                    ))

                story.append(Spacer(1, 3))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width=w, thickness=0.4, color=_BORDER, spaceAfter=4))
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    story.append(Paragraph(f"Generated by SafeSight AI · {generated}", s["small"]))

    doc.build(story)
    return buf.getvalue()
