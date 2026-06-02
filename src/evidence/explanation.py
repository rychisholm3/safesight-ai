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
    Handles missing_ppe, zone_intrusion, and near_miss event types.
    """
    etype = event.get("event_type", "")
    if etype == "near_miss":
        return _build_near_miss_explanation(event)

    items: list[ExplanationItem] = []

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


# ── Near-miss explanation ─────────────────────────────────────────────────────

_NEAR_MISS_TYPE_TEXT: dict[str, tuple[str, str]] = {
    # zone_rule → (headline, detail)
    "proximity": (
        "Vehicle proximity hazard detected",
        "A worker was detected within a dangerous distance of a vehicle or heavy "
        "equipment without physical contact. This constitutes a near-miss event — "
        "a situation that could have resulted in a struck-by or crush fatality.",
    ),
    "trajectory": (
        "Collision trajectory predicted",
        "Two workers' movement paths were predicted to converge to within a "
        "collision-risk distance within the next few seconds based on their current "
        "speed and direction. No contact occurred, but the hazard was imminent.",
    ),
    "zone_entry": (
        "Brief restricted zone entry",
        "A worker's foot momentarily crossed the boundary of a no-entry restricted "
        "zone and exited safely. This near-miss captures the event even when the "
        "dwell time was too short to trigger a full zone-intrusion alarm.",
    ),
}

_NEAR_MISS_ACTION: dict[str, str] = {
    "proximity": (
        "Establish a minimum 2-metre exclusion zone around all moving vehicles. "
        "Use spotters when vehicles reverse or manoeuvre near pedestrian routes. "
        "Consider physical separation barriers (jersey barriers, cones) between "
        "vehicle travel lanes and pedestrian access routes."
    ),
    "trajectory": (
        "Brief workers on situational awareness and looking both ways before "
        "crossing travel lanes. Review site traffic management plan. Consider "
        "separate pedestrian routes that do not cross vehicle paths."
    ),
    "zone_entry": (
        "Reinforce zone boundaries with physical barriers (not just tape or cones). "
        "Brief the crew on zone locations before the next shift. Install high-"
        "visibility signage at every access point to the restricted area."
    ),
}

_NEAR_MISS_GDC_TEXT = (
    "Near-miss events trigger employer obligations under OSH Act Section 5(a)(1) "
    "(General Duty Clause) — employers must address known hazards that are likely "
    "to cause death or serious physical harm, even before an injury occurs. "
    "Failure to act on recorded near-miss data can be used as evidence of wilful "
    "non-compliance in subsequent OSHA inspections."
)


def _build_near_miss_explanation(event: dict) -> list[ExplanationItem]:
    items: list[ExplanationItem] = []

    zone_rule   = event.get("zone_rule") or "_default"
    severity    = event.get("severity", "WARNING")
    confidence  = float(event.get("confidence") or 0.0)
    start_frame = event.get("start_frame", 0) or 0
    end_frame   = event.get("end_frame")
    zone_id     = event.get("zone_id")
    osha_codes  = event.get("osha_codes") or []

    headline, detail = _NEAR_MISS_TYPE_TEXT.get(
        zone_rule,
        ("Near-miss hazard detected", "A potential safety hazard was detected."),
    )

    # 1. What happened
    items.append(ExplanationItem(
        category="Near-miss detected",
        text=f"{headline}. {detail}",
        icon="⚡",
    ))

    # 2. Location context
    if zone_id:
        items.append(ExplanationItem(
            category="Location",
            text=f"Incident occurred in or adjacent to zone '{zone_id}'.",
            icon="📍",
        ))
    else:
        items.append(ExplanationItem(
            category="Location",
            text="Incident occurred in the general work area (not zone-specific).",
            icon="📍",
        ))

    # 3. Severity
    sev_text = (
        "CRITICAL — the hazard was imminent and could have caused a fatality or "
        "serious injury within seconds without corrective action."
        if severity == "CRITICAL" else
        "WARNING — the hazard was developing and required prompt intervention to "
        "prevent escalation to a serious incident."
    )
    items.append(ExplanationItem(
        category="Severity assessment",
        text=sev_text,
        icon="🚨" if severity == "CRITICAL" else "⚠️",
    ))

    # 4. Recommended action
    action = _NEAR_MISS_ACTION.get(zone_rule, "Review site safety procedures and brief workers.")
    items.append(ExplanationItem(
        category="Recommended action",
        text=action,
        icon="🛠️",
    ))

    # 5. Regulatory obligation
    if osha_codes:
        codes_str = ", ".join(osha_codes)
        items.append(ExplanationItem(
            category="Regulatory obligation",
            text=f"{_NEAR_MISS_GDC_TEXT} Applicable codes: {codes_str}.",
            icon="📋",
        ))
    else:
        items.append(ExplanationItem(
            category="Regulatory obligation",
            text=_NEAR_MISS_GDC_TEXT,
            icon="📋",
        ))

    # 6. Important note — no fine, but liability exists
    items.append(ExplanationItem(
        category="Fine exposure",
        text=(
            "No OSHA fine is issued for near-miss events themselves — however, "
            "failure to investigate and address the root cause may result in fines "
            "under the General Duty Clause if a subsequent injury occurs. "
            "Document this near-miss in your site safety log and share it with "
            "your insurance carrier."
        ),
        icon="⚖️",
    ))

    # 7. Detection confidence
    pct        = round(confidence * 100)
    conf_label = "high" if pct >= 70 else "medium" if pct >= 45 else "low"
    items.append(ExplanationItem(
        category="Detection confidence",
        text=f"{pct}% ({conf_label} confidence). The AI detection model assigned this score.",
        icon="🎯",
    ))

    # 8. Duration
    if end_frame is not None:
        duration = end_frame - start_frame
        items.append(ExplanationItem(
            category="Duration",
            text=(
                f"Near-miss was active for approximately {duration} frames "
                f"(frame {start_frame} → {end_frame}). Worker exited the hazard safely."
            ),
            icon="⏱️",
        ))
    else:
        items.append(ExplanationItem(
            category="Duration",
            text=(
                f"Near-miss is currently ACTIVE — started at frame {start_frame}. "
                "Hazard has not yet resolved."
            ),
            icon="⏱️",
        ))

    return items
