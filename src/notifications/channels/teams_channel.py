"""
Microsoft Teams channel — posts Adaptive Card violation alerts to a Teams Incoming Webhook.

No Teams SDK needed — standard urllib.request POST.
"""
import json
import logging
import os
import urllib.request

from src.events import Event

logger = logging.getLogger(__name__)

_DASHBOARD_URL = os.environ.get("SAFESIGHT_DASHBOARD_URL", "http://localhost:5173")

_SEVERITY_COLOUR = {"CRITICAL": "attention", "WARNING": "warning"}


def send_teams(webhook_url: str, event: Event) -> None:
    colour = _SEVERITY_COLOUR.get(event.severity, "default")
    etype  = event.event_type.replace("_", " ").title()
    zone   = event.zone_id or "—"
    ppe    = ", ".join(event.missing_ppe) if event.missing_ppe else "—"

    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": f"SafeSight {event.severity} Alert",
                            "size": "Large",
                            "weight": "Bolder",
                            "color": colour,
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Type",        "value": etype},
                                {"title": "Severity",    "value": event.severity},
                                {"title": "Zone",        "value": zone},
                                {"title": "Missing PPE", "value": ppe},
                                {"title": "Person ID",   "value": f"#{event.track_id}"},
                                {"title": "Event ID",    "value": event.event_id[:12] + "…"},
                            ],
                        },
                    ],
                    "actions": [
                        {
                            "type": "Action.OpenUrl",
                            "title": "View Dashboard",
                            "url": _DASHBOARD_URL,
                        }
                    ],
                    "msteams": {"width": "Full"},
                },
            }
        ],
    }

    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        webhook_url, data=data,
        headers={"Content-Type": "application/json", "User-Agent": "SafeSight-AI/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            status = resp.status
        if status < 300:
            logger.info("Teams sent: event_id=%s status=%d", event.event_id, status)
        else:
            logger.warning("Teams returned %d for event_id=%s", status, event.event_id)
    except Exception as exc:
        logger.error("Teams failed: event_id=%s error=%s", event.event_id, exc)
        raise
