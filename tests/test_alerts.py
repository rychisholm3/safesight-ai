"""Tests for WebhookAlerter — uses a mock HTTP server to avoid real network calls."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from src.pipeline.alerts import WebhookAlerter
from src.pipeline.events import Event


def make_event(severity: str = "CRITICAL") -> Event:
    return Event(
        event_id="evt001",
        event_type="zone_intrusion",
        track_id=3,
        zone_id="forklift_lane",
        missing_ppe=[],
        start_frame=100,
        end_frame=None,
        snapshot_path=None,
        severity=severity,
    )


class _CollectingHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self.server.received.append(json.loads(body))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass  # silence server logs in test output


class _ErrorHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.server.call_count += 1
        self.send_response(500)
        self.end_headers()

    def log_message(self, *args):
        pass


def _start_server(handler_class):
    server = HTTPServer(("127.0.0.1", 0), handler_class)
    server.received = []
    server.call_count = 0
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


class TestWebhookAlerter:
    def test_delivers_event_payload(self):
        server = _start_server(_CollectingHandler)
        port = server.server_address[1]
        alerter = WebhookAlerter(f"http://127.0.0.1:{port}/hook")
        alerter.send(make_event())
        alerter.shutdown(wait=True)
        server.shutdown()

        assert len(server.received) == 1
        payload = server.received[0]
        assert payload["event_id"] == "evt001"
        assert payload["severity"] == "CRITICAL"
        assert payload["event_type"] == "zone_intrusion"

    def test_delivers_warning_severity(self):
        server = _start_server(_CollectingHandler)
        port = server.server_address[1]
        alerter = WebhookAlerter(f"http://127.0.0.1:{port}/hook")
        alerter.send(make_event(severity="WARNING"))
        alerter.shutdown(wait=True)
        server.shutdown()

        assert server.received[0]["severity"] == "WARNING"

    def test_retries_on_server_error(self):
        server = _start_server(_ErrorHandler)
        port = server.server_address[1]
        # Use short timeout so retries are fast in tests
        alerter = WebhookAlerter(f"http://127.0.0.1:{port}/hook", timeout=1.0)
        alerter.send(make_event())
        alerter.shutdown(wait=True)
        server.shutdown()

        # Should attempt 3 times (MAX_RETRIES)
        assert server.call_count == 3

    def test_shutdown_drains_queue(self):
        server = _start_server(_CollectingHandler)
        port = server.server_address[1]
        alerter = WebhookAlerter(f"http://127.0.0.1:{port}/hook")
        for i in range(5):
            e = make_event()
            e.event_id = f"evt{i:03d}"
            alerter.send(e)
        alerter.shutdown(wait=True)
        server.shutdown()

        assert len(server.received) == 5
