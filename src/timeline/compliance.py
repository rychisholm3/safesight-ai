"""
Compliance engine — computes live PPE %, zone %, and overall PASS/FAIL status
from the events table, plus 7-day history and a predicted tomorrow value.

Compliance definition
---------------------
For a rolling 24-hour window, every unique track_id is classified as:
  • PPE compliant     — had zero missing_ppe events
  • Zone compliant    — had zero zone_intrusion or near_miss events

PPE %    = compliant_ppe_workers  / total_workers × 100
Zone %   = compliant_zone_workers / total_workers × 100
Overall  = mean(PPE %, Zone %)

PASS when PPE ≥ 90 % AND Zone ≥ 95 %.  FAIL otherwise.

Prediction
----------
Linear trend over the last 7 days of daily overall %, applied one step ahead,
clamped to 0–100.  Direction arrow: RISING / FALLING / STABLE (< 2 pp change).
"""
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

_PPE_BAD   = ("missing_ppe",)
_ZONE_BAD  = ("zone_intrusion", "near_miss")
_PASS_PPE  = 90.0
_PASS_ZONE = 95.0


@dataclass
class ComplianceStatus:
    ppe_pct:              float
    zone_pct:             float
    overall_pct:          float
    status:               str    # "PASS" | "FAIL"
    tracked_workers_24h:  int
    computed_at:          str


@dataclass
class DailyCompliance:
    date:        str    # YYYY-MM-DD
    ppe_pct:     float
    zone_pct:    float
    overall_pct: float
    event_count: int


@dataclass
class ComplianceForecast:
    predicted_pct: float
    trend:         str   # "RISING" | "FALLING" | "STABLE"
    trend_pct:     float # change from yesterday (signed)


class ComplianceEngine:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _workers_in_window(self, from_iso: str, to_iso: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(DISTINCT track_id) as n FROM events "
            "WHERE created_at >= ? AND created_at < ?",
            (from_iso, to_iso),
        ).fetchone()
        return int(row["n"]) if row else 0

    def _bad_workers(self, from_iso: str, to_iso: str, types: tuple[str, ...]) -> int:
        ph  = ",".join("?" * len(types))
        row = self._conn.execute(
            f"SELECT COUNT(DISTINCT track_id) as n FROM events "
            f"WHERE created_at >= ? AND created_at < ? AND event_type IN ({ph})",
            [from_iso, to_iso, *types],
        ).fetchone()
        return int(row["n"]) if row else 0

    def _event_count(self, from_iso: str, to_iso: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) as n FROM events WHERE created_at >= ? AND created_at < ?",
            (from_iso, to_iso),
        ).fetchone()
        return int(row["n"]) if row else 0

    @staticmethod
    def _pcts(total: int, ppe_bad: int, zone_bad: int) -> tuple[float, float, float]:
        if total == 0:
            return 100.0, 100.0, 100.0
        ppe  = round((total - ppe_bad)  / total * 100, 1)
        zone = round((total - zone_bad) / total * 100, 1)
        ovr  = round((ppe + zone) / 2,  1)
        return ppe, zone, ovr

    # ── Public API ────────────────────────────────────────────────────────────

    def current_status(self) -> ComplianceStatus:
        """Compute live compliance for the rolling 24-hour window."""
        now   = datetime.now(timezone.utc)
        ago   = now - timedelta(hours=24)
        f_iso = ago.isoformat()
        t_iso = now.isoformat()

        total    = self._workers_in_window(f_iso, t_iso)
        ppe_bad  = self._bad_workers(f_iso, t_iso, _PPE_BAD)
        zone_bad = self._bad_workers(f_iso, t_iso, _ZONE_BAD)

        ppe, zone, ovr = self._pcts(total, ppe_bad, zone_bad)
        status = "PASS" if ppe >= _PASS_PPE and zone >= _PASS_ZONE else "FAIL"

        return ComplianceStatus(
            ppe_pct             = ppe,
            zone_pct            = zone,
            overall_pct         = ovr,
            status              = status,
            tracked_workers_24h = total,
            computed_at         = now.isoformat(),
        )

    def daily_history(self, days: int = 7) -> list[DailyCompliance]:
        """Return per-day compliance for the last *days* calendar days (UTC)."""
        today   = date.today()
        results = []

        for offset in range(days - 1, -1, -1):
            d      = today - timedelta(days=offset)
            d_next = d + timedelta(days=1)
            f_iso  = f"{d.isoformat()}T00:00:00"
            t_iso  = f"{d_next.isoformat()}T00:00:00"

            total    = self._workers_in_window(f_iso, t_iso)
            ppe_bad  = self._bad_workers(f_iso, t_iso, _PPE_BAD)
            zone_bad = self._bad_workers(f_iso, t_iso, _ZONE_BAD)
            ev_cnt   = self._event_count(f_iso, t_iso)

            ppe, zone, ovr = self._pcts(total, ppe_bad, zone_bad)
            results.append(DailyCompliance(
                date=d.isoformat(), ppe_pct=ppe, zone_pct=zone,
                overall_pct=ovr, event_count=ev_cnt,
            ))

        return results

    def forecast(self, history: list[DailyCompliance] | None = None) -> ComplianceForecast:
        """Predict tomorrow's overall compliance using linear trend."""
        if history is None:
            history = self.daily_history(7)

        values = [h.overall_pct for h in history]

        if len(values) < 2:
            return ComplianceForecast(
                predicted_pct=values[0] if values else 100.0,
                trend="STABLE", trend_pct=0.0,
            )

        # Simple linear trend: slope from first to last
        n     = len(values)
        slope = (values[-1] - values[0]) / (n - 1)
        pred  = min(100.0, max(0.0, round(values[-1] + slope, 1)))

        change = round(pred - values[-1], 1)
        trend  = "RISING" if change > 2 else "FALLING" if change < -2 else "STABLE"

        return ComplianceForecast(
            predicted_pct=pred,
            trend=trend,
            trend_pct=change,
        )
