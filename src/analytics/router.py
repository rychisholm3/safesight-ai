import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.analytics.engine import AnalyticsEngine
from src.auth.dependencies import require_auth
from src.auth.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _get_engine() -> AnalyticsEngine:  # pragma: no cover
    raise RuntimeError("analytics_engine not wired — check src/api/main.py")


EngineDep = Annotated[AnalyticsEngine, Depends(_get_engine)]


@router.get("/violations/daily")
def violations_daily(
    engine: EngineDep,
    days: int = Query(default=7, ge=1, le=90),
    _: User = Depends(require_auth),
):
    return [
        {"date": b.date, "total": b.total, "ppe": b.ppe, "zone": b.zone, "near_miss": b.near_miss}
        for b in engine.violations_by_day(days)
    ]


@router.get("/violations/by-type")
def violations_by_type(engine: EngineDep, _: User = Depends(require_auth)):
    return engine.violations_by_type()


@router.get("/violations/by-zone")
def violations_by_zone(engine: EngineDep, _: User = Depends(require_auth)):
    return [
        {"zone_id": z.zone_id, "total": z.total, "critical_count": z.critical_count}
        for z in engine.violations_by_zone()
    ]


@router.get("/violations/by-worker")
def violations_by_worker(
    engine: EngineDep,
    limit: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_auth),
):
    return [
        {"track_id": w.track_id, "violation_count": w.violation_count, "most_common_type": w.most_common_type}
        for w in engine.violations_by_worker(limit)
    ]


@router.get("/score")
def safety_score(engine: EngineDep, _: User = Depends(require_auth)):
    s = engine.safety_score()
    return {
        "score":           s.score,
        "ppe_score":       s.ppe_score,
        "zone_score":      s.zone_score,
        "near_miss_score": s.near_miss_score,
        "prev_score":      s.prev_score,
        "violations_7d":   s.violations_7d,
        "ppe_7d":          s.ppe_7d,
        "zone_7d":         s.zone_7d,
        "near_miss_7d":    s.near_miss_7d,
        "computed_at":     s.computed_at,
    }


@router.get("/score/history")
def score_history(
    engine: EngineDep,
    days: int = Query(default=30, ge=7, le=90),
    _: User = Depends(require_auth),
):
    return [
        {
            "date":            d.date,
            "score":           d.score,
            "ppe_score":       d.ppe_score,
            "zone_score":      d.zone_score,
            "near_miss_score": d.near_miss_score,
            "event_count":     d.event_count,
        }
        for d in engine.score_history(days)
    ]


@router.get("/heatmap")
def heatmap(engine: EngineDep, _: User = Depends(require_auth)):
    return [{"x": p.x, "y": p.y, "severity": p.severity} for p in engine.heatmap_points()]
