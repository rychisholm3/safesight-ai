"""
FastAPI router for notification preferences.

GET  /notifications/prefs   — return current user's prefs
PUT  /notifications/prefs   — update current user's prefs
POST /notifications/test    — send a test notification on all enabled channels
"""
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from src.auth.dependencies import require_auth
from src.auth.models import User
from src.notifications.db import NotificationDB
from src.notifications.models import NotificationPrefs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ── Dependency injected by main.py ────────────────────────────────────────────
# Populated at startup; overridable in tests via app.dependency_overrides.

def _get_notification_db() -> NotificationDB:  # pragma: no cover
    raise RuntimeError("notification_db not wired — check src/api/main.py")


NotificationDBDep = Annotated[NotificationDB, Depends(_get_notification_db)]


# ── Request / Response models ─────────────────────────────────────────────────

class PrefsRequest(BaseModel):
    email_enabled: bool = False
    sms_enabled:   bool = False
    slack_enabled: bool = False
    teams_enabled: bool = False
    min_severity:  Literal["WARNING", "CRITICAL"] = "WARNING"
    quiet_start:   str | None = None
    quiet_end:     str | None = None
    email_to:      str | None = None
    phone_number:  str | None = None
    slack_webhook: str | None = None
    teams_webhook: str | None = None

    @field_validator("quiet_start", "quiet_end")
    @classmethod
    def _valid_time(cls, v: str | None) -> str | None:
        if v is None:
            return v
        parts = v.split(":")
        if len(parts) != 2:
            raise ValueError("must be HH:MM format")
        h, m = parts
        if not (h.isdigit() and m.isdigit() and 0 <= int(h) <= 23 and 0 <= int(m) <= 59):
            raise ValueError("must be HH:MM in 00:00–23:59 range")
        return v


class PrefsResponse(BaseModel):
    user_id:       str
    email_enabled: bool
    sms_enabled:   bool
    slack_enabled: bool
    teams_enabled: bool
    min_severity:  str
    quiet_start:   str | None
    quiet_end:     str | None
    email_to:      str | None
    phone_number:  str | None
    slack_webhook: str | None
    teams_webhook: str | None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/prefs", response_model=PrefsResponse)
def get_prefs(
    ndb: NotificationDBDep,
    current_user: User = Depends(require_auth),
) -> PrefsResponse:
    prefs = ndb.get_prefs(current_user.user_id)
    return PrefsResponse(
        user_id       = prefs.user_id,
        email_enabled = prefs.email_enabled,
        sms_enabled   = prefs.sms_enabled,
        slack_enabled = prefs.slack_enabled,
        teams_enabled = prefs.teams_enabled,
        min_severity  = prefs.min_severity,
        quiet_start   = prefs.quiet_start,
        quiet_end     = prefs.quiet_end,
        email_to      = prefs.email_to,
        phone_number  = prefs.phone_number,
        slack_webhook = prefs.slack_webhook,
        teams_webhook = prefs.teams_webhook,
    )


@router.put("/prefs", response_model=PrefsResponse)
def put_prefs(
    body: PrefsRequest,
    ndb: NotificationDBDep,
    current_user: User = Depends(require_auth),
) -> PrefsResponse:
    prefs = NotificationPrefs(
        user_id       = current_user.user_id,
        email_enabled = body.email_enabled,
        sms_enabled   = body.sms_enabled,
        slack_enabled = body.slack_enabled,
        teams_enabled = body.teams_enabled,
        min_severity  = body.min_severity,
        quiet_start   = body.quiet_start,
        quiet_end     = body.quiet_end,
        email_to      = body.email_to,
        phone_number  = body.phone_number,
        slack_webhook = body.slack_webhook,
        teams_webhook = body.teams_webhook,
    )
    ndb.upsert_prefs(prefs)
    logger.info("Notification prefs updated for user_id=%s", current_user.user_id)
    return get_prefs(ndb, current_user)
