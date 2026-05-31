"""
Build a structured plain-text site context block for Claude.

The context is rebuilt from live DB data on every /copilot/ask request so
Claude always sees current violation counts, risk scores, and zone config.
Claude's ephemeral prompt caching means repeated identical contexts
(same events, same risk scores) still get a cache hit within the 5-min TTL.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.risk.engine import RiskEngine
from src.store import EventStore

logger = logging.getLogger(__name__)


def build_site_context(
    store: EventStore,
    risk_engine: RiskEngine,
    zones_path: Path,
    max_events: int = 50,
) -> str:
    """Return a structured text block describing the current state of the site."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [f"=== SAFESIGHT LIVE SITE CONTEXT (as of {now}) ===\n"]

    # ── Recent events ──────────────────────────────────────────────────────
    events = store.get_events(limit=max_events)
    lines.append(f"RECENT EVENTS (last {len(events)} of up to {max_events}):")
    if not events:
        lines.append("  (no events recorded yet)")
    else:
        for e in events:
            ts        = (e.get("created_at") or "")[:16]
            etype     = e["event_type"].replace("_", " ").upper()
            sev       = e.get("severity", "WARNING")
            tid       = e.get("track_id", "?")
            zone      = e.get("zone_id") or "global"
            ppe_items = e.get("missing_ppe") or []
            ppe       = ", ".join(ppe_items) if ppe_items else "-"
            osha_list = e.get("osha_codes") or []
            osha      = ", ".join(osha_list) if osha_list else "-"
            fine_lo   = e.get("fine_min_usd", 0)
            fine_hi   = e.get("fine_max_usd", 0)
            conf      = e.get("confidence", 0.0)
            status    = "OPEN" if e.get("end_frame") is None else "CLOSED"
            lines.append(
                f"  [{ts}] {sev} {etype} | Worker #{tid} | Zone: {zone} | "
                f"PPE missing: {ppe} | OSHA: {osha} | "
                f"Fine: ${fine_lo:,}–${fine_hi:,} | Conf: {conf:.0%} | {status}"
            )

    # ── Aggregate stats from the shown events ──────────────────────────────
    lines.append("")
    total      = len(events)
    open_count = sum(1 for e in events if e.get("end_frame") is None)
    by_type: dict[str, int] = {}
    for e in events:
        by_type[e["event_type"]] = by_type.get(e["event_type"], 0) + 1
    total_fines_lo = sum(e.get("fine_min_usd", 0) for e in events)
    total_fines_hi = sum(e.get("fine_max_usd", 0) for e in events)
    lines.append("AGGREGATE STATISTICS (from events shown above):")
    lines.append(
        f"  Total events: {total} | Active: {open_count} | Closed: {total - open_count}"
    )
    lines.append(
        f"  PPE violations: {by_type.get('missing_ppe', 0)} | "
        f"Zone intrusions: {by_type.get('zone_intrusion', 0)}"
    )
    lines.append(
        f"  Cumulative OSHA fine exposure: ${total_fines_lo:,}–${total_fines_hi:,}"
    )

    # ── Site risk summary ──────────────────────────────────────────────────
    try:
        summary = risk_engine.site_summary()
        lines.append("")
        lines.append("SITE RISK SUMMARY (computed by risk engine):")
        lines.append(
            f"  Overall risk level: {summary.overall_risk_level} "
            f"(score {summary.overall_risk_score}/100)"
        )
        lines.append(
            f"  Violations last 24 h: {summary.total_violations_24h} | "
            f"Last 7 days: {summary.total_violations_7d}"
        )
        lines.append(
            f"  Highest-risk zone: {summary.highest_risk_zone or 'none identified'}"
        )
        rising = summary.rising_risk_zones
        lines.append(
            f"  Rising-risk zones: {', '.join(rising) if rising else 'none'}"
        )
        lines.append(f"  Repeat offenders right now: {summary.repeat_offender_count}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Site summary unavailable: %s", exc)

    # ── Per-zone risk scores ───────────────────────────────────────────────
    try:
        zone_risks = risk_engine.zone_risks()
        if zone_risks:
            lines.append("")
            lines.append("ZONE RISK SCORES (sorted by risk, highest first):")
            for z in zone_risks:
                trend_str = f"{z.trend} ({z.trend_pct:+.0f}%)"
                lines.append(
                    f"  '{z.zone_id}': score={z.risk_score}/100 [{z.risk_level}] | "
                    f"trend={trend_str} | 24 h={z.violations_24h} | 7 d={z.violations_7d}"
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Zone risks unavailable: %s", exc)

    # ── Repeat offenders ───────────────────────────────────────────────────
    try:
        offenders = risk_engine.repeat_offenders()
        if offenders:
            lines.append("")
            lines.append("REPEAT OFFENDERS (≥3 violations in last 24 h):")
            for w in offenders:
                zone_str = f" | most-flagged zone: {w.most_common_zone}" if w.most_common_zone else ""
                lines.append(
                    f"  Worker #{w.track_id}: {w.violations_24h} violations today "
                    f"({w.violation_count} total all-time) | "
                    f"primary violation: {w.most_common_type}{zone_str}"
                )
        else:
            lines.append("")
            lines.append("REPEAT OFFENDERS: none in the last 24 h.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Repeat offenders unavailable: %s", exc)

    # ── Zone configuration ─────────────────────────────────────────────────
    try:
        if zones_path.exists():
            zones_data = json.loads(zones_path.read_text())
            global_ppe = zones_data.get("required_ppe", [])
            zones_list = zones_data.get("zones", [])
            lines.append("")
            lines.append("CONFIGURED ZONES:")
            lines.append(
                f"  Site-wide PPE requirement: "
                f"{', '.join(global_ppe) if global_ppe else 'none'}"
            )
            for z in zones_list:
                rule     = z.get("rule", "unknown")
                req_ppe  = z.get("required_ppe", [])
                ppe_str  = f" — requires: {', '.join(req_ppe)}" if req_ppe else ""
                lines.append(
                    f"  '{z.get('name', z.get('id'))}' [{z.get('id')}]: "
                    f"rule={rule}{ppe_str}"
                )
        else:
            lines.append("")
            lines.append("CONFIGURED ZONES: zones.json not found.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Zone config unavailable: %s", exc)

    return "\n".join(lines)
