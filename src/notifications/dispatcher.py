"""
NotificationDispatcher — orchestrates multi-channel alerts.

Responsibilities
----------------
1. Load every active user and their notification preferences.
2. For each user, check: severity threshold, quiet hours, deduplication.
3. Send via each enabled channel in a background thread.

Integration
-----------
The dispatcher is instantiated in src/api/main.py and registered on
the EventBroadcaster.  When the pipeline calls broadcaster.publish()
with action="opened", the broadcaster calls dispatcher.dispatch(event).
"""
import logging
import threading
from datetime import datetime, timezone

from src.auth.db import AuthDB
from src.pipeline.events import Event
from src.notifications.channels.email_channel import EmailConfig, send_email
from src.notifications.channels.slack_channel import send_slack
from src.notifications.channels.sms_channel import TwilioConfig, send_sms
from src.notifications.channels.teams_channel import send_teams
from src.notifications.db import NotificationDB
from src.notifications.models import NotificationPrefs

logger = logging.getLogger(__name__)


def _in_quiet_hours(prefs: NotificationPrefs) -> bool:
    if not prefs.quiet_start or not prefs.quiet_end:
        return False
    now = datetime.now(timezone.utc).strftime("%H:%M")
    qs, qe = prefs.quiet_start, prefs.quiet_end
    if qs <= qe:
        return qs <= now < qe
    # overnight range e.g. 22:00 – 06:00
    return now >= qs or now < qe


def _severity_meets_threshold(event_severity: str, min_severity: str) -> bool:
    if min_severity == "CRITICAL":
        return event_severity == "CRITICAL"
    return True  # "WARNING" → send all


class NotificationDispatcher:
    """Thread-safe, non-blocking dispatcher for multi-channel alerts."""

    def __init__(
        self,
        notification_db: NotificationDB,
        auth_db: AuthDB,
        email_config: EmailConfig | None = None,
        twilio_config: TwilioConfig | None = None,
    ) -> None:
        self._ndb    = notification_db
        self._adb    = auth_db
        self._email  = email_config
        self._twilio = twilio_config

    def dispatch(self, event: Event) -> None:
        """Non-blocking: runs delivery in a daemon thread."""
        threading.Thread(
            target=self._do_dispatch, args=(event,), daemon=True,
            name=f"notify-{event.event_id[:8]}",
        ).start()

    def _do_dispatch(self, event: Event) -> None:
        try:
            users = self._adb.list_all_users()
        except Exception as exc:
            logger.error("NotificationDispatcher: failed to load users: %s", exc)
            return

        for user in users:
            if not user.is_active:
                continue
            try:
                prefs = self._ndb.get_prefs(user.user_id)
                self._notify_user(event, user, prefs)
            except Exception as exc:
                logger.error(
                    "NotificationDispatcher: error notifying user=%s: %s",
                    user.user_id, exc,
                )

    def _notify_user(self, event: Event, user, prefs: NotificationPrefs) -> None:
        if not _severity_meets_threshold(event.severity, prefs.min_severity):
            return
        if _in_quiet_hours(prefs):
            return

        if prefs.email_enabled:
            dest = prefs.email_to or user.email
            self._try_send("email", event, prefs.user_id,
                           lambda: send_email(self._email, dest, event)
                           if self._email else logger.warning(
                               "Email channel not configured — skipping user=%s", user.user_id))

        if prefs.sms_enabled and event.severity == "CRITICAL":
            if prefs.phone_number:
                self._try_send("sms", event, prefs.user_id,
                               lambda: send_sms(self._twilio, prefs.phone_number, event)
                               if self._twilio else logger.warning(
                                   "Twilio not configured — skipping user=%s", user.user_id))

        if prefs.slack_enabled and prefs.slack_webhook:
            self._try_send("slack", event, prefs.user_id,
                           lambda: send_slack(prefs.slack_webhook, event))

        if prefs.teams_enabled and prefs.teams_webhook:
            self._try_send("teams", event, prefs.user_id,
                           lambda: send_teams(prefs.teams_webhook, event))

    def _try_send(self, channel: str, event: Event, user_id: str, send_fn) -> None:
        if self._ndb.has_sent(event.event_id, channel, user_id):
            logger.debug("Dedup: skipping %s for event_id=%s user=%s",
                         channel, event.event_id, user_id)
            return
        try:
            send_fn()
            self._ndb.mark_sent(event.event_id, channel, user_id)
        except Exception as exc:
            logger.error("Channel %s failed for event_id=%s user=%s: %s",
                         channel, event.event_id, user_id, exc)
