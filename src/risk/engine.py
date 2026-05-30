"""
RiskEngine — computes zone risk scores and repeat-offender flags
directly from the events SQLite table.

All computation is on-demand (no background jobs needed until Phase 14).
Queries are lightweight aggregations; no full table scans on large datasets.
"""
import logging
import sqlite3
from collections import Counter
from datetime import datetime, timezone

from src.risk.models import SiteSummary, WorkerRisk, ZoneRisk

logger = logging.getLogger(__name__)

# ── Risk scoring constants ────────────────────────────────────────────────────
_RISING_THRESHOLD_PCT  = 20.0   # week-over-week % increase → "RISING"
_REPEAT_WINDOW_HOURS   = 24     # window for repeat offender check
_REPEAT_MIN_VIOLATIONS = 3      # violations in window = repeat offender


def _risk_level(score: float) -> str:
    if score >= 75:
        return "CRITICAL"
    if score >= 50:
        return "HIGH"
    if score >= 25:
        return "ELEVATED"
    return "LOW"


def _trend_label(pct: float) -> str:
    if pct > _RISING_THRESHOLD_PCT:
        return "RISING"
    if pct < -_RISING_THRESHOLD_PCT:
        return "FALLING"
    return "STABLE"


def _compute_score(count_24h: int, count_7d: int, count_prev_7d: int) -> tuple[float, float]:
    """Return (risk_score 0-100, trend_pct)."""
    # Base: recent 24 h activity drives most of the score
    base = min(float(count_24h) * 8.0, 60.0)

    # Trend: week-over-week change
    if count_prev_7d == 0:
        trend_pct = 100.0 if count_7d > 0 else 0.0
    else:
        trend_pct = (count_7d - count_prev_7d) / count_prev_7d * 100.0

    if trend_pct > 50:
        trend_bonus = 30.0
    elif trend_pct > _RISING_THRESHOLD_PCT:
        trend_bonus = 15.0
    elif trend_pct > 0:
        trend_bonus = 5.0
    elif trend_pct < -_RISING_THRESHOLD_PCT:
        trend_bonus = -15.0
    elif trend_pct < 0:
        trend_bonus = -5.0
    else:
        trend_bonus = 0.0

    score = min(100.0, max(0.0, base + trend_bonus))
    return score, trend_pct


class RiskEngine:
    """Stateless risk engine — takes a shared SQLite connection."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ── Zone risk ─────────────────────────────────────────────────────────────

    def zone_risks(self) -> list[ZoneRisk]:
        """Compute risk scores for every zone that has at least one event."""
        now_iso = datetime.now(timezone.utc).isoformat()

        rows_24h = self._conn.execute(
            """
            SELECT zone_id, COUNT(*) as cnt
            FROM events
            WHERE zone_id IS NOT NULL
              AND created_at >= strftime('%Y-%m-%dT%H:%M:%S', 'now', '-1 day')
            GROUP BY zone_id
            """
        ).fetchall()

        rows_7d = self._conn.execute(
            """
            SELECT zone_id, COUNT(*) as cnt
            FROM events
            WHERE zone_id IS NOT NULL
              AND created_at >= strftime('%Y-%m-%dT%H:%M:%S', 'now', '-7 days')
            GROUP BY zone_id
            """
        ).fetchall()

        rows_prev = self._conn.execute(
            """
            SELECT zone_id, COUNT(*) as cnt
            FROM events
            WHERE zone_id IS NOT NULL
              AND created_at >= strftime('%Y-%m-%dT%H:%M:%S', 'now', '-14 days')
              AND created_at  < strftime('%Y-%m-%dT%H:%M:%S', 'now', '-7 days')
            GROUP BY zone_id
            """
        ).fetchall()

        # Merge into dicts keyed by zone_id
        c24  = {r["zone_id"]: r["cnt"] for r in rows_24h}
        c7   = {r["zone_id"]: r["cnt"] for r in rows_7d}
        cprev = {r["zone_id"]: r["cnt"] for r in rows_prev}

        all_zones = set(c24) | set(c7) | set(cprev)
        results: list[ZoneRisk] = []

        for zone_id in sorted(all_zones):
            n24   = c24.get(zone_id, 0)
            n7    = c7.get(zone_id, 0)
            nprev = cprev.get(zone_id, 0)
            score, trend_pct = _compute_score(n24, n7, nprev)
            results.append(ZoneRisk(
                zone_id          = zone_id,
                risk_score       = round(score, 1),
                risk_level       = _risk_level(score),
                trend            = _trend_label(trend_pct),
                trend_pct        = round(trend_pct, 1),
                violations_24h   = n24,
                violations_7d    = n7,
                violations_prev_7d = nprev,
                is_rising        = trend_pct > _RISING_THRESHOLD_PCT,
                computed_at      = now_iso,
            ))

        # Sort by risk_score descending
        results.sort(key=lambda z: z.risk_score, reverse=True)
        return results

    # ── Repeat offenders ──────────────────────────────────────────────────────

    def repeat_offenders(
        self,
        window_hours: int = _REPEAT_WINDOW_HOURS,
        min_violations: int = _REPEAT_MIN_VIOLATIONS,
    ) -> list[WorkerRisk]:
        """Return workers with >= min_violations in the last window_hours."""
        rows_recent = self._conn.execute(
            f"""
            SELECT track_id, COUNT(*) as cnt
            FROM events
            WHERE created_at >= strftime('%Y-%m-%dT%H:%M:%S', 'now', '-{window_hours} hours')
            GROUP BY track_id
            HAVING cnt >= ?
            ORDER BY cnt DESC
            """,
            (min_violations,),
        ).fetchall()

        results: list[WorkerRisk] = []
        for row in rows_recent:
            tid = row["track_id"]
            cnt_24h = row["cnt"]

            # Total violations ever
            total_row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM events WHERE track_id = ?", (tid,)
            ).fetchone()
            total = total_row["cnt"] if total_row else cnt_24h

            # Most common violation type and zone
            type_rows = self._conn.execute(
                "SELECT event_type, COUNT(*) as cnt FROM events "
                "WHERE track_id = ? GROUP BY event_type ORDER BY cnt DESC LIMIT 1",
                (tid,),
            ).fetchone()
            zone_row = self._conn.execute(
                "SELECT zone_id, COUNT(*) as cnt FROM events "
                "WHERE track_id = ? AND zone_id IS NOT NULL "
                "GROUP BY zone_id ORDER BY cnt DESC LIMIT 1",
                (tid,),
            ).fetchone()

            results.append(WorkerRisk(
                track_id           = tid,
                violation_count    = total,
                violations_24h     = cnt_24h,
                most_common_type   = type_rows["event_type"] if type_rows else "unknown",
                most_common_zone   = zone_row["zone_id"] if zone_row else None,
                is_repeat_offender = True,
            ))

        return results

    # ── Site summary ──────────────────────────────────────────────────────────

    def site_summary(self) -> SiteSummary:
        """Roll up zone risks into a single site-level snapshot."""
        zones = self.zone_risks()
        offenders = self.repeat_offenders()

        total_24h_row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM events "
            "WHERE created_at >= strftime('%Y-%m-%dT%H:%M:%S', 'now', '-1 day')"
        ).fetchone()
        total_7d_row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM events "
            "WHERE created_at >= strftime('%Y-%m-%dT%H:%M:%S', 'now', '-7 days')"
        ).fetchone()

        total_24h = total_24h_row["cnt"] if total_24h_row else 0
        total_7d  = total_7d_row["cnt"]  if total_7d_row  else 0

        rising = [z.zone_id for z in zones if z.is_rising]

        if zones:
            avg_score = sum(z.risk_score for z in zones) / len(zones)
            top_zone  = zones[0]
            overall_level = top_zone.risk_level
            highest_zone  = top_zone.zone_id
        else:
            avg_score     = 0.0
            overall_level = "LOW"
            highest_zone  = None

        return SiteSummary(
            overall_risk_level    = overall_level,
            overall_risk_score    = round(avg_score, 1),
            total_violations_24h  = total_24h,
            total_violations_7d   = total_7d,
            rising_risk_zones     = rising,
            repeat_offender_count = len(offenders),
            highest_risk_zone     = highest_zone,
        )
