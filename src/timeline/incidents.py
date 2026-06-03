"""
Incident story detection — groups related events from the same worker into
multi-event incidents with a plain-English narrative summary.

An "incident" is defined as two or more events from the same track_id whose
timestamps fall within INCIDENT_WINDOW_MINUTES of each other.  Multiple events
can chain into a single incident if each consecutive pair is within the window.

Narrative rules
---------------
• If severity increases over the incident (WARNING → CRITICAL) → "Escalating"
• If the same violation type repeats → "Repeated"
• Otherwise → generic multi-event summary

The narrative is generated deterministically from stored event data — no LLM
call required.  The AI Copilot (Phase 5) can be used for deeper analysis.
"""
import uuid
from datetime import datetime, timezone

INCIDENT_WINDOW_MINUTES: int = 30   # consecutive events within this window = one incident
MIN_EVENTS_PER_INCIDENT: int = 2    # minimum group size to qualify as an incident

_SEV_RANK = {"WARNING": 0, "CRITICAL": 1}

_TYPE_LABEL = {
    "missing_ppe":    "PPE violation",
    "zone_intrusion": "zone intrusion",
    "near_miss":      "near-miss",
}

_NEAR_MISS_SUB = {
    "proximity":   "vehicle proximity",
    "trajectory":  "collision trajectory",
    "zone_entry":  "zone entry",
}


def _parse_ts(iso: str) -> datetime:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def _is_escalating(events: list[dict]) -> bool:
    """True if severity increases at any point across the event sequence."""
    sevs = [_SEV_RANK.get(e.get("severity", "WARNING"), 0) for e in events]
    return any(sevs[i] < sevs[i + 1] for i in range(len(sevs) - 1))


def _event_label(event: dict) -> str:
    """One-line description of a single event."""
    etype = event.get("event_type", "")
    if etype == "missing_ppe":
        items = event.get("missing_ppe") or []
        ppe_str = ", ".join(items) if items else "PPE"
        return f"Missing {ppe_str}"
    if etype == "near_miss":
        sub = _NEAR_MISS_SUB.get(event.get("zone_rule") or "", "near-miss")
        return f"Near miss — {sub}"
    zone = event.get("zone_id")
    return f"Zone intrusion{f' ({zone})' if zone else ''}"


def _generate_narrative(
    track_id: int,
    events: list[dict],
    duration_minutes: float,
    escalating: bool,
) -> str:
    n = len(events)
    types = [e.get("event_type", "") for e in events]

    ppe_count  = types.count("missing_ppe")
    zone_count = types.count("zone_intrusion")
    nm_count   = types.count("near_miss")

    zones   = list(dict.fromkeys(e.get("zone_id") for e in events if e.get("zone_id")))
    zone_str = (
        f" in zone '{zones[0]}'" if len(zones) == 1
        else f" across {len(zones)} zones" if zones
        else ""
    )

    # Build event-type summary
    parts: list[str] = []
    if ppe_count:
        parts.append(f"{ppe_count} PPE violation{'s' if ppe_count > 1 else ''}")
    if zone_count:
        parts.append(f"{zone_count} zone intrusion{'s' if zone_count > 1 else ''}")
    if nm_count:
        parts.append(f"{nm_count} near-miss{'es' if nm_count > 1 else ''}")
    event_summary = ", ".join(parts)

    dur_str = f"{duration_minutes:.0f} minute{'s' if duration_minutes != 1 else ''}"

    # Pattern description
    all_same_type = len(set(types)) == 1
    if escalating:
        pattern = (
            f"Escalating incident — Worker #{track_id} triggered {n} events over "
            f"{dur_str}{zone_str}: {event_summary}. "
            "Severity increased during the incident window. "
            "Immediate supervisor intervention is required before this worker continues."
        )
    elif all_same_type and n >= 3:
        t = _TYPE_LABEL.get(types[0], types[0])
        pattern = (
            f"Repeated {t}s — Worker #{track_id} triggered {n} {t}s over "
            f"{dur_str}{zone_str}. "
            "Repeated violations of the same type suggest the root cause has not been "
            "addressed. Brief the worker and verify corrective action before the next task."
        )
    else:
        pattern = (
            f"Multi-event incident — Worker #{track_id} triggered {n} events over "
            f"{dur_str}{zone_str}: {event_summary}. "
            "Review this sequence with the worker and log any corrective action taken."
        )

    return pattern


def detect_incidents(
    events: list[dict],
    window_minutes: int = INCIDENT_WINDOW_MINUTES,
    min_events:     int = MIN_EVENTS_PER_INCIDENT,
) -> list[dict]:
    """
    Return a list of incident dicts from *events*.

    Each incident contains:
      incident_id, track_id, start_time, end_time, duration_minutes,
      event_count, severity, is_escalating, event_types, zones,
      narrative, events (list of event dicts)

    Events within *events* that are NOT part of any incident are returned
    as singleton incidents with ``is_incident = False`` so the caller can
    choose whether to show them.
    """
    if not events:
        return []

    # Sort by track_id then timestamp
    sorted_events = sorted(
        events,
        key=lambda e: (e.get("track_id", 0), e.get("created_at", "")),
    )

    # Chain events into groups: consecutive events from same track_id within window
    groups: list[list[dict]] = []
    current_group: list[dict] = []

    for ev in sorted_events:
        if not current_group:
            current_group = [ev]
            continue

        same_worker = ev.get("track_id") == current_group[-1].get("track_id")
        if same_worker:
            dt = _parse_ts(ev.get("created_at", ""))
            dt_prev = _parse_ts(current_group[-1].get("created_at", ""))
            gap_min = abs((dt - dt_prev).total_seconds()) / 60
            if gap_min <= window_minutes:
                current_group.append(ev)
                continue

        groups.append(current_group)
        current_group = [ev]

    if current_group:
        groups.append(current_group)

    # Build incident dicts for groups that qualify
    incidents: list[dict] = []
    for group in groups:
        track_id = group[0].get("track_id")

        if len(group) < min_events:
            continue  # singleton — not an incident

        t_start = _parse_ts(group[0].get("created_at", ""))
        t_end   = _parse_ts(group[-1].get("created_at", ""))
        dur_min = abs((t_end - t_start).total_seconds()) / 60

        escalating = _is_escalating(group)

        sev_ranks = [_SEV_RANK.get(e.get("severity", "WARNING"), 0) for e in group]
        max_sev   = "CRITICAL" if max(sev_ranks) > 0 else "WARNING"

        etypes = list(dict.fromkeys(e.get("event_type", "") for e in group))
        zones  = list(dict.fromkeys(e.get("zone_id") for e in group if e.get("zone_id")))

        narrative = _generate_narrative(track_id, group, dur_min, escalating)

        incidents.append({
            "incident_id":      uuid.uuid4().hex[:12],
            "track_id":         track_id,
            "start_time":       group[0].get("created_at", ""),
            "end_time":         group[-1].get("created_at", ""),
            "duration_minutes": round(dur_min, 1),
            "event_count":      len(group),
            "severity":         max_sev,
            "is_escalating":    escalating,
            "event_types":      etypes,
            "zones":            zones,
            "narrative":        narrative,
            "events":           group,
        })

    # Sort incidents by start_time
    incidents.sort(key=lambda i: i["start_time"])
    return incidents
