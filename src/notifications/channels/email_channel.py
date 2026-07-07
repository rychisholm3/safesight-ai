"""
Email channel — sends HTML violation alerts via SMTP.

Config is loaded from environment variables:
    SAFESIGHT_SMTP_HOST   (required to enable)
    SAFESIGHT_SMTP_PORT   (default: 587)
    SAFESIGHT_SMTP_USER
    SAFESIGHT_SMTP_PASS
    SAFESIGHT_SMTP_FROM   (defaults to SAFESIGHT_SMTP_USER)
    SAFESIGHT_SMTP_TLS    ("false" to disable STARTTLS)
    SAFESIGHT_DASHBOARD_URL (default: http://localhost:5173)
"""
import logging
import os
import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.pipeline.events import Event

logger = logging.getLogger(__name__)

_DASHBOARD_URL = os.environ.get("SAFESIGHT_DASHBOARD_URL", "http://localhost:5173")

_SEVERITY_COLOUR = {"CRITICAL": "#dc2626", "WARNING": "#f59e0b"}


@dataclass
class EmailConfig:
    host: str
    port: int
    username: str
    password: str
    from_addr: str
    use_tls: bool = True

    @classmethod
    def from_env(cls) -> "EmailConfig | None":
        host = os.environ.get("SAFESIGHT_SMTP_HOST")
        if not host:
            return None
        port = int(os.environ.get("SAFESIGHT_SMTP_PORT", "587"))
        user = os.environ.get("SAFESIGHT_SMTP_USER", "")
        pw   = os.environ.get("SAFESIGHT_SMTP_PASS", "")
        from_ = os.environ.get("SAFESIGHT_SMTP_FROM") or user
        tls  = os.environ.get("SAFESIGHT_SMTP_TLS", "true").lower() != "false"
        return cls(host=host, port=port, username=user, password=pw,
                   from_addr=from_, use_tls=tls)


def _build_html(event: Event) -> str:
    colour = _SEVERITY_COLOUR.get(event.severity, "#6b7280")
    etype  = event.event_type.replace("_", " ").title()
    zone   = event.zone_id or "—"
    ppe    = ", ".join(event.missing_ppe) if event.missing_ppe else "—"
    return f"""
<html><body style="font-family: system-ui, sans-serif; background:#f5f6fa; padding:24px;">
  <div style="max-width:520px;margin:0 auto;background:#fff;border-radius:12px;
              box-shadow:0 2px 12px rgba(0,0,0,.08);overflow:hidden;">
    <div style="background:{colour};padding:16px 24px;">
      <h2 style="margin:0;color:#fff;font-size:18px;">SafeSight Alert</h2>
      <p style="margin:4px 0 0;color:rgba(255,255,255,.85);font-size:13px;">
        {event.severity} violation detected
      </p>
    </div>
    <div style="padding:24px;">
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <tr><td style="padding:6px 0;color:#6b7280;width:130px;">Type</td>
            <td style="padding:6px 0;font-weight:600;">{etype}</td></tr>
        <tr><td style="padding:6px 0;color:#6b7280;">Severity</td>
            <td style="padding:6px 0;font-weight:600;color:{colour};">{event.severity}</td></tr>
        <tr><td style="padding:6px 0;color:#6b7280;">Zone</td>
            <td style="padding:6px 0;">{zone}</td></tr>
        <tr><td style="padding:6px 0;color:#6b7280;">Missing PPE</td>
            <td style="padding:6px 0;">{ppe}</td></tr>
        <tr><td style="padding:6px 0;color:#6b7280;">Person ID</td>
            <td style="padding:6px 0;">#{event.track_id}</td></tr>
        <tr><td style="padding:6px 0;color:#6b7280;">Event ID</td>
            <td style="padding:6px 0;font-size:12px;color:#9ca3af;">{event.event_id}</td></tr>
      </table>
      <div style="margin-top:20px;">
        <a href="{_DASHBOARD_URL}" style="display:inline-block;padding:10px 20px;
           background:#1a1a2e;color:#fff;border-radius:6px;text-decoration:none;
           font-size:13px;font-weight:600;">View Dashboard →</a>
      </div>
    </div>
  </div>
</body></html>
"""


def send_email(config: EmailConfig, to: str, event: Event) -> None:
    subject = f"[SafeSight {event.severity}] {event.event_type.replace('_', ' ').title()}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = config.from_addr
    msg["To"]      = to
    msg.attach(MIMEText(_build_html(event), "html"))

    try:
        if config.use_tls:
            with smtplib.SMTP(config.host, config.port, timeout=10) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                if config.username:
                    smtp.login(config.username, config.password)
                smtp.sendmail(config.from_addr, [to], msg.as_string())
        else:
            with smtplib.SMTP(config.host, config.port, timeout=10) as smtp:
                if config.username:
                    smtp.login(config.username, config.password)
                smtp.sendmail(config.from_addr, [to], msg.as_string())
        logger.info("Email sent: to=%s event_id=%s", to, event.event_id)
    except Exception as exc:
        logger.error("Email failed: to=%s event_id=%s error=%s", to, event.event_id, exc)
        raise
