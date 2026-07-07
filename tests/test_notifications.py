"""
Tests for Phase 2 — Multi-Channel Notifications.

Covers:
- NotificationDB CRUD and deduplication
- Quiet-hours logic
- Severity threshold filtering
- NotificationDispatcher routing
- API endpoints GET/PUT /notifications/prefs
"""
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.auth.dependencies import require_auth
from src.auth.models import Role, User
from src.pipeline.events import Event
from src.notifications.channels.email_channel import _build_html
from src.notifications.channels.slack_channel import send_slack
from src.notifications.channels.sms_channel import _build_body, TwilioConfig
from src.notifications.channels.teams_channel import send_teams
from src.notifications.db import NotificationDB
from src.notifications.dispatcher import (
    NotificationDispatcher,
    _in_quiet_hours,
    _severity_meets_threshold,
)
from src.notifications.models import NotificationPrefs
from src.notifications.router import _get_notification_db


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    # auth tables needed for FK references
    from src.auth.models import create_auth_tables
    create_auth_tables(c)
    return c


@pytest.fixture()
def ndb(conn):
    return NotificationDB(conn)


def _make_user(**kwargs) -> User:
    defaults = dict(
        user_id="u1", org_id="org1", email="test@example.com",
        hashed_password="x", role=Role.safety_officer,
        is_active=True, created_at="2025-01-01",
    )
    defaults.update(kwargs)
    return User(**defaults)


def _make_event(**kwargs) -> Event:
    defaults = dict(
        event_id="evt-001",
        event_type="missing_ppe",
        track_id=1,
        start_frame=0,
        end_frame=None,
        zone_id=None,
        missing_ppe=["hardhat"],
        snapshot_path=None,
        severity="WARNING",
    )
    defaults.update(kwargs)
    return Event(**defaults)


@pytest.fixture()
def fake_user():
    return _make_user()


@pytest.fixture()
def client(conn, fake_user):
    ndb = NotificationDB(conn)
    app.dependency_overrides[require_auth] = lambda: fake_user
    app.dependency_overrides[_get_notification_db] = lambda: ndb
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── NotificationDB ────────────────────────────────────────────────────────────

class TestNotificationDB:
    def test_get_prefs_default(self, ndb):
        p = ndb.get_prefs("user-unknown")
        assert p.user_id == "user-unknown"
        assert p.email_enabled is False
        assert p.min_severity == "WARNING"

    def test_upsert_and_get(self, ndb):
        prefs = NotificationPrefs(
            user_id="u1",
            email_enabled=True,
            slack_enabled=True,
            slack_webhook="https://hooks.slack.com/test",
            min_severity="CRITICAL",
        )
        ndb.upsert_prefs(prefs)
        got = ndb.get_prefs("u1")
        assert got.email_enabled is True
        assert got.slack_enabled is True
        assert got.min_severity == "CRITICAL"
        assert got.slack_webhook == "https://hooks.slack.com/test"

    def test_upsert_overwrites(self, ndb):
        ndb.upsert_prefs(NotificationPrefs(user_id="u1", email_enabled=True))
        ndb.upsert_prefs(NotificationPrefs(user_id="u1", email_enabled=False))
        assert ndb.get_prefs("u1").email_enabled is False

    def test_dedup_not_sent(self, ndb):
        assert ndb.has_sent("evt1", "email", "u1") is False

    def test_dedup_mark_and_check(self, ndb):
        ndb.mark_sent("evt1", "email", "u1")
        assert ndb.has_sent("evt1", "email", "u1") is True

    def test_dedup_different_channel(self, ndb):
        ndb.mark_sent("evt1", "email", "u1")
        assert ndb.has_sent("evt1", "slack", "u1") is False

    def test_dedup_idempotent(self, ndb):
        ndb.mark_sent("evt1", "email", "u1")
        ndb.mark_sent("evt1", "email", "u1")  # no error
        assert ndb.has_sent("evt1", "email", "u1") is True


# ── Quiet hours logic ─────────────────────────────────────────────────────────

class TestQuietHours:
    def _prefs(self, start, end):
        return NotificationPrefs(user_id="u", quiet_start=start, quiet_end=end)

    def test_no_quiet_hours(self):
        assert _in_quiet_hours(NotificationPrefs(user_id="u")) is False

    def test_within_normal_range(self):
        with patch("src.notifications.dispatcher.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 1, 14, 0, tzinfo=timezone.utc)
            mock_dt.now.return_value = MagicMock()
            mock_dt.now.return_value.strftime.return_value = "14:00"
            assert _in_quiet_hours(self._prefs("13:00", "15:00")) is True

    def test_outside_normal_range(self):
        with patch("src.notifications.dispatcher.datetime") as mock_dt:
            mock_dt.now.return_value = MagicMock()
            mock_dt.now.return_value.strftime.return_value = "10:00"
            assert _in_quiet_hours(self._prefs("13:00", "15:00")) is False

    def test_overnight_inside(self):
        with patch("src.notifications.dispatcher.datetime") as mock_dt:
            mock_dt.now.return_value = MagicMock()
            mock_dt.now.return_value.strftime.return_value = "23:30"
            assert _in_quiet_hours(self._prefs("22:00", "06:00")) is True

    def test_overnight_outside(self):
        with patch("src.notifications.dispatcher.datetime") as mock_dt:
            mock_dt.now.return_value = MagicMock()
            mock_dt.now.return_value.strftime.return_value = "12:00"
            assert _in_quiet_hours(self._prefs("22:00", "06:00")) is False


# ── Severity threshold ────────────────────────────────────────────────────────

class TestSeverityThreshold:
    def test_warning_threshold_allows_warning(self):
        assert _severity_meets_threshold("WARNING", "WARNING") is True

    def test_warning_threshold_allows_critical(self):
        assert _severity_meets_threshold("CRITICAL", "WARNING") is True

    def test_critical_threshold_blocks_warning(self):
        assert _severity_meets_threshold("WARNING", "CRITICAL") is False

    def test_critical_threshold_allows_critical(self):
        assert _severity_meets_threshold("CRITICAL", "CRITICAL") is True


# ── Dispatcher routing ────────────────────────────────────────────────────────

class TestDispatcher:
    def _make_dispatcher(self, ndb, users):
        auth_db = MagicMock()
        auth_db.list_all_users.return_value = users
        return NotificationDispatcher(ndb, auth_db)

    def test_slack_called_when_enabled(self, ndb):
        ndb.upsert_prefs(NotificationPrefs(
            user_id="u1", slack_enabled=True,
            slack_webhook="https://hooks.slack.com/test",
        ))
        user = _make_user()
        d = self._make_dispatcher(ndb, [user])
        event = _make_event()

        with patch("src.notifications.dispatcher.send_slack") as mock_slack:
            d._do_dispatch(event)
            mock_slack.assert_called_once_with("https://hooks.slack.com/test", event)

    def test_dedup_prevents_double_send(self, ndb):
        ndb.upsert_prefs(NotificationPrefs(
            user_id="u1", slack_enabled=True,
            slack_webhook="https://hooks.slack.com/test",
        ))
        user = _make_user()
        d = self._make_dispatcher(ndb, [user])
        event = _make_event()

        with patch("src.notifications.dispatcher.send_slack") as mock_slack:
            d._do_dispatch(event)
            d._do_dispatch(event)  # second call should be deduped
            mock_slack.assert_called_once()

    def test_severity_threshold_blocks_warning(self, ndb):
        ndb.upsert_prefs(NotificationPrefs(
            user_id="u1", slack_enabled=True,
            slack_webhook="https://hooks.slack.com/test",
            min_severity="CRITICAL",
        ))
        user = _make_user()
        d = self._make_dispatcher(ndb, [user])
        event = _make_event(severity="WARNING")

        with patch("src.notifications.dispatcher.send_slack") as mock_slack:
            d._do_dispatch(event)
            mock_slack.assert_not_called()

    def test_sms_only_for_critical(self, ndb):
        config = TwilioConfig("sid", "token", "+15005550006")
        ndb.upsert_prefs(NotificationPrefs(
            user_id="u1", sms_enabled=True, phone_number="+14155551234",
        ))
        user = _make_user()
        auth_db = MagicMock()
        auth_db.list_all_users.return_value = [user]
        d = NotificationDispatcher(ndb, auth_db, twilio_config=config)

        with patch("src.notifications.dispatcher.send_sms") as mock_sms:
            d._do_dispatch(_make_event(severity="WARNING"))
            mock_sms.assert_not_called()

            d._do_dispatch(_make_event(event_id="evt-002", severity="CRITICAL"))
            mock_sms.assert_called_once()

    def test_inactive_user_skipped(self, ndb):
        ndb.upsert_prefs(NotificationPrefs(
            user_id="u1", slack_enabled=True,
            slack_webhook="https://hooks.slack.com/test",
        ))
        user = _make_user(is_active=False)
        d = self._make_dispatcher(ndb, [user])

        with patch("src.notifications.dispatcher.send_slack") as mock_slack:
            d._do_dispatch(_make_event())
            mock_slack.assert_not_called()


# ── Channel helpers ───────────────────────────────────────────────────────────

class TestChannelHelpers:
    def test_email_html_contains_severity(self):
        html = _build_html(_make_event(severity="CRITICAL"))
        assert "CRITICAL" in html

    def test_sms_body_truncated_at_160(self):
        body = _build_body(_make_event(zone_id="a" * 200))
        assert len(body) <= 160

    def test_sms_body_critical_label(self):
        body = _build_body(_make_event(severity="CRITICAL", event_type="zone_intrusion"))
        assert "CRITICAL" in body


# ── API endpoints ─────────────────────────────────────────────────────────────

class TestNotificationAPI:
    def test_get_prefs_default(self, client):
        res = client.get("/notifications/prefs")
        assert res.status_code == 200
        data = res.json()
        assert data["email_enabled"] is False
        assert data["min_severity"] == "WARNING"

    def test_put_prefs(self, client):
        res = client.put("/notifications/prefs", json={
            "email_enabled": True,
            "slack_enabled": True,
            "slack_webhook": "https://hooks.slack.com/abc",
            "min_severity": "CRITICAL",
            "sms_enabled": False,
            "teams_enabled": False,
            "quiet_start": "22:00",
            "quiet_end": "06:00",
            "email_to": None,
            "phone_number": None,
            "teams_webhook": None,
        })
        assert res.status_code == 200
        data = res.json()
        assert data["email_enabled"] is True
        assert data["min_severity"] == "CRITICAL"
        assert data["slack_webhook"] == "https://hooks.slack.com/abc"
        assert data["quiet_start"] == "22:00"

    def test_put_prefs_invalid_time(self, client):
        res = client.put("/notifications/prefs", json={
            "email_enabled": False, "sms_enabled": False,
            "slack_enabled": False, "teams_enabled": False,
            "min_severity": "WARNING", "quiet_start": "25:00",
            "quiet_end": None, "email_to": None, "phone_number": None,
            "slack_webhook": None, "teams_webhook": None,
        })
        assert res.status_code == 422

    def test_requires_auth(self, conn):
        ndb = NotificationDB(conn)
        # only wire notification_db, leave auth override absent
        app.dependency_overrides[_get_notification_db] = lambda: ndb
        try:
            c = TestClient(app)
            res = c.get("/notifications/prefs")
            assert res.status_code in (401, 403)
        finally:
            app.dependency_overrides.pop(_get_notification_db, None)
