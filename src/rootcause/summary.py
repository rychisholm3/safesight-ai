"""
Root cause summary generator.

Deterministic fallback always available; Claude-powered narrative when
ANTHROPIC_API_KEY is set (reuses the same client pattern as the copilot).
"""
import json
import logging
import os

from src.rootcause.analyzer import RootCauseAnalysis

logger = logging.getLogger(__name__)

_SEGMENT_LABEL = {
    "isolated":  "Isolated incidents (1 violation)",
    "recurring": "Recurring risk (2–4 violations)",
    "chronic":   "Chronic offenders (5+ violations)",
}

_RISK_RECS: dict[str, list[str]] = {
    "Shift Start": [
        "Conduct a mandatory PPE check and toolbox talk at the start of every shift.",
        "Assign a safety monitor to each entry point for the first 30 minutes of each shift.",
        "Post large-format PPE reminder signs at site entrance gates.",
    ],
    "Lunch": [
        "Brief workers on re-entry procedures before lunch breaks end.",
        "Ensure PPE stations are stocked and visible at the return-to-work entry points.",
        "Consider a brief 2-minute post-lunch safety reminder over the site PA system.",
    ],
    "Shift End": [
        "Increase supervisor visibility in the final hour — fatigue-driven violations peak here.",
        "Implement a 'secure your area' checklist before workers leave their stations.",
        "Consider staggered shift-end times to reduce crowding and near-miss risk.",
    ],
    "Afternoon": [
        "Schedule a mid-afternoon refresher break to counteract fatigue.",
        "Rotate workers between tasks to maintain alertness in the hotspot zones.",
    ],
}

_GENERIC_RECS = [
    "Increase supervisor presence in the highest-risk zones during peak violation hours.",
    "Run a site-wide PPE audit and replace any worn or missing equipment.",
    "Hold a toolbox talk reviewing the top violation patterns with the full crew.",
    "Review the traffic management plan for zones with near-miss incidents.",
    "Document all repeat-offender violations and schedule formal retraining sessions.",
]


def _deterministic_summary(analysis: RootCauseAnalysis) -> dict:
    """Generate a structured root cause report without any AI call."""
    recs: list[str] = []

    # Time-based recommendations
    for period in analysis.top_peak_periods:
        recs.extend(_RISK_RECS.get(period, []))

    # Chronic worker recommendations
    chronic = [w for w in analysis.worker_patterns if w.segment == "chronic"]
    if chronic:
        recs.append(
            f"Schedule mandatory retraining for "
            f"{len(chronic)} chronic offender{'s' if len(chronic) > 1 else ''} "
            f"(Worker{'s' if len(chronic) > 1 else ''} "
            f"#{', #'.join(str(w.track_id) for w in chronic[:5])})."
        )

    # Zone-based
    for zone in analysis.top_hotspot_zones[:2]:
        recs.append(
            f"Conduct a dedicated safety walkthrough of zone '{zone}' — "
            f"it is the highest-risk location on site."
        )

    # Fill with generic if few specific ones
    for rec in _GENERIC_RECS:
        if len(recs) >= 5:
            break
        if rec not in recs:
            recs.append(rec)

    # Root causes
    root_causes: list[dict] = []
    for period in analysis.top_peak_periods[:3]:
        sp = next((s for s in analysis.shift_periods if s.name == period), None)
        if sp:
            root_causes.append({
                "title":    f"Elevated violations during {period}",
                "evidence": f"{sp.count} events ({sp.avg_per_hour:.1f}/hour) — "
                            f"risk level: {sp.risk_level}. "
                            f"Primary violation type: {sp.dominant_type.replace('_', ' ')}.",
                "type":     "time_pattern",
            })

    for zone in analysis.top_hotspot_zones[:2]:
        zp = next((z for z in analysis.zone_patterns if z.zone_id == zone), None)
        if zp:
            root_causes.append({
                "title":    f"Zone '{zone}' is a persistent hotspot",
                "evidence": f"{zp.count} events — PPE: {zp.ppe_count}, "
                            f"intrusions: {zp.zone_count}, near-misses: {zp.nm_count}. "
                            f"Peak hour: {zp.peak_hour:02d}:00 ({zp.peak_period}).",
                "type":     "location_pattern",
            })

    if chronic:
        root_causes.append({
            "title":    f"{len(chronic)} chronic offenders driving repeat violations",
            "evidence": f"Workers #{', #'.join(str(w.track_id) for w in chronic[:3])} "
                        f"each have 5+ violations in the analysis window, "
                        f"suggesting inadequate initial training or persistent non-compliance.",
            "type":     "worker_pattern",
        })

    segments = {s: 0 for s in ("isolated", "recurring", "chronic")}
    for w in analysis.worker_patterns:
        segments[w.segment] += 1

    return {
        "generated_by":    "deterministic",
        "days_analysed":   analysis.days_analysed,
        "event_total":     analysis.event_total,
        "root_causes":     root_causes[:5],
        "recommendations": recs[:6],
        "worker_segments": {_SEGMENT_LABEL[k]: v for k, v in segments.items()},
        "top_peak_periods": analysis.top_peak_periods,
        "top_hotspot_zones": analysis.top_hotspot_zones,
        "computed_at":     analysis.computed_at,
    }


def _ai_context(analysis: RootCauseAnalysis) -> str:
    """Serialise analysis into a compact text block for Claude."""
    lines = [
        f"Analysis window: {analysis.days_analysed} days",
        f"Total events: {analysis.event_total}",
        "",
        "SHIFT PERIOD BREAKDOWN (violations per period):",
    ]
    for sp in analysis.shift_periods:
        if sp.count > 0:
            lines.append(
                f"  {sp.name}: {sp.count} events ({sp.avg_per_hour}/hr) "
                f"[{sp.risk_level}] dominant type: {sp.dominant_type}"
            )
    lines.append("")
    lines.append("ZONE HOTSPOTS:")
    for zp in analysis.zone_patterns[:5]:
        lines.append(
            f"  {zp.zone_id}: {zp.count} events "
            f"(PPE={zp.ppe_count} zone={zp.zone_count} near_miss={zp.nm_count}) "
            f"peak hour: {zp.peak_hour:02d}:00 {zp.peak_period}"
        )
    lines.append("")
    lines.append("WORKER SEGMENTS (by violation frequency):")
    chronic  = [w for w in analysis.worker_patterns if w.segment == "chronic"]
    recurr   = [w for w in analysis.worker_patterns if w.segment == "recurring"]
    isolated = [w for w in analysis.worker_patterns if w.segment == "isolated"]
    lines.append(f"  Chronic (5+):      {len(chronic)} workers")
    lines.append(f"  Recurring (2-4):   {len(recurr)} workers")
    lines.append(f"  Isolated (1):      {len(isolated)} workers")
    for w in chronic[:5]:
        lines.append(
            f"  Worker #{w.track_id}: {w.violation_count} violations, "
            f"primary type={w.dominant_type}, zone={w.primary_zone}, "
            f"peak hour={w.peak_hour:02d}:00"
        )
    return "\n".join(lines)


def generate_summary(analysis: RootCauseAnalysis) -> dict:
    """
    Return structured root cause summary.
    Uses Claude if ANTHROPIC_API_KEY is set; deterministic fallback otherwise.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        logger.info("No ANTHROPIC_API_KEY — using deterministic root cause summary")
        return _deterministic_summary(analysis)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        ctx    = _ai_context(analysis)

        system = (
            "You are a construction safety analyst. "
            "Analyse the violation pattern data provided and identify root causes "
            "with specific, evidence-backed intervention recommendations. "
            "Be concise and actionable — safety officers need to act on this today."
        )

        prompt = f"""Based on this {analysis.days_analysed}-day violation analysis, provide a root cause report.

{ctx}

Respond with a JSON object with exactly these fields:
{{
  "root_causes": [
    {{"title": "...", "evidence": "...", "type": "time_pattern|location_pattern|worker_pattern"}}
  ],
  "recommendations": ["...", "..."],
  "executive_summary": "2-3 sentence plain-English summary of the main safety risk pattern and what to do."
}}

Include 3-5 root causes and 4-6 prioritised recommendations. Be specific — name hours, zones, and worker IDs from the data."""

        resp = client.messages.create(
            model      = "claude-opus-4-7",
            max_tokens = 1024,
            system     = system,
            messages   = [{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            raw = raw.rstrip("`").strip()

        ai_result = json.loads(raw)

        # Merge deterministic scaffolding with AI content
        det = _deterministic_summary(analysis)
        return {
            **det,
            "generated_by":      "claude",
            "root_causes":       ai_result.get("root_causes",    det["root_causes"]),
            "recommendations":   ai_result.get("recommendations", det["recommendations"]),
            "executive_summary": ai_result.get("executive_summary", ""),
        }

    except Exception as exc:
        logger.warning("AI summary failed (%s) — falling back to deterministic", exc)
        result = _deterministic_summary(analysis)
        result["ai_error"] = str(exc)
        return result
