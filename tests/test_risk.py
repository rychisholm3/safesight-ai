"""
Tests for Phase 3 — Predictive Risk Engine.

Covers:
- RiskEngine.zone_risks() scoring and trend logic
- RiskEngine.repeat_offenders() detection
- RiskEngine.site_summary() rollup
- API endpoints GET /risk/zones, /risk/summary, /risk/workers/offenders
"""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.auth.dependencies import require_auth
from src.auth.models import Role, User
from src.risk.engine import RiskEngine, _compute_score, _risk_level, _trend_label
from src.risk.router import _get_risk_engine


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("""
        CREATE TABLE events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            track_id INTEGER NOT NULL,
            zone_id TEXT,
            missing_ppe TEXT NOT NULL DEFAULT '[]',
            severity TEXT NOT NULL DEFAULT 'WARNING',
            start_frame INTEGER NOT NULL,
            end_frame INTEGER,
            snapshot_path TEXT,
            created_at TEXT NOT NULL
        )
    """)
    c.commit()
    return c


@pytest.fixture()
def engine(conn):
    return RiskEngine(conn)


def _insert_event(conn, zone_id, track_id=1, hours_ago=1, event_type="zone_intrusion"):
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    eid = f"evt-{zone_id}-{track_id}-{hours_ago}-{event_type}"
    conn.execute(
        "INSERT OR IGNORE INTO events "
        "(event_id, event_type, track_id, zone_id, missing_ppe, severity, start_frame, created_at) "
        "VALUES (?, ?, ?, ?, '[]', 'CRITICAL', 0, ?)",
        (eid, event_type, track_id, zone_id, ts),
    )
    conn.commit()


def _fake_user():
    return User(
        user_id="u1", org_id="org1", email="test@example.com",
        hashed_password="x", role=Role.safety_officer,
        is_active=True, created_at="2025-01-01",
    )


@pytest.fixture()
def client(conn):
    eng = RiskEngine(conn)
    app.dependency_overrides[require_auth]      = _fake_user
    app.dependency_overrides[_get_risk_engine]  = lambda: eng
    with TestClient(app) as c:
        yield c, conn
    app.dependency_overrides.clear()


# ── Pure scoring functions ────────────────────────────────────────────────────

class TestScoringFunctions:
    def test_zero_violations_zero_score(self):
        score, trend_pct = _compute_score(0, 0, 0)
        assert score == 0.0
        assert trend_pct == 0.0

    def test_score_capped_at_100(self):
        score, _ = _compute_score(100, 100, 0)
        assert score <= 100.0

    def test_rising_trend_increases_score(self):
        score_flat, _  = _compute_score(5, 10, 10)
        score_rising, _ = _compute_score(5, 20, 10)
        assert score_rising > score_flat

    def test_falling_trend_decreases_score(self):
        score_flat, _    = _compute_score(5, 10, 10)
        score_falling, _ = _compute_score(5, 5, 10)
        assert score_falling < score_flat

    def test_risk_level_thresholds(self):
        assert _risk_level(0)   == "LOW"
        assert _risk_level(25)  == "ELEVATED"
        assert _risk_level(50)  == "HIGH"
        assert _risk_level(75)  == "CRITICAL"
        assert _risk_level(100) == "CRITICAL"

    def test_trend_label(self):
        assert _trend_label(50)  == "RISING"
        assert _trend_label(5)   == "STABLE"
        assert _trend_label(0)   == "STABLE"
        assert _trend_label(-5)  == "STABLE"
        assert _trend_label(-50) == "FALLING"


# ── RiskEngine.zone_risks() ───────────────────────────────────────────────────

class TestZoneRisks:
    def test_empty_db_returns_empty(self, engine):
        assert engine.zone_risks() == []

    def test_single_zone_detected(self, conn, engine):
        _insert_event(conn, "zone_a", hours_ago=1)
        zones = engine.zone_risks()
        assert len(zones) == 1
        assert zones[0].zone_id == "zone_a"
        assert zones[0].violations_24h == 1

    def test_null_zone_excluded(self, conn, engine):
        # Events with no zone (global PPE violations) should not appear
        conn.execute(
            "INSERT INTO events (event_id,event_type,track_id,zone_id,missing_ppe,severity,start_frame,created_at) "
            "VALUES ('x','missing_ppe',1,NULL,'[]','WARNING',0,datetime('now'))"
        )
        conn.commit()
        assert engine.zone_risks() == []

    def test_multiple_zones_sorted_by_score(self, conn, engine):
        for i in range(5):
            _insert_event(conn, "hot_zone", track_id=i, hours_ago=1)
        _insert_event(conn, "cool_zone", hours_ago=1)
        zones = engine.zone_risks()
        assert zones[0].zone_id == "hot_zone"

    def test_trend_is_rising_when_this_week_higher(self, conn, engine):
        # 10 events this week, 2 last week
        for i in range(10):
            _insert_event(conn, "zone_a", track_id=i, hours_ago=24)
        for i in range(2):
            _insert_event(conn, "zone_a", track_id=i+10, hours_ago=24*10)
        zones = engine.zone_risks()
        zone = next(z for z in zones if z.zone_id == "zone_a")
        assert zone.trend == "RISING"
        assert zone.is_rising is True

    def test_risk_level_elevated_with_moderate_violations(self, conn, engine):
        for i in range(4):
            _insert_event(conn, "zone_b", track_id=i, hours_ago=2)
        zones = engine.zone_risks()
        zone = next(z for z in zones if z.zone_id == "zone_b")
        assert zone.risk_level in ("ELEVATED", "HIGH", "CRITICAL")

    def test_computed_at_is_recent(self, conn, engine):
        _insert_event(conn, "zone_a")
        zones = engine.zone_risks()
        ts = datetime.fromisoformat(zones[0].computed_at)
        delta = datetime.now(timezone.utc) - ts
        assert delta.total_seconds() < 5


# ── RiskEngine.repeat_offenders() ────────────────────────────────────────────

class TestRepeatOffenders:
    def test_no_offenders_when_below_threshold(self, conn, engine):
        _insert_event(conn, "z", track_id=1, hours_ago=1)
        _insert_event(conn, "z", track_id=1, hours_ago=2)
        assert engine.repeat_offenders() == []

    def test_offender_detected_at_threshold(self, conn, engine):
        for i in range(3):
            _insert_event(conn, "z", track_id=42, hours_ago=i+1)
        offenders = engine.repeat_offenders()
        assert len(offenders) == 1
        assert offenders[0].track_id == 42
        assert offenders[0].violations_24h == 3
        assert offenders[0].is_repeat_offender is True

    def test_old_violations_excluded(self, conn, engine):
        # 3 violations but all >24h ago
        for i in range(3):
            _insert_event(conn, "z", track_id=99, hours_ago=30+i)
        assert engine.repeat_offenders() == []

    def test_multiple_offenders_sorted_by_count(self, conn, engine):
        for i in range(5):
            _insert_event(conn, "z", track_id=1, hours_ago=i+1)
        for i in range(3):
            _insert_event(conn, "z", track_id=2, hours_ago=i+1)
        offenders = engine.repeat_offenders()
        assert offenders[0].track_id == 1
        assert offenders[0].violations_24h == 5


# ── RiskEngine.site_summary() ────────────────────────────────────────────────

class TestSiteSummary:
    def test_empty_site_returns_low_risk(self, engine):
        s = engine.site_summary()
        assert s.overall_risk_level == "LOW"
        assert s.total_violations_24h == 0
        assert s.repeat_offender_count == 0

    def test_summary_counts_recent_violations(self, conn, engine):
        for i in range(5):
            _insert_event(conn, "zone_a", track_id=i, hours_ago=1)
        s = engine.site_summary()
        assert s.total_violations_24h == 5

    def test_highest_risk_zone_identified(self, conn, engine):
        for i in range(6):
            _insert_event(conn, "danger_zone", track_id=i, hours_ago=1)
        _insert_event(conn, "safe_zone", track_id=99, hours_ago=1)
        s = engine.site_summary()
        assert s.highest_risk_zone == "danger_zone"

    def test_rising_zones_flagged(self, conn, engine):
        for i in range(10):
            _insert_event(conn, "rising_zone", track_id=i, hours_ago=24)
        for i in range(1):
            _insert_event(conn, "rising_zone", track_id=i+10, hours_ago=24*10)
        s = engine.site_summary()
        assert "rising_zone" in s.rising_risk_zones


# ── API endpoints ─────────────────────────────────────────────────────────────

class TestRiskAPI:
    def test_get_zones_empty(self, client):
        c, _ = client
        res = c.get("/risk/zones")
        assert res.status_code == 200
        assert res.json() == []

    def test_get_zones_with_data(self, client):
        c, conn = client
        for i in range(3):
            _insert_event(conn, "zone_a", track_id=i, hours_ago=1)
        res = c.get("/risk/zones")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["zone_id"] == "zone_a"
        assert data[0]["violations_24h"] == 3
        assert "risk_level" in data[0]
        assert "trend" in data[0]

    def test_get_summary(self, client):
        c, conn = client
        _insert_event(conn, "zone_a", hours_ago=1)
        res = c.get("/risk/summary")
        assert res.status_code == 200
        data = res.json()
        assert "overall_risk_level" in data
        assert "total_violations_24h" in data
        assert data["total_violations_24h"] == 1

    def test_get_offenders_empty(self, client):
        c, _ = client
        res = c.get("/risk/workers/offenders")
        assert res.status_code == 200
        assert res.json() == []

    def test_get_offenders_with_data(self, client):
        c, conn = client
        for i in range(3):
            _insert_event(conn, "z", track_id=7, hours_ago=i+1)
        res = c.get("/risk/workers/offenders")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["track_id"] == 7

    def test_requires_auth(self, conn):
        eng = RiskEngine(conn)
        app.dependency_overrides[_get_risk_engine] = lambda: eng
        try:
            c = TestClient(app)
            res = c.get("/risk/zones")
            assert res.status_code in (401, 403)
        finally:
            app.dependency_overrides.pop(_get_risk_engine, None)
