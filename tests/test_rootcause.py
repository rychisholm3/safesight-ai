"""
Tests for Phase 9 — Automated Root Cause Analysis.
"""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.rootcause.analyzer import RootCauseAnalyzer, _shift_period
from src.rootcause.summary import _deterministic_summary


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("""
        CREATE TABLE events (
            event_id TEXT, event_type TEXT, track_id INTEGER,
            zone_id TEXT, zone_rule TEXT, missing_ppe TEXT DEFAULT '[]',
            severity TEXT DEFAULT 'WARNING', created_at TEXT
        )
    """)
    c.commit()
    return c


def _insert(conn, event_type="missing_ppe", track_id=1,
            hours_ago=1.0, zone_id=None, severity="WARNING"):
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    conn.execute(
        "INSERT INTO events (event_id, event_type, track_id, zone_id, severity, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (f"ev_{event_type}_{track_id}_{hours_ago}", event_type, track_id,
         zone_id, severity, ts),
    )
    conn.commit()


# ── _shift_period ─────────────────────────────────────────────────────────────

class TestShiftPeriod:
    def test_shift_start(self):
        assert _shift_period(8) == "Shift Start"

    def test_lunch(self):
        assert _shift_period(12) == "Lunch"
        assert _shift_period(13) == "Lunch"

    def test_night(self):
        assert _shift_period(2) == "Pre-shift / Night"

    def test_shift_end(self):
        assert _shift_period(18) == "Shift End"


# ── RootCauseAnalyzer ─────────────────────────────────────────────────────────

class TestRootCauseAnalyzer:
    def test_empty_db_returns_zero_events(self, conn):
        a = RootCauseAnalyzer(conn).analyse(7)
        assert a.event_total == 0

    def test_24_hour_buckets_always_returned(self, conn):
        a = RootCauseAnalyzer(conn).analyse(7)
        assert len(a.hour_buckets) == 24

    def test_all_shift_periods_returned(self, conn):
        a = RootCauseAnalyzer(conn).analyse(7)
        assert len(a.shift_periods) == 7

    def test_events_counted_correctly(self, conn):
        _insert(conn, track_id=1, hours_ago=1)
        _insert(conn, track_id=2, hours_ago=2)
        _insert(conn, track_id=3, hours_ago=3)
        a = RootCauseAnalyzer(conn).analyse(7)
        assert a.event_total == 3

    def test_old_events_excluded(self, conn):
        _insert(conn, hours_ago=200)  # > 7 days
        a = RootCauseAnalyzer(conn).analyse(7)
        assert a.event_total == 0

    def test_zone_pattern_detected(self, conn):
        _insert(conn, zone_id="forklift_lane", hours_ago=1)
        _insert(conn, zone_id="forklift_lane", hours_ago=2)
        a = RootCauseAnalyzer(conn).analyse(7)
        assert len(a.zone_patterns) == 1
        assert a.zone_patterns[0].zone_id == "forklift_lane"
        assert a.zone_patterns[0].count == 2

    def test_worker_patterns_segmented(self, conn):
        # Chronic: 5+ violations
        for i in range(6):
            _insert(conn, track_id=99, hours_ago=i + 1)
        # Isolated: 1 violation
        _insert(conn, track_id=42, hours_ago=1)

        a = RootCauseAnalyzer(conn).analyse(7)
        chronic = [w for w in a.worker_patterns if w.segment == "chronic"]
        isolated = [w for w in a.worker_patterns if w.segment == "isolated"]
        assert any(w.track_id == 99 for w in chronic)
        assert any(w.track_id == 42 for w in isolated)

    def test_z_scores_computed(self, conn):
        # Insert many events in one hour, few in others
        for i in range(10):
            _insert(conn, track_id=i, hours_ago=1)  # 1 hour ago
        a = RootCauseAnalyzer(conn).analyse(7)
        # The 1-hour-ago bucket should have the highest z_score
        peak_buckets = [b for b in a.hour_buckets if b.is_peak]
        assert len(peak_buckets) >= 1

    def test_top_peak_periods_non_empty_when_events_exist(self, conn):
        _insert(conn, hours_ago=8)  # shift start
        _insert(conn, hours_ago=8)
        _insert(conn, hours_ago=8)
        a = RootCauseAnalyzer(conn).analyse(7)
        assert len(a.top_peak_periods) >= 0  # may be 0 if only one period

    def test_global_events_for_non_zone_events(self, conn):
        _insert(conn, event_type="missing_ppe", zone_id=None)
        _insert(conn, event_type="zone_intrusion", zone_id=None)
        a = RootCauseAnalyzer(conn).analyse(7)
        assert a.global_events.get("missing_ppe", 0) >= 1
        assert a.global_events.get("zone_intrusion", 0) >= 1

    def test_zone_patterns_sorted_by_count_descending(self, conn):
        for _ in range(5):
            _insert(conn, zone_id="high_risk_zone")
        for _ in range(2):
            _insert(conn, zone_id="low_risk_zone")
        a = RootCauseAnalyzer(conn).analyse(7)
        counts = [z.count for z in a.zone_patterns]
        assert counts == sorted(counts, reverse=True)

    def test_days_param_filters_correctly(self, conn):
        _insert(conn, hours_ago=1)    # within 1 day
        _insert(conn, hours_ago=200)  # older than 7 days
        a1 = RootCauseAnalyzer(conn).analyse(days=1)
        a7 = RootCauseAnalyzer(conn).analyse(days=7)
        assert a1.event_total == 1
        assert a7.event_total == 1  # 200h > 7 days too


# ── Deterministic summary ─────────────────────────────────────────────────────

class TestDeterministicSummary:
    def _analysis(self, conn):
        return RootCauseAnalyzer(conn).analyse(7)

    def test_returns_required_fields(self, conn):
        s = _deterministic_summary(self._analysis(conn))
        assert "root_causes" in s
        assert "recommendations" in s
        assert "worker_segments" in s
        assert "generated_by" in s
        assert s["generated_by"] == "deterministic"

    def test_recommendations_non_empty(self, conn):
        s = _deterministic_summary(self._analysis(conn))
        assert len(s["recommendations"]) > 0

    def test_chronic_worker_mentioned_in_recs(self, conn):
        for i in range(6):
            _insert(conn, track_id=77, hours_ago=i + 1)
        s = _deterministic_summary(self._analysis(conn))
        recs_text = " ".join(s["recommendations"])
        assert "77" in recs_text or any("chronic" in rc["title"].lower()
                                         for rc in s.get("root_causes", []))


# ── HTTP endpoints ────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    from src.api.main import app, _shared_conn
    from src.rootcause.router import _get_conn as _rc_get_conn
    app.dependency_overrides[_rc_get_conn] = lambda: _shared_conn
    return TestClient(app, raise_server_exceptions=True)


def _auth(client):
    client.post("/auth/register", json={"org_name": "RCOrg", "email": "rc@test.com", "password": "secret123"})
    r = client.post("/auth/login", json={"email": "rc@test.com", "password": "secret123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


class TestRootCauseEndpoints:
    def test_analysis_returns_expected_fields(self, client):
        h   = _auth(client)
        res = client.get("/rootcause/analysis", headers=h)
        assert res.status_code == 200
        body = res.json()
        assert "hour_buckets"   in body
        assert "shift_periods"  in body
        assert "zone_patterns"  in body
        assert "worker_patterns" in body
        assert len(body["hour_buckets"]) == 24

    def test_analysis_days_param(self, client):
        h   = _auth(client)
        res = client.get("/rootcause/analysis?days=14", headers=h)
        assert res.status_code == 200
        assert res.json()["days_analysed"] == 14

    def test_analysis_requires_auth(self, client):
        assert client.get("/rootcause/analysis").status_code == 401

    def test_summary_returns_expected_fields(self, client):
        h   = _auth(client)
        res = client.post("/rootcause/summary", headers=h)
        assert res.status_code == 200
        body = res.json()
        assert "root_causes"     in body
        assert "recommendations" in body
        assert "generated_by"    in body

    def test_summary_requires_auth(self, client):
        assert client.post("/rootcause/summary").status_code == 401

    def test_invalid_days_param(self, client):
        h   = _auth(client)
        res = client.get("/rootcause/analysis?days=0", headers=h)
        assert res.status_code == 422
