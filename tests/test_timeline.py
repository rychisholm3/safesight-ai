"""
Tests for Phase 8 — Safety Timeline & Compliance Autopilot.

Covers: NotesDB, ComplianceEngine, and HTTP endpoints.
"""
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.timeline.notes import NotesDB, SupervisorNote
from src.timeline.compliance import ComplianceEngine, ComplianceStatus


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mem_conn():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@pytest.fixture
def notes_db(mem_conn):
    return NotesDB(mem_conn)


@pytest.fixture
def compliance(mem_conn):
    # Create events table in memory
    mem_conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT,
            track_id INTEGER,
            created_at TEXT,
            zone_id TEXT,
            missing_ppe TEXT DEFAULT '[]',
            severity TEXT DEFAULT 'WARNING',
            start_frame INTEGER DEFAULT 0,
            end_frame INTEGER,
            snapshot_path TEXT,
            zone_rule TEXT,
            osha_codes TEXT DEFAULT '[]',
            fine_min_usd INTEGER DEFAULT 0,
            fine_max_usd INTEGER DEFAULT 0,
            confidence REAL DEFAULT 0.0,
            bbox TEXT,
            person_detections TEXT
        )
    """)
    mem_conn.commit()
    return ComplianceEngine(mem_conn)


def _insert_event(conn, event_type="missing_ppe", track_id=1, hours_ago=1):
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    conn.execute(
        "INSERT INTO events (event_id, event_type, track_id, created_at) VALUES (?, ?, ?, ?)",
        (f"ev_{event_type}_{track_id}_{hours_ago}", event_type, track_id, ts),
    )
    conn.commit()


# ── NotesDB ───────────────────────────────────────────────────────────────────

class TestNotesDB:
    def test_add_and_get_note(self, notes_db):
        note = notes_db.add_note("event1", "user1", "Spoke to worker.")
        assert isinstance(note, SupervisorNote)
        assert note.event_id == "event1"
        assert note.note == "Spoke to worker."

    def test_get_notes_empty(self, notes_db):
        assert notes_db.get_notes("unknown_event") == []

    def test_get_notes_returns_all(self, notes_db):
        notes_db.add_note("ev1", "u1", "Note A")
        notes_db.add_note("ev1", "u2", "Note B")
        notes = notes_db.get_notes("ev1")
        assert len(notes) == 2
        assert {n.note for n in notes} == {"Note A", "Note B"}

    def test_get_notes_bulk(self, notes_db):
        notes_db.add_note("ev1", "u1", "Note 1")
        notes_db.add_note("ev2", "u1", "Note 2")
        bulk = notes_db.get_notes_bulk(["ev1", "ev2", "ev3"])
        assert len(bulk["ev1"]) == 1
        assert len(bulk["ev2"]) == 1
        assert len(bulk["ev3"]) == 0

    def test_delete_note(self, notes_db):
        note = notes_db.add_note("ev1", "u1", "To delete")
        assert notes_db.delete_note(note.note_id) is True
        assert notes_db.get_notes("ev1") == []

    def test_delete_unknown_note_returns_false(self, notes_db):
        assert notes_db.delete_note("no_such_id") is False

    def test_notes_ordered_by_created_at(self, notes_db):
        notes_db.add_note("ev1", "u1", "First")
        notes_db.add_note("ev1", "u1", "Second")
        notes = notes_db.get_notes("ev1")
        assert notes[0].note == "First"
        assert notes[1].note == "Second"


# ── ComplianceEngine ──────────────────────────────────────────────────────────

class TestComplianceEngine:
    def test_no_events_returns_100_pct_pass(self, compliance):
        status = compliance.current_status()
        assert status.ppe_pct == 100.0
        assert status.zone_pct == 100.0
        assert status.status == "PASS"
        assert status.tracked_workers_24h == 0

    def test_ppe_violation_reduces_ppe_pct(self, compliance, mem_conn):
        # 2 workers seen; 1 has PPE violation
        _insert_event(mem_conn, "missing_ppe",    track_id=1, hours_ago=1)
        _insert_event(mem_conn, "zone_intrusion", track_id=2, hours_ago=1)
        status = compliance.current_status()
        # Worker 1: PPE bad, zone good
        # Worker 2: PPE good, zone bad
        assert status.ppe_pct < 100.0
        assert status.zone_pct < 100.0

    def test_old_events_excluded_from_24h(self, compliance, mem_conn):
        _insert_event(mem_conn, "missing_ppe", track_id=1, hours_ago=25)
        status = compliance.current_status()
        assert status.tracked_workers_24h == 0
        assert status.ppe_pct == 100.0

    def test_all_compliant_returns_pass(self, compliance, mem_conn):
        # No violations — but workers were seen via zone events with no violations
        # (we don't have a "seen" event without violation, so this stays as 100%)
        status = compliance.current_status()
        assert status.status == "PASS"

    def test_fail_when_ppe_below_90(self, compliance, mem_conn):
        # 10 workers, 2 compliant (80% PPE) → FAIL
        for i in range(10):
            _insert_event(mem_conn, "missing_ppe", track_id=i, hours_ago=1)
        status = compliance.current_status()
        assert status.status == "FAIL"

    def test_daily_history_returns_7_days(self, compliance):
        history = compliance.daily_history(days=7)
        assert len(history) == 7

    def test_daily_history_dates_are_sequential(self, compliance):
        history = compliance.daily_history(days=7)
        dates = [h.date for h in history]
        for i in range(1, len(dates)):
            from datetime import date
            d_prev = date.fromisoformat(dates[i - 1])
            d_curr = date.fromisoformat(dates[i])
            assert d_curr == d_prev + timedelta(days=1)

    def test_forecast_returns_value_in_range(self, compliance):
        forecast = compliance.forecast()
        assert 0.0 <= forecast.predicted_pct <= 100.0

    def test_forecast_trend_labels(self, compliance):
        from src.timeline.compliance import DailyCompliance
        # Improving trend
        history = [DailyCompliance(date=f"2024-01-{i+1:02d}", ppe_pct=70+i*3,
                                   zone_pct=70+i*3, overall_pct=70+i*3, event_count=5)
                   for i in range(7)]
        forecast = compliance.forecast(history)
        assert forecast.trend == "RISING"

        # Declining trend
        history2 = [DailyCompliance(date=f"2024-01-{i+1:02d}", ppe_pct=90-i*3,
                                    zone_pct=90-i*3, overall_pct=90-i*3, event_count=5)
                    for i in range(7)]
        forecast2 = compliance.forecast(history2)
        assert forecast2.trend == "FALLING"


# ── HTTP endpoints ────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    from src.api.main import app, get_store, notes_db, compliance_engine
    from src.timeline.router import (
        _get_store      as _tl_get_store,
        _get_notes_db   as _tl_get_notes_db,
        _get_compliance as _tl_get_compliance,
    )
    # Re-apply overrides in case another test module called dependency_overrides.clear()
    app.dependency_overrides[_tl_get_store]      = get_store
    app.dependency_overrides[_tl_get_notes_db]   = lambda: notes_db
    app.dependency_overrides[_tl_get_compliance] = lambda: compliance_engine
    return TestClient(app, raise_server_exceptions=True)


def _auth(client):
    client.post("/auth/register", json={"org_name": "TLOrg", "email": "tl@test.com", "password": "secret123"})
    res = client.post("/auth/login", json={"email": "tl@test.com", "password": "secret123"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


class TestTimelineEndpoint:
    def test_returns_today_by_default(self, client):
        h = _auth(client)
        res = client.get("/timeline", headers=h)
        assert res.status_code == 200
        body = res.json()
        assert "date" in body
        assert "total_events" in body
        assert "hours" in body

    def test_accepts_date_param(self, client):
        h = _auth(client)
        res = client.get("/timeline?date=2024-01-15", headers=h)
        assert res.status_code == 200
        assert res.json()["date"] == "2024-01-15"

    def test_invalid_date_returns_422(self, client):
        h = _auth(client)
        res = client.get("/timeline?date=not-a-date", headers=h)
        assert res.status_code == 422

    def test_requires_auth(self, client):
        assert client.get("/timeline").status_code == 401


class TestComplianceEndpoint:
    def test_returns_status_history_forecast(self, client):
        h = _auth(client)
        res = client.get("/timeline/compliance", headers=h)
        assert res.status_code == 200
        body = res.json()
        assert "status"   in body
        assert "history"  in body
        assert "forecast" in body
        assert body["status"]["pass_fail"] in ("PASS", "FAIL")
        assert len(body["history"]) == 7
        assert body["forecast"]["trend"] in ("RISING", "FALLING", "STABLE")

    def test_requires_auth(self, client):
        assert client.get("/timeline/compliance").status_code == 401


class TestNotesEndpoints:
    def _insert_event(self, client, h) -> str:
        from src.api.main import _store
        from src.events import Event
        ev = Event(
            event_id="note_test_ev01", event_type="missing_ppe",
            track_id=3, zone_id=None, missing_ppe=["hardhat"],
            start_frame=1, end_frame=None, snapshot_path=None,
        )
        _store.save_event(ev)
        return ev.event_id

    def test_add_note(self, client):
        h   = _auth(client)
        eid = self._insert_event(client, h)
        res = client.post(f"/timeline/{eid}/note", json={"note": "Warned worker."}, headers=h)
        assert res.status_code == 200
        body = res.json()
        assert body["note"] == "Warned worker."
        assert body["event_id"] == eid

    def test_get_notes(self, client):
        h   = _auth(client)
        eid = self._insert_event(client, h)
        client.post(f"/timeline/{eid}/note", json={"note": "Note 1"}, headers=h)
        client.post(f"/timeline/{eid}/note", json={"note": "Note 2"}, headers=h)
        res = client.get(f"/timeline/{eid}/notes", headers=h)
        assert res.status_code == 200
        assert len(res.json()) >= 2

    def test_delete_note(self, client):
        h   = _auth(client)
        eid = self._insert_event(client, h)
        add_res = client.post(f"/timeline/{eid}/note", json={"note": "Delete me"}, headers=h)
        note_id = add_res.json()["note_id"]
        del_res = client.delete(f"/timeline/notes/{note_id}", headers=h)
        assert del_res.status_code == 200

    def test_empty_note_rejected(self, client):
        h   = _auth(client)
        eid = self._insert_event(client, h)
        res = client.post(f"/timeline/{eid}/note", json={"note": ""}, headers=h)
        assert res.status_code == 422

    def test_note_on_unknown_event_returns_404(self, client):
        h   = _auth(client)
        res = client.post("/timeline/no_such_event/note", json={"note": "Test"}, headers=h)
        assert res.status_code == 404

    def test_requires_auth(self, client):
        assert client.post("/timeline/abc/note", json={"note": "x"}).status_code == 401


class TestPdfExport:
    def test_returns_pdf(self, client):
        h   = _auth(client)
        res = client.get("/timeline/export.pdf", headers=h)
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/pdf"
        assert res.content[:4] == b"%PDF"

    def test_requires_auth(self, client):
        assert client.get("/timeline/export.pdf").status_code == 401
