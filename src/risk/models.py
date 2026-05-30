"""
Data models for the Phase 3 Predictive Risk Engine.

ZoneRisk   — risk score + trend for a single zone
WorkerRisk — violation history for a tracked worker (repeat offender detection)
SiteSummary — rolled-up site-wide risk snapshot
"""
from dataclasses import dataclass, field


@dataclass
class ZoneRisk:
    zone_id: str
    risk_score: float           # 0–100
    risk_level: str             # LOW | ELEVATED | HIGH | CRITICAL
    trend: str                  # RISING | STABLE | FALLING
    trend_pct: float            # week-over-week % change (positive = rising)
    violations_24h: int
    violations_7d: int
    violations_prev_7d: int     # previous week (7–14 days ago)
    is_rising: bool             # trend_pct > configured threshold (default 20 %)
    computed_at: str            # ISO-8601 UTC timestamp


@dataclass
class WorkerRisk:
    track_id: int
    violation_count: int        # total in DB
    violations_24h: int
    most_common_type: str       # "missing_ppe" | "zone_intrusion"
    most_common_zone: str | None
    is_repeat_offender: bool    # violations_24h >= repeat_threshold


@dataclass
class SiteSummary:
    overall_risk_level: str     # worst zone level or aggregate
    overall_risk_score: float   # average across all zones
    total_violations_24h: int
    total_violations_7d: int
    rising_risk_zones: list[str] = field(default_factory=list)
    repeat_offender_count: int = 0
    highest_risk_zone: str | None = None
