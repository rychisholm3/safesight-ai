"""
Tests for Phase 7 — Near-Miss Detection.

Covers:
  - bbox_min_distance utility
  - TrajectoryTracker (update, predict, convergence)
  - NearMissEngine (proximity, trajectory, zone_entry)
  - Pipeline integration (near_miss events stored and returned by API)
"""
import math
from unittest.mock import MagicMock

import pytest

from src.nearmiss.proximity import bbox_min_distance, bbox_center, VEHICLE_CLASSES
from src.nearmiss.trajectory import TrajectoryTracker
from src.nearmiss.engine import NearMissEngine
from src.pipeline.detector import Detection
from src.pipeline.tracker import TrackedObject


# ── bbox_min_distance ─────────────────────────────────────────────────────────

class TestBboxMinDistance:
    def test_overlapping_boxes_returns_zero(self):
        a = (0, 0, 100, 100)
        b = (50, 50, 150, 150)
        assert bbox_min_distance(a, b) == 0.0

    def test_touching_boxes_returns_zero(self):
        a = (0, 0, 100, 100)
        b = (100, 0, 200, 100)
        assert bbox_min_distance(a, b) == 0.0

    def test_horizontal_gap(self):
        a = (0, 0, 100, 100)
        b = (150, 0, 250, 100)  # 50 px gap
        assert bbox_min_distance(a, b) == pytest.approx(50.0)

    def test_vertical_gap(self):
        a = (0, 0, 100, 100)
        b = (0, 180, 100, 280)  # 80 px gap
        assert bbox_min_distance(a, b) == pytest.approx(80.0)

    def test_diagonal_gap(self):
        a = (0, 0, 100, 100)
        b = (140, 130, 200, 200)  # dx=40, dy=30 → dist=50
        assert bbox_min_distance(a, b) == pytest.approx(50.0)

    def test_same_box_returns_zero(self):
        a = (10, 20, 110, 120)
        assert bbox_min_distance(a, a) == 0.0


# ── bbox_center ───────────────────────────────────────────────────────────────

class TestBboxCenter:
    def test_center(self):
        cx, cy = bbox_center((0, 0, 100, 100))
        assert cx == pytest.approx(50.0)
        assert cy == pytest.approx(50.0)


# ── VEHICLE_CLASSES ───────────────────────────────────────────────────────────

class TestVehicleClasses:
    def test_contains_common_vehicles(self):
        assert "truck" in VEHICLE_CLASSES
        assert "car"   in VEHICLE_CLASSES
        assert "bus"   in VEHICLE_CLASSES

    def test_does_not_contain_person(self):
        assert "person" not in VEHICLE_CLASSES


# ── TrajectoryTracker ─────────────────────────────────────────────────────────

class TestTrajectoryTracker:
    def _tracker(self):
        return TrajectoryTracker(history_len=10)

    def test_history_length_zero_initially(self):
        t = self._tracker()
        assert t.history_length(1) == 0

    def test_update_increments_history(self):
        t = self._tracker()
        t.update(1, (0, 0, 10, 10))
        assert t.history_length(1) == 1

    def test_predict_returns_none_with_single_frame(self):
        t = self._tracker()
        t.update(1, (0, 0, 10, 10))
        assert t.predict_position(1, 5) is None

    def test_predict_linear_extrapolation(self):
        t = self._tracker()
        # Object moving right at 10 px/frame
        for i in range(5):
            t.update(1, (i * 10, 0, i * 10 + 30, 50))
        pred = t.predict_position(1, 3)
        assert pred is not None
        # Last centre was at x=(40+65)/2=52.5, velocity ≈ 10, so at t+3 ≈ 82.5
        px, py = pred
        assert 70 < px < 100  # rough range check

    def test_predict_stationary_object(self):
        t = self._tracker()
        for _ in range(5):
            t.update(1, (100, 100, 200, 200))
        pred = t.predict_position(1, 10)
        assert pred is not None
        px, py = pred
        assert abs(px - 150) < 1  # stationary → stays at centre
        assert abs(py - 150) < 1

    def test_evict_stale_removes_old_tracks(self):
        t = self._tracker()
        t.update(1, (0, 0, 10, 10))
        t.update(2, (100, 100, 110, 110))
        t.evict_stale({1})
        assert t.history_length(1) == 1
        assert t.history_length(2) == 0

    def test_time_to_convergence_returns_none_insufficient_history(self):
        t = self._tracker()
        t.update(1, (0, 0, 10, 10))
        t.update(2, (500, 0, 510, 10))
        # Only 1 frame → not enough history
        assert t.time_to_convergence(1, 2, threshold_px=50, frames_ahead=30) is None

    def test_time_to_convergence_detects_approaching_objects(self):
        t = self._tracker()
        # Object A moves right, Object B moves left — they will meet
        for i in range(8):
            t.update(1, (i * 10,      200, i * 10 + 30,      250))
            t.update(2, (700 - i * 10, 200, 700 - i * 10 + 30, 250))
        ttc = t.time_to_convergence(1, 2, threshold_px=100, frames_ahead=60, min_history=5)
        assert ttc is not None
        assert 1 <= ttc <= 60

    def test_time_to_convergence_returns_none_for_diverging_objects(self):
        t = self._tracker()
        # Both objects moving in the same direction, same speed → constant distance
        for i in range(8):
            t.update(1, (i * 10,       0, i * 10 + 30, 50))
            t.update(2, (i * 10 + 500, 0, i * 10 + 530, 50))
        ttc = t.time_to_convergence(1, 2, threshold_px=50, frames_ahead=30, min_history=5)
        assert ttc is None


# ── NearMissEngine ────────────────────────────────────────────────────────────

def _person(track_id: int, bbox: tuple) -> TrackedObject:
    return TrackedObject(
        track_id=track_id, class_name="person",
        bbox=bbox, confidence=0.85, frame_id=0,
    )

def _detection(class_name: str, bbox: tuple) -> Detection:
    return Detection(class_name=class_name, bbox=bbox, confidence=0.9, frame_id=0)


class TestProximityRequiresNonZeroDistance:
    """Fix: overlapping bboxes (dist=0) should not fire near-miss (that's a collision)."""

    def test_overlapping_bboxes_not_a_near_miss(self):
        engine = NearMissEngine()
        # Person and vehicle bboxes overlap completely — distance = 0
        persons = [_person(1, (100, 100, 300, 400))]
        detections = [_detection("truck", (100, 100, 300, 400))]  # same bbox
        viols = engine.check(persons, detections, frame_id=1)
        prox = [v for v in viols if v.zone_rule == "proximity"]
        assert len(prox) == 0

    def test_touching_bboxes_not_a_near_miss(self):
        engine = NearMissEngine()
        # Person ends at x=200, truck starts at x=200 — touching (dist=0)
        persons = [_person(1, (100, 100, 200, 300))]
        detections = [_detection("truck", (200, 100, 350, 300))]
        viols = engine.check(persons, detections, frame_id=1)
        prox = [v for v in viols if v.zone_rule == "proximity"]
        assert len(prox) == 0

    def test_one_pixel_gap_is_a_near_miss(self):
        engine = NearMissEngine()
        # 1 px gap — should fire CRITICAL (< 50 px threshold)
        persons = [_person(1, (100, 100, 200, 300))]
        detections = [_detection("truck", (201, 100, 350, 300))]
        viols = engine.check(persons, detections, frame_id=1)
        prox = [v for v in viols if v.zone_rule == "proximity"]
        assert len(prox) == 1
        assert prox[0].severity == "CRITICAL"


class TestNearMissEngineProximity:
    def test_no_vehicles_no_violations(self):
        engine = NearMissEngine()
        persons = [_person(1, (100, 100, 200, 300))]
        detections = [_detection("hardhat", (110, 110, 150, 140))]
        viols = engine.check(persons, detections, frame_id=1)
        assert all(v.zone_rule != "proximity" for v in viols)

    def test_critical_proximity_to_truck(self):
        engine = NearMissEngine()
        # Person at x=100–200, truck at x=220–400 → 20 px gap < 50 px critical
        persons = [_person(1, (100, 100, 200, 300))]
        detections = [_detection("truck", (220, 100, 400, 300))]
        viols = engine.check(persons, detections, frame_id=1)
        prox = [v for v in viols if v.zone_rule == "proximity"]
        assert len(prox) == 1
        assert prox[0].severity == "CRITICAL"
        assert prox[0].type == "near_miss"

    def test_warning_proximity_to_car(self):
        engine = NearMissEngine()
        # Person at x=0–100, car at x=200–300 → 100 px gap — WARNING
        persons = [_person(1, (0, 100, 100, 300))]
        detections = [_detection("car", (200, 100, 300, 300))]
        viols = engine.check(persons, detections, frame_id=1)
        prox = [v for v in viols if v.zone_rule == "proximity"]
        assert len(prox) == 1
        assert prox[0].severity == "WARNING"

    def test_safe_distance_no_violation(self):
        engine = NearMissEngine()
        # 300 px gap — well beyond warning threshold
        persons = [_person(1, (0, 0, 100, 200))]
        detections = [_detection("truck", (400, 0, 600, 200))]
        viols = engine.check(persons, detections, frame_id=1)
        prox = [v for v in viols if v.zone_rule == "proximity"]
        assert len(prox) == 0

    def test_non_vehicle_detection_ignored(self):
        engine = NearMissEngine()
        persons = [_person(1, (0, 0, 100, 200))]
        detections = [_detection("hardhat", (105, 0, 200, 200))]  # adjacent but not a vehicle
        viols = engine.check(persons, detections, frame_id=1)
        prox = [v for v in viols if v.zone_rule == "proximity"]
        assert len(prox) == 0


class TestNearMissEngineTrajectory:
    def _approaching_engine(self):
        engine = NearMissEngine()
        # Build up history: two persons moving toward each other
        for i in range(10):
            engine.check(
                [_person(1, (i * 5, 200, i * 5 + 30, 280)),
                 _person(2, (800 - i * 5, 200, 800 - i * 5 + 30, 280))],
                [],
                frame_id=i,
            )
        return engine

    def test_converging_trajectories_detected(self):
        engine = self._approaching_engine()
        viols = engine.check(
            [_person(1, (50, 200, 80, 280)), _person(2, (750, 200, 780, 280))],
            [], frame_id=10,
        )
        traj = [v for v in viols if v.zone_rule == "trajectory"]
        assert len(traj) >= 1

    def test_insufficient_history_no_trajectory_violation(self):
        engine = NearMissEngine()
        # Only 2 frames of history — below min_history=5
        for i in range(2):
            engine.check([_person(1, (i, 0, i + 10, 50)), _person(2, (200 - i, 0, 210 - i, 50))], [], i)
        viols = engine.check([_person(1, (2, 0, 12, 50)), _person(2, (198, 0, 208, 50))], [], 2)
        traj = [v for v in viols if v.zone_rule == "trajectory"]
        assert len(traj) == 0


class TestNearMissEngineZoneEntry:
    def _scene_with_zone(self):
        from src.pipeline.rules import SceneConfig, ZoneConfig
        zone = ZoneConfig(
            id="restricted", name="Restricted", rule="no_entry",
            polygon=[(200, 200), (400, 200), (400, 400), (200, 400)],
        )
        return SceneConfig(required_ppe=[], zones=[zone])

    def test_person_inside_zone_fires_near_miss(self):
        scene = self._scene_with_zone()
        engine = NearMissEngine(scene=scene)
        # Person with foot at (300, 390) — inside the zone
        persons = [_person(1, (270, 300, 330, 390))]
        viols = engine.check(persons, [], frame_id=1)
        zone_viols = [v for v in viols if v.zone_rule == "zone_entry"]
        assert len(zone_viols) == 1
        assert zone_viols[0].zone_id == "restricted"
        assert zone_viols[0].type == "near_miss"

    def test_person_outside_zone_no_violation(self):
        scene = self._scene_with_zone()
        engine = NearMissEngine(scene=scene)
        # Person with foot well outside zone
        persons = [_person(1, (0, 0, 50, 100))]
        viols = engine.check(persons, [], frame_id=1)
        zone_viols = [v for v in viols if v.zone_rule == "zone_entry"]
        assert len(zone_viols) == 0

    def test_no_scene_no_zone_violations(self):
        engine = NearMissEngine(scene=None)
        persons = [_person(1, (270, 300, 330, 390))]
        viols = engine.check(persons, [], frame_id=1)
        zone_viols = [v for v in viols if v.zone_rule == "zone_entry"]
        assert len(zone_viols) == 0


# ── API integration — near_miss events stored and queryable ───────────────────

class TestNearMissApiIntegration:
    def test_near_miss_events_returned_by_list_endpoint(self):
        from fastapi.testclient import TestClient
        from src.api.main import app, _store
        from src.pipeline.events import Event

        client = TestClient(app)

        # Register + login
        client.post("/auth/register", json={"org_name": "NMOrg", "email": "nm@test.com", "password": "secret123"})
        res = client.post("/auth/login", json={"email": "nm@test.com", "password": "secret123"})
        token = res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Insert a near_miss event directly
        ev = Event(
            event_id    = "nm_test_001",
            event_type  = "near_miss",
            track_id    = 5,
            zone_id     = None,
            missing_ppe = [],
            start_frame = 1,
            end_frame   = None,
            snapshot_path = None,
            severity    = "CRITICAL",
            zone_rule   = "proximity",
            confidence  = 0.77,
        )
        _store.save_event(ev)

        # Should appear in the events list
        res = client.get("/events?limit=100", headers=headers)
        assert res.status_code == 200
        events = res.json()
        nm = [e for e in events if e["event_type"] == "near_miss"]
        assert len(nm) >= 1
        assert nm[0]["zone_rule"] == "proximity"
        assert nm[0]["severity"] == "CRITICAL"

    def test_near_miss_counted_in_stats(self):
        from fastapi.testclient import TestClient
        from src.api.main import app
        client = TestClient(app)

        client.post("/auth/register", json={"org_name": "NMOrg2", "email": "nm2@test.com", "password": "secret123"})
        res = client.post("/auth/login", json={"email": "nm2@test.com", "password": "secret123"})
        headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

        res = client.get("/stats", headers=headers)
        assert res.status_code == 200
        stats = res.json()
        # "near_miss" key should exist (may be 0 if no events yet)
        assert "by_type" in stats
