"""
Notification database — prefs CRUD and deduplication tracking.
"""
import sqlite3
from datetime import datetime, timezone

from src.notifications.models import NotificationPrefs, create_notification_tables


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class NotificationDB:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        create_notification_tables(self._conn)

    def get_prefs(self, user_id: str) -> NotificationPrefs:
        """Return prefs for user_id, creating a default row if missing."""
        row = self._conn.execute(
            "SELECT * FROM notification_prefs WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return NotificationPrefs(user_id=user_id)
        d = dict(row)
        d["email_enabled"] = bool(d["email_enabled"])
        d["sms_enabled"]   = bool(d["sms_enabled"])
        d["slack_enabled"] = bool(d["slack_enabled"])
        d["teams_enabled"] = bool(d["teams_enabled"])
        return NotificationPrefs(**d)

    def upsert_prefs(self, prefs: NotificationPrefs) -> None:
        self._conn.execute(
            """
            INSERT INTO notification_prefs
                (user_id, email_enabled, sms_enabled, slack_enabled, teams_enabled,
                 min_severity, quiet_start, quiet_end, email_to, phone_number,
                 slack_webhook, teams_webhook)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                email_enabled = excluded.email_enabled,
                sms_enabled   = excluded.sms_enabled,
                slack_enabled = excluded.slack_enabled,
                teams_enabled = excluded.teams_enabled,
                min_severity  = excluded.min_severity,
                quiet_start   = excluded.quiet_start,
                quiet_end     = excluded.quiet_end,
                email_to      = excluded.email_to,
                phone_number  = excluded.phone_number,
                slack_webhook = excluded.slack_webhook,
                teams_webhook = excluded.teams_webhook
            """,
            (
                prefs.user_id,
                int(prefs.email_enabled),
                int(prefs.sms_enabled),
                int(prefs.slack_enabled),
                int(prefs.teams_enabled),
                prefs.min_severity,
                prefs.quiet_start,
                prefs.quiet_end,
                prefs.email_to,
                prefs.phone_number,
                prefs.slack_webhook,
                prefs.teams_webhook,
            ),
        )
        self._conn.commit()

    def has_sent(self, event_id: str, channel: str, user_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM notification_sent WHERE event_id=? AND channel=? AND user_id=?",
            (event_id, channel, user_id),
        ).fetchone()
        return row is not None

    def mark_sent(self, event_id: str, channel: str, user_id: str) -> None:
        try:
            self._conn.execute(
                "INSERT INTO notification_sent (event_id, channel, user_id, sent_at) "
                "VALUES (?, ?, ?, ?)",
                (event_id, channel, user_id, _now()),
            )
            self._conn.commit()
        except sqlite3.IntegrityError:
            pass  # already recorded — idempotent
