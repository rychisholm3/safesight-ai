"""
Root Cause Analyzer — statistical pattern detection from the events table.

Produces three analysis layers:
  1. Time-of-day distribution — hourly violation counts + Z-scores + shift-period labelling
  2. Location analysis       — per-zone violation breakdown with time-of-day peaks
  3. Worker pattern analysis — violation frequency segmentation + per-worker time / zone affinity

Worker-type note
----------------
ByteTrack assigns numeric IDs; we have no HR data to distinguish temp vs. permanent staff.
We instead segment by violation frequency (isolated / recurring / chronic) and surface
time/zone affinity patterns — clinically equivalent for intervention decisions.
"""
import sqlite3
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# ── Shift-period labels ────────────────────────────────────────────────────────
_SHIFT_PERIODS: list[tuple[str, range]] = [
    ("Pre-shift / Night",  range(0, 6)),
    ("Shift Start",        range(6, 10)),
    ("Mid-Morning",        range(10, 12)),
    ("Lunch",              range(12, 14)),
    ("Afternoon",          range(14, 17)),
    ("Shift End",          range(17, 20)),
    ("Evening",            range(20, 24)),
]

def _shift_period(hour: int) -> str:
    for name, r in _SHIFT_PERIODS:
        if hour in r:
            return name
    return "Unknown"


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class HourBucket:
    hour:          int
    label:         str           # "08:00"
    count:         int
    period:        str           # "Shift Start"
    z_score:       float         # std-devs above mean
    is_peak:       bool          # True if z_score >= 1.0


@dataclass
class ShiftPeriodSummary:
    name:            str
    count:           int
    avg_per_hour:    float
    risk_level:      str         # "LOW" | "ELEVATED" | "HIGH" | "CRITICAL"
    dominant_type:   str         # most common event_type in this period


@dataclass
class ZonePattern:
    zone_id:       str
    count:         int
    ppe_count:     int
    zone_count:    int
    nm_count:      int
    peak_hour:     int | None
    peak_period:   str | None


@dataclass
class WorkerPattern:
    track_id:          int
    violation_count:   int
    segment:           str        # "isolated" | "recurring" | "chronic"
    dominant_type:     str
    primary_zone:      str | None
    peak_hour:         int | None
    peak_period:       str | None


@dataclass
class RootCauseAnalysis:
    days_analysed:      int
    event_total:        int
    hour_buckets:       list[HourBucket]
    shift_periods:      list[ShiftPeriodSummary]
    zone_patterns:      list[ZonePattern]
    global_events:      dict                  # event_type → count for non-zone events
    worker_patterns:    list[WorkerPattern]
    top_peak_periods:   list[str]             # top 2 shift periods by count
    top_hotspot_zones:  list[str]             # top 3 zones by count
    computed_at:        str


# ── Engine ────────────────────────────────────────────────────────────────────

class RootCauseAnalyzer:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _fetch_events(self, days: int) -> list[dict]:
        rows = self._conn.execute(
            f"""
            SELECT event_type, track_id, zone_id, zone_rule, missing_ppe,
                   severity, created_at
            FROM events
            WHERE created_at >= strftime('%Y-%m-%dT%H:%M:%S','now','-{days} days')
            ORDER BY created_at ASC
            """,
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _hour_of(iso: str) -> int:
        try:
            return datetime.fromisoformat(iso.replace("Z", "+00:00")).hour
        except ValueError:
            return 0

    # ── Public API ────────────────────────────────────────────────────────────

    def analyse(self, days: int = 7) -> RootCauseAnalysis:
        events = self._fetch_events(days)
        now_iso = datetime.now(timezone.utc).isoformat()

        # ── Time-of-day distribution ──────────────────────────────────────────
        hour_counts: dict[int, int] = {h: 0 for h in range(24)}
        for ev in events:
            hour_counts[self._hour_of(ev["created_at"])] += 1

        counts   = list(hour_counts.values())
        mean_c   = statistics.mean(counts) if counts else 0
        stdev_c  = statistics.stdev(counts) if len(counts) > 1 else 1.0 or 1.0

        hour_buckets: list[HourBucket] = []
        for h in range(24):
            c  = hour_counts[h]
            z  = (c - mean_c) / stdev_c if stdev_c else 0.0
            hour_buckets.append(HourBucket(
                hour    = h,
                label   = f"{h:02d}:00",
                count   = c,
                period  = _shift_period(h),
                z_score = round(z, 2),
                is_peak = z >= 1.0,
            ))

        # ── Shift-period summaries ────────────────────────────────────────────
        period_events: dict[str, list[dict]] = {n: [] for n, _ in _SHIFT_PERIODS}
        for ev in events:
            p = _shift_period(self._hour_of(ev["created_at"]))
            if p in period_events:
                period_events[p].append(ev)

        shift_periods: list[ShiftPeriodSummary] = []
        for name, r in _SHIFT_PERIODS:
            evs   = period_events[name]
            cnt   = len(evs)
            n_hrs = len(r) or 1
            avg   = round(cnt / n_hrs, 1)
            types: dict[str, int] = {}
            for ev in evs:
                types[ev["event_type"]] = types.get(ev["event_type"], 0) + 1
            dom   = max(types, key=lambda k: types[k]) if types else "none"
            risk  = ("CRITICAL" if avg >= 5 else "HIGH" if avg >= 3
                     else "ELEVATED" if avg >= 1 else "LOW")
            shift_periods.append(ShiftPeriodSummary(
                name=name, count=cnt, avg_per_hour=avg,
                risk_level=risk, dominant_type=dom,
            ))

        # ── Zone patterns ─────────────────────────────────────────────────────
        zone_data: dict[str, dict] = {}
        for ev in events:
            zid = ev.get("zone_id")
            if not zid:
                continue
            if zid not in zone_data:
                zone_data[zid] = {"hours": [], "ppe": 0, "zone": 0, "nm": 0, "total": 0}
            zone_data[zid]["total"] += 1
            zone_data[zid]["hours"].append(self._hour_of(ev["created_at"]))
            t = ev["event_type"]
            if t == "missing_ppe":    zone_data[zid]["ppe"]  += 1
            elif t == "zone_intrusion": zone_data[zid]["zone"] += 1
            elif t == "near_miss":      zone_data[zid]["nm"]   += 1

        zone_patterns: list[ZonePattern] = []
        for zid, d in sorted(zone_data.items(), key=lambda x: -x[1]["total"]):
            hours = d["hours"]
            peak_h = max(set(hours), key=hours.count) if hours else None
            zone_patterns.append(ZonePattern(
                zone_id    = zid,
                count      = d["total"],
                ppe_count  = d["ppe"],
                zone_count = d["zone"],
                nm_count   = d["nm"],
                peak_hour  = peak_h,
                peak_period= _shift_period(peak_h) if peak_h is not None else None,
            ))

        global_evs = {"missing_ppe": 0, "zone_intrusion": 0, "near_miss": 0}
        for ev in events:
            if not ev.get("zone_id"):
                global_evs[ev["event_type"]] = global_evs.get(ev["event_type"], 0) + 1

        # ── Worker patterns ───────────────────────────────────────────────────
        worker_data: dict[int, dict] = {}
        for ev in events:
            tid = ev.get("track_id")
            if tid is None:
                continue
            if tid not in worker_data:
                worker_data[tid] = {"hours": [], "zones": [], "types": []}
            worker_data[tid]["hours"].append(self._hour_of(ev["created_at"]))
            if ev.get("zone_id"):
                worker_data[tid]["zones"].append(ev["zone_id"])
            worker_data[tid]["types"].append(ev["event_type"])

        worker_patterns: list[WorkerPattern] = []
        for tid, d in sorted(worker_data.items(), key=lambda x: -len(x[1]["types"])):
            cnt   = len(d["types"])
            seg   = ("chronic" if cnt >= 5 else "recurring" if cnt >= 2 else "isolated")
            hours = d["hours"]
            zones = d["zones"]
            types = d["types"]
            dom_t = max(set(types), key=types.count) if types else "unknown"
            ph    = max(set(hours), key=hours.count) if hours else None
            pz    = max(set(zones), key=zones.count) if zones else None
            worker_patterns.append(WorkerPattern(
                track_id        = tid,
                violation_count = cnt,
                segment         = seg,
                dominant_type   = dom_t,
                primary_zone    = pz,
                peak_hour       = ph,
                peak_period     = _shift_period(ph) if ph is not None else None,
            ))

        # Top summaries
        top_peaks = sorted(
            [s for s in shift_periods if s.count > 0],
            key=lambda s: -s.count,
        )[:2]
        top_zones = [z.zone_id for z in zone_patterns[:3]]

        return RootCauseAnalysis(
            days_analysed    = days,
            event_total      = len(events),
            hour_buckets     = hour_buckets,
            shift_periods    = shift_periods,
            zone_patterns    = zone_patterns,
            global_events    = global_evs,
            worker_patterns  = worker_patterns,
            top_peak_periods = [s.name for s in top_peaks],
            top_hotspot_zones= top_zones,
            computed_at      = now_iso,
        )
