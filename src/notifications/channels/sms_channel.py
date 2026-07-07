"""
SMS channel — sends critical violation alerts via Twilio REST API.

No Twilio SDK needed — standard urllib.request + HTTP Basic auth.

Config from environment variables:
    SAFESIGHT_TWILIO_SID    (Account SID)
    SAFESIGHT_TWILIO_TOKEN  (Auth token)
    SAFESIGHT_TWILIO_FROM   (E.164 sender number, e.g. +15005550006)
    SAFESIGHT_DASHBOARD_URL (default: http://localhost:5173)
"""
import base64
import json
import logging
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass

from src.pipeline.events import Event

logger = logging.getLogger(__name__)

_DASHBOARD_URL = os.environ.get("SAFESIGHT_DASHBOARD_URL", "http://localhost:5173")
_TWILIO_API    = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"


@dataclass
class TwilioConfig:
    account_sid: str
    auth_token:  str
    from_number: str  # E.164

    @classmethod
    def from_env(cls) -> "TwilioConfig | None":
        sid   = os.environ.get("SAFESIGHT_TWILIO_SID")
        token = os.environ.get("SAFESIGHT_TWILIO_TOKEN")
        from_ = os.environ.get("SAFESIGHT_TWILIO_FROM")
        if not (sid and token and from_):
            return None
        return cls(account_sid=sid, auth_token=token, from_number=from_)


def _build_body(event: Event) -> str:
    etype = event.event_type.replace("_", " ").title()
    zone  = f" in {event.zone_id}" if event.zone_id else ""
    return (
        f"SafeSight {event.severity}: {etype}{zone}, Person #{event.track_id}. "
        f"View: {_DASHBOARD_URL}"
    )[:160]  # SMS body limit


def send_sms(config: TwilioConfig, to: str, event: Event) -> None:
    url  = _TWILIO_API.format(sid=config.account_sid)
    body = urllib.parse.urlencode({
        "To":   to,
        "From": config.from_number,
        "Body": _build_body(event),
    }).encode()

    creds = base64.b64encode(
        f"{config.account_sid}:{config.auth_token}".encode()
    ).decode()

    req = urllib.request.Request(
        url, data=body,
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type":  "application/x-www-form-urlencoded",
            "User-Agent":    "SafeSight-AI/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            result = json.loads(resp.read())
        if status in (200, 201):
            logger.info("SMS sent: to=%s sid=%s event_id=%s",
                        to, result.get("sid"), event.event_id)
        else:
            logger.warning("SMS returned %d for event_id=%s", status, event.event_id)
    except Exception as exc:
        logger.error("SMS failed: to=%s event_id=%s error=%s", to, event.event_id, exc)
        raise
