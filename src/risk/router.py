"""
FastAPI router for Phase 3 Predictive Risk Engine.

GET /risk/zones          — risk score + trend for every zone
GET /risk/summary        — site-wide snapshot
GET /risk/workers/offenders — repeat offenders in last 24 h
"""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from src.auth.dependencies import require_auth
from src.auth.models import User
from src.risk.engine import RiskEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/risk", tags=["risk"])


# ── Dependency injected by main.py ────────────────────────────────────────────

def _get_risk_engine() -> RiskEngine:  # pragma: no cover
    raise RuntimeError("risk_engine not wired — check src/api/main.py")


RiskEngineDep = Annotated[RiskEngine, Depends(_get_risk_engine)]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/zones")
def get_zone_risks(
    engine: RiskEngineDep,
    _: User = Depends(require_auth),
):
    zones = engine.zone_risks()
    return [
        {
            "zone_id":           z.zone_id,
            "risk_score":        z.risk_score,
            "risk_level":        z.risk_level,
            "trend":             z.trend,
            "trend_pct":         z.trend_pct,
            "violations_24h":    z.violations_24h,
            "violations_7d":     z.violations_7d,
            "violations_prev_7d": z.violations_prev_7d,
            "is_rising":         z.is_rising,
            "computed_at":       z.computed_at,
        }
        for z in zones
    ]


@router.get("/summary")
def get_risk_summary(
    engine: RiskEngineDep,
    _: User = Depends(require_auth),
):
    s = engine.site_summary()
    return {
        "overall_risk_level":   s.overall_risk_level,
        "overall_risk_score":   s.overall_risk_score,
        "total_violations_24h": s.total_violations_24h,
        "total_violations_7d":  s.total_violations_7d,
        "rising_risk_zones":    s.rising_risk_zones,
        "repeat_offender_count": s.repeat_offender_count,
        "highest_risk_zone":    s.highest_risk_zone,
    }


@router.get("/workers/offenders")
def get_repeat_offenders(
    engine: RiskEngineDep,
    _: User = Depends(require_auth),
):
    workers = engine.repeat_offenders()
    return [
        {
            "track_id":           w.track_id,
            "violation_count":    w.violation_count,
            "violations_24h":     w.violations_24h,
            "most_common_type":   w.most_common_type,
            "most_common_zone":   w.most_common_zone,
            "is_repeat_offender": w.is_repeat_offender,
        }
        for w in workers
    ]
