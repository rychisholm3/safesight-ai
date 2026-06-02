"""
Reason breakdown builder — turns a raw event dict into a structured,
human-readable explanation list suitable for the UI and PDF export.
"""
from dataclasses import dataclass


@dataclass
class ExplanationItem:
    category: str
    text: str
    icon: str = ""


def build_explanation(event: dict) -> list[ExplanationItem]:
    """
    Return an ordered list of explanation items for a single event dict.
    Works entirely from the stored fields — no extra DB queries needed.
    """
    items: list[ExplanationItem] = []

    etype       = event.get("event_type", "")
    missing_ppe = event.get("missing_ppe") or []
    zone_id     = event.get("zone_id")
    zone_rule   = event.get("zone_rule")
    severity    = event.get("severity", "WARNING")
    confidence  = float(event.get("confidence") or 0.0)
    fine_min    = event.get("fine_min_usd", 0) or 0
    fine_max    = event.get("fine_max_usd", 0) or 0
    osha_codes  = event.get("osha_codes") or []
    start_frame = event.get("start_frame", 0) or 0
    end_frame   = event.get("end_frame")

    # ── 1. What was detected ─────────────────────────────────────────────────
    if etype == "missing_ppe":
        ppe_str = ", ".join(missing_ppe) if missing_ppe else "required PPE"
        items.append(ExplanationItem(
            category="Violation detected",
            text=(
                f"Worker #{event.get('track_id')} was observed without required "
                f"personal protective equipment: {ppe_str}."
            ),
            icon="🦺",
        ))
    else:
        zone_part = f" (zone: '{zone_id}')" if zone_id else ""
        items.append(ExplanationItem(
            category="Violation detected",
            text=(
                f"Worker #{event.get('track_id')} entered a restricted area{zone_part} "
                "in breach of site safety rules."
            ),
            icon="⛔",
        ))

    # ── 2. Zone / location context ───────────────────────────────────────────
    if zone_id:
        _RULE_DESC: dict[str, str] = {
            "no_entry":    "This is a no-entry restricted zone. Unauthorised entry poses serious risk of struck-by, crush, or fall injuries.",
            "require_ppe": f"This zone requires additional PPE beyond the site-wide minimum. The worker was missing: {', '.join(missing_ppe) or 'required items'}.",
        }
        rule_text = _RULE_DESC.get(zone_rule or "", f"Zone rule: {zone_rule or 'unknown'}.")
        items.append(ExplanationItem(
            category="Zone context",
            text=f"Zone '{zone_id}': {rule_text}",
            icon="📍",
        ))
    else:
        items.append(ExplanationItem(
            category="Zone context",
            text=(
                "This is a site-wide PPE requirement — all workers on site must "
                "comply with this rule regardless of their current location."
            ),
            icon="📍",
        ))

    # ── 3. Severity rationale ────────────────────────────────────────────────
    _SEV_TEXT = {
        "CRITICAL": (
            "CRITICAL severity indicates an imminent safety risk. "
            "Unauthorised zone entries expose workers to vehicle strikes, "
            "falls from height, crush injuries, and other life-threatening hazards. "
            "Immediate supervisor intervention is required."
        ),
        "WARNING": (
            "WARNING severity indicates a significant safety violation. "
            "Missing PPE removes the last line of defence against injury. "
            "The violation must be corrected before work continues."
        ),
    }
    items.append(ExplanationItem(
        category="Severity assessment",
        text=_SEV_TEXT.get(severity, f"Severity: {severity}."),
        icon="🚨" if severity == "CRITICAL" else "⚠️",
    ))

    # ── 4. Regulatory exposure ────────────────────────────────────────────────
    if osha_codes:
        codes_str = ", ".join(osha_codes)
        items.append(ExplanationItem(
            category="Regulatory exposure",
            text=(
                f"This violation triggers {len(osha_codes)} OSHA "
                f"regulation{'s' if len(osha_codes) > 1 else ''}: {codes_str}. "
                "See the OSHA cards below for full citation details."
            ),
            icon="📋",
        ))

    # ── 5. Financial exposure ─────────────────────────────────────────────────
    if fine_max > 0:
        items.append(ExplanationItem(
            category="Financial exposure",
            text=(
                f"Estimated OSHA penalty: ${fine_min:,}–${fine_max:,} per violation "
                "(2024 adjusted serious-violation schedule). "
                "Willful or repeat violations can reach ten times this amount."
            ),
            icon="⚖️",
        ))

    # ── 6. Detection confidence ───────────────────────────────────────────────
    pct        = round(confidence * 100)
    conf_label = "high" if pct >= 70 else "medium" if pct >= 45 else "low"
    items.append(ExplanationItem(
        category="Detection confidence",
        text=(
            f"{pct}% ({conf_label} confidence). "
            "The AI detection model assigned this score based on the clarity of "
            "the image, the worker's proximity to the camera, and the visibility "
            "of their equipment."
        ),
        icon="🎯",
    ))

    # ── 7. Duration ────────────────────────────────────────────────────────────
    if end_frame is not None:
        duration = end_frame - start_frame
        items.append(ExplanationItem(
            category="Duration",
            text=(
                f"Violation was active for approximately {duration} frames "
                f"(frame {start_frame} → {end_frame}). Status: CLOSED."
            ),
            icon="⏱️",
        ))
    else:
        items.append(ExplanationItem(
            category="Duration",
            text=(
                f"Violation is currently ACTIVE — started at frame {start_frame} "
                "and has not yet been resolved."
            ),
            icon="⏱️",
        ))

    return items
