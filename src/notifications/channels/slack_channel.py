"""
Slack channel — posts Block Kit violation cards to an Incoming Webhook URL.

No Slack SDK needed — standard urllib.request POST.
"""
import json
import logging
import os
import urllib.request

from src.events import Event

logger = logging.getLogger(__name__)

_DASHBOARD_URL = os.environ.get("SAFESIGHT_DASHBOARD_URL", "http://localhost:5173")

_SEVERITY_EMOJI = {"CRITICAL": ":rotating_light:", "WARNING": ":warning:"}
_SEVERITY_COLOUR = {"CRITICAL": "#dc2626", "WARNING": "#f59e0b"}


def send_slack(webhook_url: str, event: Event) -> None:
    emoji  = _SEVERITY_EMOJI.get(event.severity, ":bell:")
    colour = _SEVERITY_COLOUR.get(event.severity, "#6b7280")
    etype  = event.event_type.replace("_", " ").title()
    zone   = event.zone_id or "—"
    ppe    = ", ".join(event.missing_ppe) if event.missing_ppe else "—"

    payload = {
        "attachments": [
            {
                "color": colour,
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"{emoji} SafeSight {event.severity} Alert",
                        },
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Type*\n{etype}"},
                            {"type": "mrkdwn", "text": f"*Severity*\n{event.severity}"},
                            {"type": "mrkdwn", "text": f"*Zone*\n{zone}"},
                            {"type": "mrkdwn", "text": f"*Missing PPE*\n{ppe}"},
                            {"type": "mrkdwn", "text": f"*Person ID*\n#{event.track_id}"},
                            {"type": "mrkdwn", "text": f"*Event ID*\n`{event.event_id[:8]}…`"},
                        ],
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "View Dashboard"},
                                "url": _DASHBOARD_URL,
                                "style": "primary" if event.severity == "CRITICAL" else None,
                            }
                        ],
                    },
                ],
            }
        ]
    }
    # remove None style field
    btn = payload["attachments"][0]["blocks"][2]["elements"][0]
    if btn.get("style") is None:
        del btn["style"]

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
            logger.info("Slack sent: event_id=%s status=%d", event.event_id, status)
        else:
            logger.warning("Slack returned %d for event_id=%s", status, event.event_id)
    except Exception as exc:
        logger.error("Slack failed: event_id=%s error=%s", event.event_id, exc)
        raise
