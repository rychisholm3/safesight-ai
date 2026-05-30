"""
Database schema and Python models for notification preferences.

Tables
------
notification_prefs  – per-user channel settings and routing info
notification_sent   – deduplication log (event_id + channel + user_id)
"""
import sqlite3
from dataclasses import dataclass, field


@dataclass
class NotificationPrefs:
    user_id: str
    email_enabled: bool = False
    sms_enabled: bool = False
    slack_enabled: bool = False
    teams_enabled: bool = False
    min_severity: str = "WARNING"   # "WARNING" = all events; "CRITICAL" = critical only
    quiet_start: str | None = None  # "HH:MM" UTC, e.g. "22:00"
    quiet_end: str | None = None    # "HH:MM" UTC, e.g. "06:00"
    email_to: str | None = None     # destination address (defaults to user.email)
    phone_number: str | None = None # E.164 for SMS, e.g. "+14155552671"
    slack_webhook: str | None = None
    teams_webhook: str | None = None


_DDL = """
CREATE TABLE IF NOT EXISTS notification_prefs (
    user_id       TEXT PRIMARY KEY REFERENCES users(user_id),
    email_enabled INTEGER NOT NULL DEFAULT 0,
    sms_enabled   INTEGER NOT NULL DEFAULT 0,
    slack_enabled INTEGER NOT NULL DEFAULT 0,
    teams_enabled INTEGER NOT NULL DEFAULT 0,
    min_severity  TEXT NOT NULL DEFAULT 'WARNING',
    quiet_start   TEXT,
    quiet_end     TEXT,
    email_to      TEXT,
    phone_number  TEXT,
    slack_webhook TEXT,
    teams_webhook TEXT
);

CREATE TABLE IF NOT EXISTS notification_sent (
    event_id TEXT NOT NULL,
    channel  TEXT NOT NULL,
    user_id  TEXT NOT NULL,
    sent_at  TEXT NOT NULL,
    PRIMARY KEY (event_id, channel, user_id)
);
"""


def create_notification_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(_DDL)
    conn.commit()
