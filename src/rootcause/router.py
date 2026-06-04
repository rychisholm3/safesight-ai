"""
Root Cause Analysis router — Phase 9.

GET  /rootcause/analysis?days=7   statistical pattern data
POST /rootcause/summary?days=7    AI-generated (or deterministic) root cause report
"""
import logging
import sqlite3

from fastapi import APIRouter, Depends, Query

from src.auth.dependencies import require_auth
from src.auth.models import User
from src.rootcause.analyzer import RootCauseAnalyzer
from src.rootcause.summary import generate_summary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rootcause", tags=["rootcause"])


# ── Dependency stubs — overridden by main.py ─────────────────────────────────

def _get_conn() -> sqlite3.Connection:  # pragma: no cover
    raise NotImplementedError


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/analysis")
def get_analysis(
    _: User = Depends(require_auth),
    conn: sqlite3.Connection = Depends(_get_conn),
    days: int = Query(default=7, ge=1, le=90),
):
    """Return statistical violation pattern analysis for the last N days."""
    analyzer = RootCauseAnalyzer(conn)
    analysis = analyzer.analyse(days)

    return {
        "days_analysed":      analysis.days_analysed,
        "event_total":        analysis.event_total,
        "computed_at":        analysis.computed_at,
        "hour_buckets": [
            {
                "hour":    b.hour,
                "label":   b.label,
                "count":   b.count,
                "period":  b.period,
                "z_score": b.z_score,
                "is_peak": b.is_peak,
            }
            for b in analysis.hour_buckets
        ],
        "shift_periods": [
            {
                "name":          s.name,
                "count":         s.count,
                "avg_per_hour":  s.avg_per_hour,
                "risk_level":    s.risk_level,
                "dominant_type": s.dominant_type,
            }
            for s in analysis.shift_periods
        ],
        "zone_patterns": [
            {
                "zone_id":     z.zone_id,
                "count":       z.count,
                "ppe_count":   z.ppe_count,
                "zone_count":  z.zone_count,
                "nm_count":    z.nm_count,
                "peak_hour":   z.peak_hour,
                "peak_period": z.peak_period,
            }
            for z in analysis.zone_patterns
        ],
        "global_events":     analysis.global_events,
        "worker_patterns": [
            {
                "track_id":        w.track_id,
                "violation_count": w.violation_count,
                "segment":         w.segment,
                "dominant_type":   w.dominant_type,
                "primary_zone":    w.primary_zone,
                "peak_hour":       w.peak_hour,
                "peak_period":     w.peak_period,
            }
            for w in analysis.worker_patterns
        ],
        "top_peak_periods":  analysis.top_peak_periods,
        "top_hotspot_zones": analysis.top_hotspot_zones,
    }


@router.post("/summary")
def get_summary(
    _: User = Depends(require_auth),
    conn: sqlite3.Connection = Depends(_get_conn),
    days: int = Query(default=7, ge=1, le=90),
):
    """
    Generate a root cause summary for the last N days.
    Uses Claude when ANTHROPIC_API_KEY is set; deterministic fallback otherwise.
    """
    analyzer = RootCauseAnalyzer(conn)
    analysis = analyzer.analyse(days)
    return generate_summary(analysis)
