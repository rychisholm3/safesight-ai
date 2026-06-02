"""
Tests for Phase 6 — Explainability & Evidence.

Covers:
  - explanation builder
  - snapshot annotation (mocked cv2)
  - PDF generation (smoke test)
  - HTTP endpoints via TestClient
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.evidence.explanation import ExplanationItem, build_explanation
from src.evidence.annotation import _make_label, annotate_snapshot


# ── build_explanation ─────────────────────────────────────────────────────────

class TestBuildExplanation:
    def _event(self, **kw) -> dict:
        base = {
            "event_id":    "abc123",
            "event_type":  "missing_ppe",
            "track_id":    7,
            "zone_id":     None,
            "zone_rule":   None,
            "missing_ppe": ["hardhat", "vest"],
            "osha_codes":  ["29 CFR 1926.100(a)"],
            "fine_min_usd": 1000,
            "fine_max_usd": 15000,
            "confidence":  0.87,
            "severity":    "WARNING",
            "start_frame": 100,
            "end_frame":   None,
        }
        return {**base, **kw}

    def test_returns_list_of_items(self):
        items = build_explanation(self._event())
        assert isinstance(items, list)
        assert all(isinstance(i, ExplanationItem) for i in items)

    def test_first_item_describes_violation(self):
        items = build_explanation(self._event())
        assert "hardhat" in items[0].text or "vest" in items[0].text

    def test_zone_intrusion_type(self):
        items = build_explanation(self._event(event_type="zone_intrusion", zone_id="forklift_lane"))
        assert items[0].icon == "⛔"
        assert "forklift_lane" in items[0].text

    def test_global_ppe_context_when_no_zone(self):
        items = build_explanation(self._event(zone_id=None))
        zone_item = next(i for i in items if i.category == "Zone context")
        assert "site-wide" in zone_item.text.lower()

    def test_zone_context_shown_when_zone_set(self):
        items = build_explanation(self._event(zone_id="weld_area", zone_rule="require_ppe"))
        zone_item = next(i for i in items if i.category == "Zone context")
        assert "weld_area" in zone_item.text

    def test_severity_critical(self):
        items = build_explanation(self._event(severity="CRITICAL"))
        sev_item = next(i for i in items if i.category == "Severity assessment")
        assert "CRITICAL" in sev_item.text
        assert sev_item.icon == "🚨"

    def test_severity_warning(self):
        items = build_explanation(self._event(severity="WARNING"))
        sev_item = next(i for i in items if i.category == "Severity assessment")
        assert sev_item.icon == "⚠️"

    def test_financial_exposure_included(self):
        items = build_explanation(self._event(fine_max_usd=15000))
        fine_item = next((i for i in items if i.category == "Financial exposure"), None)
        assert fine_item is not None
        assert "15,000" in fine_item.text

    def test_no_financial_item_when_zero_fines(self):
        items = build_explanation(self._event(fine_min_usd=0, fine_max_usd=0))
        cats = [i.category for i in items]
        assert "Financial exposure" not in cats

    def test_confidence_item_present(self):
        items = build_explanation(self._event(confidence=0.91))
        conf = next(i for i in items if i.category == "Detection confidence")
        assert "91%" in conf.text

    def test_active_event_duration(self):
        items = build_explanation(self._event(end_frame=None))
        dur = next(i for i in items if i.category == "Duration")
        assert "ACTIVE" in dur.text

    def test_closed_event_duration(self):
        items = build_explanation(self._event(start_frame=50, end_frame=200))
        dur = next(i for i in items if i.category == "Duration")
        assert "150 frames" in dur.text
        assert "CLOSED" in dur.text

    def test_no_osha_codes(self):
        items = build_explanation(self._event(osha_codes=[]))
        cats = [i.category for i in items]
        assert "Regulatory exposure" not in cats


# ── _make_label ───────────────────────────────────────────────────────────────

class TestMakeLabel:
    def test_missing_ppe_label(self):
        label = _make_label({"event_type": "missing_ppe", "missing_ppe": ["hardhat"], "severity": "WARNING"})
        assert "hardhat" in label
        assert "WARNING" in label

    def test_zone_intrusion_label(self):
        label = _make_label({"event_type": "zone_intrusion", "zone_id": "forklift_lane", "severity": "CRITICAL", "missing_ppe": []})
        assert "forklift_lane" in label
        assert "CRITICAL" in label

    def test_truncates_long_ppe_list(self):
        label = _make_label({"event_type": "missing_ppe", "missing_ppe": ["hardhat", "vest", "mask"], "severity": "WARNING"})
        assert "..." in label or "…" in label


# ── annotate_snapshot ─────────────────────────────────────────────────────────

class TestAnnotateSnapshot:
    def test_returns_none_when_file_missing(self, tmp_path):
        result = annotate_snapshot(tmp_path / "no_file.jpg", (0, 0, 100, 100), "label")
        assert result is None

    def test_returns_jpeg_bytes(self, tmp_path):
        # Create a small test image
        snap = tmp_path / "snap.jpg"
        import cv2
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.imwrite(str(snap), frame)

        result = annotate_snapshot(snap, (10, 10, 200, 300), "[WARNING] Missing: hardhat")
        assert result is not None
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_no_bbox_returns_original(self, tmp_path):
        snap = tmp_path / "snap.jpg"
        import cv2
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.imwrite(str(snap), frame)

        result = annotate_snapshot(snap, None, "No bbox")
        assert result is not None

    def test_bbox_clamped_to_frame_bounds(self, tmp_path):
        snap = tmp_path / "snap.jpg"
        import cv2
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        cv2.imwrite(str(snap), frame)

        # Bbox extends way beyond frame — should not crash
        result = annotate_snapshot(snap, (-50, -50, 9000, 9000), "big bbox")
        assert result is not None

    def test_per_class_detections_drawn(self, tmp_path):
        """Per-class PPE detection boxes are drawn without crashing."""
        snap = tmp_path / "snap.jpg"
        import cv2
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.imwrite(str(snap), frame)

        person_dets = [
            {"class_name": "hardhat",   "bbox": [120, 30, 200, 80],  "confidence": 0.92},
            {"class_name": "no-vest",   "bbox": [100, 90, 230, 280], "confidence": 0.85},
        ]
        result = annotate_snapshot(
            snap, (80, 20, 260, 400), "[WARNING] Missing: vest",
            person_detections=person_dets,
        )
        assert result is not None
        assert isinstance(result, bytes)

    def test_missing_detections_field_does_not_crash(self, tmp_path):
        snap = tmp_path / "snap.jpg"
        import cv2
        cv2.imwrite(str(snap), np.zeros((480, 640, 3), dtype=np.uint8))
        result = annotate_snapshot(snap, (10, 10, 200, 300), "label", person_detections=None)
        assert result is not None


# ── PDF generation (smoke test) ───────────────────────────────────────────────

class TestPdfGeneration:
    def _event(self):
        return {
            "event_id":    "testevt001",
            "event_type":  "missing_ppe",
            "track_id":    3,
            "zone_id":     "weld_area",
            "zone_rule":   "require_ppe",
            "missing_ppe": ["hardhat"],
            "osha_codes":  ["29 CFR 1926.100(a)"],
            "fine_min_usd": 1116,
            "fine_max_usd": 15625,
            "confidence":  0.81,
            "severity":    "WARNING",
            "start_frame": 10,
            "end_frame":   250,
            "created_at":  "2024-06-01T10:30:00+00:00",
        }

    def test_returns_bytes(self):
        from src.evidence.pdf_export import generate_evidence_pdf
        from src.evidence.explanation import build_explanation
        event = self._event()
        explanation = build_explanation(event)
        pdf = generate_evidence_pdf(event, explanation, [], None)
        assert isinstance(pdf, bytes)
        assert pdf[:4] == b"%PDF"

    def test_with_osha_codes(self):
        from src.evidence.pdf_export import generate_evidence_pdf
        from src.evidence.explanation import build_explanation
        event = self._event()
        explanation = build_explanation(event)
        osha = [{
            "code": "29 CFR 1926.100(a)",
            "title": "Head Protection",
            "description": "Employer must ensure hardhats are worn.",
            "fine_min_usd": 1116,
            "fine_max_usd": 15625,
            "willful_max_usd": 156259,
            "corrective_actions": ["Provide hardhats", "Enforce use"],
            "plain_english": "Hardhats protect workers from falling objects.",
            "reference_url": "https://www.osha.gov",
        }]
        pdf = generate_evidence_pdf(event, explanation, osha, None)
        assert pdf[:4] == b"%PDF"

    def test_with_snapshot_bytes(self, tmp_path):
        from src.evidence.pdf_export import generate_evidence_pdf
        from src.evidence.explanation import build_explanation
        import cv2
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        _, buf = cv2.imencode(".jpg", frame)
        snap_bytes = bytes(buf)

        event = self._event()
        explanation = build_explanation(event)
        pdf = generate_evidence_pdf(event, explanation, [], snap_bytes)
        assert pdf[:4] == b"%PDF"


# ── HTTP endpoints ────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    from src.api.main import app
    return TestClient(app, raise_server_exceptions=True)


def _login(client):
    client.post("/auth/register", json={"org_name": "EvidOrg", "email": "ev@test.com", "password": "secret123"})
    res = client.post("/auth/login", json={"email": "ev@test.com", "password": "secret123"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _insert_event(client, headers) -> str:
    """Insert a fake event via the event store and return its event_id."""
    from src.api.main import _store
    from src.events import Event
    ev = Event(
        event_id    = "evd_test_001",
        event_type  = "missing_ppe",
        track_id    = 99,
        zone_id     = None,
        missing_ppe = ["hardhat"],
        start_frame = 1,
        end_frame   = None,
        snapshot_path = None,
        severity    = "WARNING",
        osha_codes  = ["29 CFR 1926.100(a)"],
        fine_min_usd= 1116,
        fine_max_usd= 15625,
        confidence  = 0.88,
        bbox        = (10, 20, 200, 400),
    )
    _store.save_event(ev)
    return ev.event_id


class TestExplanationEndpoint:
    def test_returns_list(self, client):
        headers = _login(client)
        eid = _insert_event(client, headers)
        res = client.get(f"/evidence/{eid}/explanation", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "category" in data[0]
        assert "text" in data[0]

    def test_404_for_unknown_event(self, client):
        headers = _login(client)
        res = client.get("/evidence/no_such_event/explanation", headers=headers)
        assert res.status_code == 404

    def test_requires_auth(self, client):
        res = client.get("/evidence/abc/explanation")
        assert res.status_code == 401


class TestAnnotatedSnapshotEndpoint:
    def test_404_when_no_snapshot(self, client):
        headers = _login(client)
        eid = _insert_event(client, headers)
        # Event has no snapshot_path, so should 404
        res = client.get(f"/evidence/{eid}/annotated-snapshot", headers=headers)
        assert res.status_code == 404

    def test_requires_auth(self, client):
        res = client.get("/evidence/abc/annotated-snapshot")
        assert res.status_code == 401


class TestPdfEndpoint:
    def test_returns_pdf_bytes(self, client):
        headers = _login(client)
        eid = _insert_event(client, headers)
        res = client.get(f"/evidence/{eid}/report.pdf", headers=headers)
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/pdf"
        assert res.content[:4] == b"%PDF"

    def test_content_disposition_header(self, client):
        headers = _login(client)
        eid = _insert_event(client, headers)
        res = client.get(f"/evidence/{eid}/report.pdf", headers=headers)
        assert "attachment" in res.headers.get("content-disposition", "")
        assert ".pdf" in res.headers.get("content-disposition", "")

    def test_404_for_unknown_event(self, client):
        headers = _login(client)
        res = client.get("/evidence/no_such_event/report.pdf", headers=headers)
        assert res.status_code == 404

    def test_requires_auth(self, client):
        res = client.get("/evidence/abc/report.pdf")
        assert res.status_code == 401
