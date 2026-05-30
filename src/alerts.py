"""
Webhook alerter — posts violation events to an operator-configured HTTP endpoint.

Critical events (zone intrusions) are sent immediately; warnings (missing PPE)
are also sent but operators can filter by severity on their end.

Delivery happens on a background thread so it never blocks the inference pipeline.
Failed POSTs are retried with exponential backoff (3 attempts max).

Usage:
    alerter = WebhookAlerter(url="https://hooks.example.com/safesight")
    alerter.send(event)        # non-blocking
    alerter.shutdown(wait=True)  # drain queue before exit
"""
import json
import logging
import queue
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.events import Event

logger = logging.getLogger(__name__)

_SENTINEL = object()
_MAX_RETRIES = 3
_BASE_DELAY = 1.0  # seconds


def _event_to_dict(event: Event) -> dict[str, Any]:
    d = asdict(event)
    if isinstance(d.get("snapshot_path"), str):
        pass  # already a string via asdict
    elif d.get("snapshot_path") is not None:
        d["snapshot_path"] = str(d["snapshot_path"])
    return d


class WebhookAlerter:
    """Thread-safe webhook dispatcher with retry."""

    def __init__(self, url: str, timeout: float = 5.0) -> None:
        self._url = url
        self._timeout = timeout
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._worker, daemon=True, name="webhook-alerter")
        self._thread.start()
        logger.info("WebhookAlerter ready: url=%s", url)

    def send(self, event: Event) -> None:
        """Enqueue event for delivery. Non-blocking."""
        self._queue.put(event)

    def shutdown(self, wait: bool = True) -> None:
        """Stop the background thread. If wait=True, drains the queue first."""
        self._queue.put(_SENTINEL)
        if wait:
            self._thread.join(timeout=30)

    def _worker(self) -> None:
        try:
            import urllib.request
        except ImportError:
            logger.error("urllib.request not available — webhook alerts disabled")
            return

        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                break
            self._dispatch(item, urllib.request)

    def _dispatch(self, event: Event, urllib_request: Any) -> None:
        payload = json.dumps(_event_to_dict(event)).encode()
        headers = {"Content-Type": "application/json", "User-Agent": "SafeSight-AI/1.0"}

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                req = urllib_request.Request(
                    self._url, data=payload, headers=headers, method="POST"
                )
                with urllib_request.urlopen(req, timeout=self._timeout) as resp:
                    status = resp.status
                if status < 300:
                    logger.info(
                        "Webhook delivered: event_id=%s severity=%s status=%d",
                        event.event_id, event.severity, status,
                    )
                    return
                logger.warning(
                    "Webhook returned %d for event_id=%s (attempt %d/%d)",
                    status, event.event_id, attempt, _MAX_RETRIES,
                )
            except Exception as exc:
                logger.warning(
                    "Webhook failed for event_id=%s (attempt %d/%d): %s",
                    event.event_id, attempt, _MAX_RETRIES, exc,
                )

            if attempt < _MAX_RETRIES:
                delay = _BASE_DELAY * (2 ** (attempt - 1))
                time.sleep(delay)

        logger.error(
            "Webhook delivery abandoned after %d attempts: event_id=%s",
            _MAX_RETRIES, event.event_id,
        )
