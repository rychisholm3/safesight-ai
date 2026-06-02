"""
Evidence PDF generator — produces a professional, self-contained report
for a single safety violation event using reportlab Platypus.

The PDF includes:
  • Header with SafeSight AI branding and event summary
  • Reason breakdown (structured explanation)
  • OSHA regulation cards (code, title, fine range, corrective actions)
  • Annotated snapshot image (if available)
  • Footer with generation timestamp and legal disclaimer
"""
import io
import logging
from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.evidence.explanation import ExplanationItem

logger = logging.getLogger(__name__)

# ── Brand colours ─────────────────────────────────────────────────────────────
_DARK    = colors.HexColor("#1a1a2e")
_BLUE    = colors.HexColor("#3b82f6")
_AMBER   = colors.HexColor("#d97706")
_RED     = colors.HexColor("#dc2626")
_GREEN   = colors.HexColor("#059669")
_LIGHT   = colors.HexColor("#f8fafc")
_BORDER  = colors.HexColor("#e2e8f0")
_TEXT    = colors.HexColor("#1f2937")
_MUTED   = colors.HexColor("#6b7280")


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"],
            fontSize=18, textColor=colors.white,
            leading=22, spaceAfter=0,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"],
            fontSize=12, textColor=_DARK,
            spaceBefore=12, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"],
            fontSize=10, textColor=_TEXT,
            leading=14, spaceAfter=4,
        ),
        "small": ParagraphStyle(
            "small", parent=base["Normal"],
            fontSize=8, textColor=_MUTED,
            leading=11,
        ),
        "label": ParagraphStyle(
            "label", parent=base["Normal"],
            fontSize=8, textColor=_MUTED,
            leading=10, spaceAfter=1,
            textTransform="uppercase",
        ),
        "value": ParagraphStyle(
            "value", parent=base["Normal"],
            fontSize=11, textColor=_TEXT,
            leading=14, fontName="Helvetica-Bold",
        ),
        "osha_code": ParagraphStyle(
            "osha_code", parent=base["Normal"],
            fontSize=11, textColor=colors.white,
            fontName="Helvetica-Bold", leading=14,
        ),
        "osha_body": ParagraphStyle(
            "osha_body", parent=base["Normal"],
            fontSize=9, textColor=_TEXT, leading=13,
        ),
        "disclaimer": ParagraphStyle(
            "disclaimer", parent=base["Normal"],
            fontSize=7.5, textColor=_MUTED, leading=10,
        ),
        "item_cat": ParagraphStyle(
            "item_cat", parent=base["Normal"],
            fontSize=9, textColor=_MUTED,
            fontName="Helvetica-Bold", leading=11,
            textTransform="uppercase",
        ),
        "item_text": ParagraphStyle(
            "item_text", parent=base["Normal"],
            fontSize=10, textColor=_TEXT, leading=14,
        ),
    }


def _severity_color(severity: str) -> colors.Color:
    return _RED if severity == "CRITICAL" else _AMBER


def _fmt_currency(n: int) -> str:
    return f"${n:,}"


def _fmt_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return iso


def generate_evidence_pdf(
    event: dict,
    explanation: list[ExplanationItem],
    osha_codes: list[dict],
    annotated_jpeg: bytes | None,
) -> bytes:
    """Build and return a PDF evidence report as raw bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        title="SafeSight AI — Safety Violation Evidence Report",
        author="SafeSight AI",
    )

    s    = _styles()
    w    = letter[0] - 1.3 * inch   # usable page width
    sev  = event.get("severity", "WARNING")
    sev_color = _severity_color(sev)
    story: list = []

    # ── Header band ──────────────────────────────────────────────────────────
    etype    = event.get("event_type", "")
    is_ppe   = etype == "missing_ppe"
    ev_label = (
        f"Missing PPE — {', '.join(event.get('missing_ppe') or []) or 'unknown'}"
        if is_ppe else
        f"Zone Intrusion — {event.get('zone_id') or 'unknown zone'}"
    )
    header_table = Table(
        [[
            Paragraph("SafeSight AI", ParagraphStyle("brand", fontSize=14, textColor=colors.white, fontName="Helvetica-Bold")),
            Paragraph("SAFETY VIOLATION — EVIDENCE REPORT", ParagraphStyle("sub", fontSize=9, textColor=colors.HexColor("#94a3b8"), fontName="Helvetica")),
        ]],
        colWidths=[w * 0.5, w * 0.5],
    )
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _DARK),
        ("TOPPADDING",    (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (1, 0), (1, 0), "RIGHT"),
    ]))
    story.append(header_table)

    # Severity + event type banner
    banner = Table(
        [[
            Paragraph(f"{ev_label}", ParagraphStyle("ev", fontSize=13, textColor=colors.white, fontName="Helvetica-Bold")),
            Paragraph(sev, ParagraphStyle("sev_p", fontSize=10, textColor=colors.white, fontName="Helvetica-Bold")),
        ]],
        colWidths=[w * 0.78, w * 0.22],
    )
    banner.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), sev_color),
        ("BACKGROUND",    (1, 0), (1, 0),   sev_color),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (1, 0), (1, 0), "CENTER"),
        ("FONTNAME",      (1, 0), (1, 0), "Helvetica-Bold"),
    ]))
    story.append(banner)
    story.append(Spacer(1, 10))

    # ── Event summary grid ────────────────────────────────────────────────────
    def cell(label: str, value: str) -> list:
        return [Paragraph(label, s["label"]), Paragraph(value or "—", s["value"])]

    conf_pct = round(float(event.get("confidence") or 0) * 100)
    fine_min = event.get("fine_min_usd", 0) or 0
    fine_max = event.get("fine_max_usd", 0) or 0

    grid_data = [
        [cell("Event Type",   "Missing PPE" if is_ppe else "Zone Intrusion"),
         cell("Worker ID",    f"#{event.get('track_id', '?')}")],
        [cell("Zone",         event.get("zone_id") or "Site-wide"),
         cell("Zone Rule",    event.get("zone_rule") or "—")],
        [cell("Timestamp",    _fmt_time(event.get("created_at", ""))),
         cell("Status",       "ACTIVE" if event.get("end_frame") is None else "CLOSED")],
        [cell("Confidence",   f"{conf_pct}%"),
         cell("Event ID",     event.get("event_id", "")[:16] + "…")],
    ]
    if fine_max > 0:
        grid_data.append([
            cell("Est. OSHA Fine",
                 f"{_fmt_currency(fine_min)} – {_fmt_currency(fine_max)} per violation"),
            cell("OSHA Codes",
                 ", ".join(event.get("osha_codes") or []) or "—"),
        ])

    col_w = w / 2
    summary_table = Table(
        [[row[0], row[1]] for row in grid_data],
        colWidths=[col_w, col_w],
    )
    summary_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _LIGHT),
        ("BOX",           (0, 0), (-1, -1), 0.5, _BORDER),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, _BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 12))

    # ── Annotated snapshot ────────────────────────────────────────────────────
    if annotated_jpeg:
        story.append(Paragraph("Evidence Snapshot (Annotated)", s["h2"]))
        story.append(HRFlowable(width=w, thickness=0.5, color=_BORDER, spaceAfter=6))
        try:
            img_buf = io.BytesIO(annotated_jpeg)
            img     = Image(img_buf, width=w, height=w * 0.5, kind="bound")
            story.append(img)
        except Exception as exc:
            logger.warning("Could not embed snapshot in PDF: %s", exc)
        story.append(Spacer(1, 12))

    # ── Reason breakdown ──────────────────────────────────────────────────────
    story.append(Paragraph("Reason Breakdown", s["h2"]))
    story.append(HRFlowable(width=w, thickness=0.5, color=_BORDER, spaceAfter=6))

    for i, item in enumerate(explanation, 1):
        row_data = [[
            Paragraph(f"{i}. {item.icon} {item.category}", s["item_cat"]),
            Paragraph(item.text, s["item_text"]),
        ]]
        row_table = Table(row_data, colWidths=[w * 0.28, w * 0.72])
        row_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), _LIGHT if i % 2 == 0 else colors.white),
            ("BOX",           (0, 0), (-1, -1), 0.3, _BORDER),
            ("TOPPADDING",    (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(row_table)
    story.append(Spacer(1, 14))

    # ── OSHA regulation cards ─────────────────────────────────────────────────
    if osha_codes:
        story.append(Paragraph(f"OSHA Regulations Triggered ({len(osha_codes)})", s["h2"]))
        story.append(HRFlowable(width=w, thickness=0.5, color=_BORDER, spaceAfter=6))

        for code in osha_codes:
            # Code header
            code_header = Table(
                [[
                    Paragraph(code.get("code", ""), s["osha_code"]),
                    Paragraph(
                        f"{_fmt_currency(code.get('fine_min_usd', 0))} – "
                        f"{_fmt_currency(code.get('fine_max_usd', 0))}",
                        ParagraphStyle("fine", fontSize=11, textColor=colors.HexColor("#fbbf24"),
                                       fontName="Helvetica-Bold"),
                    ),
                ]],
                colWidths=[w * 0.6, w * 0.4],
            )
            code_header.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), _DARK),
                ("TOPPADDING",    (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING",   (0, 0), (-1, -1), 12),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN",         (1, 0), (1, 0), "RIGHT"),
            ]))
            story.append(code_header)

            # Code body
            title       = code.get("title", "")
            plain       = code.get("plain_english", "")
            description = code.get("description", "")
            actions     = code.get("corrective_actions", [])

            body_rows = []
            if title:
                body_rows.append([Paragraph(title, ParagraphStyle("ct", fontSize=11, fontName="Helvetica-Bold", textColor=_TEXT))])
            if plain:
                body_rows.append([Paragraph(plain, s["osha_body"])])
            if description:
                body_rows.append([Paragraph(f'<i>"{description}"</i>', s["small"])])
            if actions:
                action_text = "<b>Corrective actions:</b> " + " • ".join(actions)
                body_rows.append([Paragraph(action_text, s["osha_body"])])

            body_table = Table(body_rows, colWidths=[w])
            body_table.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), _LIGHT),
                ("BOX",           (0, 0), (-1, -1), 0.5, _BORDER),
                ("TOPPADDING",    (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING",   (0, 0), (-1, -1), 12),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
            ]))
            story.append(body_table)
            story.append(Spacer(1, 8))

    # ── Footer / disclaimer ───────────────────────────────────────────────────
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width=w, thickness=0.5, color=_BORDER, spaceAfter=6))
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    story.append(Paragraph(
        f"Generated by SafeSight AI · {generated_at} · Event ID: {event.get('event_id', '')}",
        s["small"],
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "<b>Disclaimer:</b> Fine amounts reflect the 2024 OSHA adjusted penalty schedule for "
        "serious violations. Actual penalties depend on severity, employer history, good-faith "
        "abatement efforts, and OSHA area office discretion. This report is for internal safety "
        "management use only and does not constitute legal advice.",
        s["disclaimer"],
    ))

    doc.build(story)
    return buf.getvalue()
