import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass
class DayBucket:
    date: str
    total: int
    ppe: int
    zone: int
    near_miss: int


@dataclass
class ZoneStat:
    zone_id: str
    total: int
    critical_count: int


@dataclass
class WorkerStat:
    track_id: int
    violation_count: int
    most_common_type: str


@dataclass
class SafetyScore:
    score: float
    ppe_score: float
    zone_score: float
    near_miss_score: float
    prev_score: float
    violations_7d: int
    ppe_7d: int
    zone_7d: int
    near_miss_7d: int
    computed_at: str


@dataclass
class ScoreDay:
    date: str
    score: float
    ppe_score: float
    zone_score: float
    near_miss_score: float
    event_count: int


@dataclass
class HeatmapPoint:
    x: float
    y: float
    severity: str


class AnalyticsEngine:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def violations_by_day(self, days: int = 7) -> list[DayBucket]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = self._conn.execute(
            """
            SELECT date(created_at) as day,
                   COUNT(*) as total,
                   SUM(CASE WHEN event_type='missing_ppe'    THEN 1 ELSE 0 END) as ppe,
                   SUM(CASE WHEN event_type='zone_intrusion' THEN 1 ELSE 0 END) as zone,
                   SUM(CASE WHEN event_type='near_miss'      THEN 1 ELSE 0 END) as near_miss
            FROM events WHERE created_at >= ?
            GROUP BY day ORDER BY day ASC
            """,
            (since,),
        ).fetchall()
        return [DayBucket(r["day"], r["total"], r["ppe"], r["zone"], r["near_miss"]) for r in rows]

    def violations_by_type(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT event_type, COUNT(*) as cnt FROM events GROUP BY event_type"
        ).fetchall()
        return {r["event_type"]: r["cnt"] for r in rows}

    def violations_by_zone(self) -> list[ZoneStat]:
        rows = self._conn.execute(
            """
            SELECT zone_id,
                   COUNT(*) as total,
                   SUM(CASE WHEN severity='CRITICAL' THEN 1 ELSE 0 END) as critical_count
            FROM events WHERE zone_id IS NOT NULL
            GROUP BY zone_id ORDER BY total DESC
            """
        ).fetchall()
        return [ZoneStat(r["zone_id"], r["total"], r["critical_count"]) for r in rows]

    def violations_by_worker(self, limit: int = 20) -> list[WorkerStat]:
        rows = self._conn.execute(
            "SELECT track_id, COUNT(*) as cnt FROM events GROUP BY track_id ORDER BY cnt DESC LIMIT ?",
            (limit,),
        ).fetchall()
        result: list[WorkerStat] = []
        for r in rows:
            type_row = self._conn.execute(
                "SELECT event_type FROM events WHERE track_id=? GROUP BY event_type ORDER BY COUNT(*) DESC LIMIT 1",
                (r["track_id"],),
            ).fetchone()
            result.append(WorkerStat(
                track_id=r["track_id"],
                violation_count=r["cnt"],
                most_common_type=type_row["event_type"] if type_row else "unknown",
            ))
        return result

    @staticmethod
    def _compute_score(ppe: int, zone: int, nm: int) -> tuple[float, float, float, float]:
        ppe_s  = max(0.0, 100.0 - ppe  * 2.0)
        zone_s = max(0.0, 100.0 - zone * 3.0)
        nm_s   = max(0.0, 100.0 - nm   * 5.0)
        composite = round(0.40 * ppe_s + 0.40 * zone_s + 0.20 * nm_s, 1)
        return composite, round(ppe_s, 1), round(zone_s, 1), round(nm_s, 1)

    def _window_counts(self, since_iso: str, until_iso: str | None = None) -> tuple[int, int, int, int]:
        if until_iso:
            row = self._conn.execute(
                """
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN event_type='missing_ppe'    THEN 1 ELSE 0 END) as ppe,
                       SUM(CASE WHEN event_type='zone_intrusion' THEN 1 ELSE 0 END) as zone,
                       SUM(CASE WHEN event_type='near_miss'      THEN 1 ELSE 0 END) as nm
                FROM events WHERE created_at >= ? AND created_at < ?
                """,
                (since_iso, until_iso),
            ).fetchone()
        else:
            row = self._conn.execute(
                """
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN event_type='missing_ppe'    THEN 1 ELSE 0 END) as ppe,
                       SUM(CASE WHEN event_type='zone_intrusion' THEN 1 ELSE 0 END) as zone,
                       SUM(CASE WHEN event_type='near_miss'      THEN 1 ELSE 0 END) as nm
                FROM events WHERE created_at >= ?
                """,
                (since_iso,),
            ).fetchone()
        return row["total"] or 0, row["ppe"] or 0, row["zone"] or 0, row["nm"] or 0

    def safety_score(self) -> SafetyScore:
        now = datetime.now(timezone.utc)
        current_since = (now - timedelta(days=7)).isoformat()
        prev_since    = (now - timedelta(days=14)).isoformat()

        total, ppe, zone, nm = self._window_counts(current_since)
        composite, ppe_s, zone_s, nm_s = self._compute_score(ppe, zone, nm)

        _, prev_ppe, prev_zone, prev_nm = self._window_counts(prev_since, current_since)
        prev_composite, _, _, _ = self._compute_score(prev_ppe, prev_zone, prev_nm)

        return SafetyScore(
            score=composite,
            ppe_score=ppe_s,
            zone_score=zone_s,
            near_miss_score=nm_s,
            prev_score=prev_composite,
            violations_7d=total,
            ppe_7d=ppe,
            zone_7d=zone,
            near_miss_7d=nm,
            computed_at=now.isoformat(),
        )

    def score_history(self, days: int = 30) -> list[ScoreDay]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = self._conn.execute(
            """
            SELECT date(created_at) as day,
                   COUNT(*) as total,
                   SUM(CASE WHEN event_type='missing_ppe'    THEN 1 ELSE 0 END) as ppe,
                   SUM(CASE WHEN event_type='zone_intrusion' THEN 1 ELSE 0 END) as zone,
                   SUM(CASE WHEN event_type='near_miss'      THEN 1 ELSE 0 END) as nm
            FROM events WHERE created_at >= ?
            GROUP BY day ORDER BY day ASC
            """,
            (since,),
        ).fetchall()
        result: list[ScoreDay] = []
        for r in rows:
            composite, ppe_s, zone_s, nm_s = self._compute_score(
                r["ppe"] or 0, r["zone"] or 0, r["nm"] or 0
            )
            result.append(ScoreDay(
                date=r["day"],
                score=composite,
                ppe_score=ppe_s,
                zone_score=zone_s,
                near_miss_score=nm_s,
                event_count=r["total"] or 0,
            ))
        return result

    def heatmap_points(self) -> list[HeatmapPoint]:
        rows = self._conn.execute(
            "SELECT bbox, severity FROM events WHERE bbox IS NOT NULL"
        ).fetchall()
        points: list[HeatmapPoint] = []
        for r in rows:
            try:
                x1, y1, x2, y2 = json.loads(r["bbox"])
                points.append(HeatmapPoint(
                    x=(x1 + x2) / 2.0,
                    y=(y1 + y2) / 2.0,
                    severity=r["severity"],
                ))
            except (json.JSONDecodeError, ValueError, TypeError):
                continue
        return points
