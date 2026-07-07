import json
from pathlib import Path

import pytest

from src.pipeline.detector import Detection
from src.pipeline.tracker import TrackedObject
from src.pipeline.rules import RulesEngine, SceneConfig, Violation, ZoneConfig

FRAME_ID = 5

# 200x200 square zone at (100,100)-(300,300)
SQUARE_ZONE = ZoneConfig(
    id="test_zone",
    name="Test Zone",
    polygon=[(100, 100), (300, 100), (300, 300), (100, 300)],
    rule="no_entry",
)

BASIC_CONFIG = SceneConfig(required_ppe=["hardhat", "vest"], zones=[SQUARE_ZONE])


def person(track_id=1, x1=0, y1=0, x2=80, y2=100) -> TrackedObject:
    """Person with foot at ((x1+x2)/2, y2)."""
    return TrackedObject(track_id=track_id, bbox=(x1, y1, x2, y2), class_name="person",
                         confidence=0.9, frame_id=FRAME_ID)


def det(x1, y1, x2, y2, class_name="hardhat") -> Detection:
    return Detection(bbox=(x1, y1, x2, y2), class_name=class_name, confidence=0.8,
                     frame_id=FRAME_ID)


# ---------------------------------------------------------------------------
# SceneConfig.from_json
# ---------------------------------------------------------------------------

class TestSceneConfigFromJson:
    def test_parses_required_ppe(self, tmp_path: Path) -> None:
        f = tmp_path / "zones.json"
        f.write_text(json.dumps({"required_ppe": ["hardhat", "vest"], "zones": []}))
        cfg = SceneConfig.from_json(f)
        assert cfg.required_ppe == ["hardhat", "vest"]

    def test_parses_zone_fields(self, tmp_path: Path) -> None:
        f = tmp_path / "zones.json"
        f.write_text(json.dumps({
            "required_ppe": [],
            "zones": [{"id": "z1", "name": "Zone 1",
                        "polygon": [[0, 0], [100, 0], [100, 100], [0, 100]],
                        "rule": "no_entry"}]
        }))
        cfg = SceneConfig.from_json(f)
        assert cfg.zones[0].id == "z1"
        assert cfg.zones[0].polygon == [(0, 0), (100, 0), (100, 100), (0, 100)]

    def test_zone_required_ppe_defaults_to_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "zones.json"
        f.write_text(json.dumps({
            "required_ppe": [],
            "zones": [{"id": "z1", "name": "Z", "polygon": [[0,0],[1,0],[1,1]], "rule": "no_entry"}]
        }))
        assert SceneConfig.from_json(f).zones[0].required_ppe == []

    def test_loads_project_zones_file(self) -> None:
        # zones.json ships with an empty zones list (operators add zones via the
        # Zone Editor UI; the file is not pre-populated with hardcoded zones).
        path = Path(__file__).parent.parent / "config" / "zones.json"
        cfg = SceneConfig.from_json(path)
        assert isinstance(cfg.zones, list)
        assert cfg.required_ppe == ["hardhat", "vest"]


# ---------------------------------------------------------------------------
# PPE checks
# ---------------------------------------------------------------------------

class TestPpeChecks:
    def test_no_violation_when_all_ppe_present(self) -> None:
        engine = RulesEngine(BASIC_CONFIG)
        p = person(x1=0, y1=0, x2=80, y2=100)
        dets = [det(10, 10, 50, 40, "hardhat"), det(10, 50, 50, 90, "vest")]
        assert engine.check([p], dets, FRAME_ID) == []

    def test_missing_hardhat_raises_violation(self) -> None:
        engine = RulesEngine(BASIC_CONFIG)
        p = person()
        violations = engine.check([p], [det(10, 50, 50, 90, "vest")], FRAME_ID)
        ppe_v = [v for v in violations if v.type == "missing_ppe"]
        assert len(ppe_v) == 1
        assert "hardhat" in ppe_v[0].missing_ppe

    def test_missing_vest_raises_violation(self) -> None:
        engine = RulesEngine(BASIC_CONFIG)
        p = person()
        violations = engine.check([p], [det(10, 10, 50, 40, "hardhat")], FRAME_ID)
        assert "vest" in violations[0].missing_ppe

    def test_ppe_outside_person_bbox_not_counted(self) -> None:
        engine = RulesEngine(BASIC_CONFIG)
        p = person(x1=0, y1=0, x2=80, y2=100)
        # Hardhat centre at (225, 225) — outside person bbox
        dets = [det(200, 200, 250, 250, "hardhat"), det(10, 50, 50, 90, "vest")]
        violations = engine.check([p], dets, FRAME_ID)
        ppe_v = [v for v in violations if v.type == "missing_ppe"]
        assert "hardhat" in ppe_v[0].missing_ppe

    def test_violation_stamped_with_track_id_and_frame(self) -> None:
        engine = RulesEngine(BASIC_CONFIG)
        p = person(track_id=7)
        violations = engine.check([p], [], FRAME_ID)
        v = next(v for v in violations if v.type == "missing_ppe")
        assert v.track_id == 7
        assert v.frame_id == FRAME_ID
        assert v.bbox == p.bbox

    def test_no_ppe_required_no_violation(self) -> None:
        engine = RulesEngine(SceneConfig(required_ppe=[], zones=[]))
        assert engine.check([person()], [], FRAME_ID) == []


# ---------------------------------------------------------------------------
# Zone intrusion
# ---------------------------------------------------------------------------

class TestZoneIntrusion:
    def test_no_violation_when_foot_outside_zone(self) -> None:
        engine = RulesEngine(BASIC_CONFIG)
        # foot at (40, 100) — outside (100,100)-(300,300) zone
        p = person(x1=0, y1=0, x2=80, y2=100)
        dets = [det(10, 10, 50, 40, "hardhat"), det(10, 50, 50, 90, "vest")]
        zone_v = [v for v in engine.check([p], dets, FRAME_ID) if v.type == "zone_intrusion"]
        assert zone_v == []

    def test_violation_when_foot_inside_no_entry_zone(self) -> None:
        engine = RulesEngine(BASIC_CONFIG)
        # foot at (200, 300) — on edge of zone, counts as inside
        p = person(x1=150, y1=100, x2=250, y2=300)
        dets = [det(160, 110, 200, 150, "hardhat"), det(160, 160, 200, 200, "vest")]
        zone_v = [v for v in engine.check([p], dets, FRAME_ID) if v.type == "zone_intrusion"]
        assert len(zone_v) == 1
        assert zone_v[0].zone_id == "test_zone"

    def test_require_ppe_zone_fires_when_ppe_missing(self) -> None:
        zone = ZoneConfig(id="weld", name="Weld bay",
                          polygon=[(100, 100), (300, 100), (300, 300), (100, 300)],
                          rule="require_ppe", required_ppe=["hardhat", "face_shield"])
        engine = RulesEngine(SceneConfig(required_ppe=[], zones=[zone]))
        p = person(x1=150, y1=100, x2=250, y2=300)
        dets = [det(160, 110, 200, 150, "hardhat")]  # has hardhat, missing face_shield
        violations = engine.check([p], dets, FRAME_ID)
        assert len(violations) == 1
        assert violations[0].zone_id == "weld"
        assert "face_shield" in violations[0].missing_ppe

    def test_require_ppe_zone_no_violation_when_compliant(self) -> None:
        zone = ZoneConfig(id="weld", name="Weld bay",
                          polygon=[(100, 100), (300, 100), (300, 300), (100, 300)],
                          rule="require_ppe", required_ppe=["hardhat"])
        engine = RulesEngine(SceneConfig(required_ppe=[], zones=[zone]))
        p = person(x1=150, y1=100, x2=250, y2=300)
        dets = [det(160, 110, 200, 150, "hardhat")]
        assert engine.check([p], dets, FRAME_ID) == []


# ---------------------------------------------------------------------------
# Multi-person
# ---------------------------------------------------------------------------

class TestMultiPerson:
    def test_violations_independent_per_person(self) -> None:
        engine = RulesEngine(BASIC_CONFIG)
        # Person 1 has all PPE, outside zone
        p1 = person(track_id=1, x1=0, y1=0, x2=80, y2=100)
        # Person 2 has no PPE
        p2 = person(track_id=2, x1=400, y1=0, x2=480, y2=100)
        dets = [det(10, 10, 50, 40, "hardhat"), det(10, 50, 50, 90, "vest")]
        violations = engine.check([p1, p2], dets, FRAME_ID)
        ids_with_ppe_violation = {v.track_id for v in violations if v.type == "missing_ppe"}
        assert 1 not in ids_with_ppe_violation
        assert 2 in ids_with_ppe_violation

    def test_no_tracked_objects_returns_empty(self) -> None:
        engine = RulesEngine(BASIC_CONFIG)
        assert engine.check([], [], FRAME_ID) == []


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------

class TestSeverity:
    def test_missing_ppe_is_warning(self) -> None:
        engine = RulesEngine(BASIC_CONFIG)
        violations = engine.check([person()], [], FRAME_ID)
        ppe_v = [v for v in violations if v.type == "missing_ppe"]
        assert all(v.severity == "WARNING" for v in ppe_v)

    def test_zone_intrusion_is_critical(self) -> None:
        engine = RulesEngine(BASIC_CONFIG)
        p = person(x1=150, y1=100, x2=250, y2=300)
        dets = [det(160, 110, 200, 150, "hardhat"), det(160, 160, 200, 200, "vest")]
        violations = engine.check([p], dets, FRAME_ID)
        zone_v = [v for v in violations if v.type == "zone_intrusion"]
        assert all(v.severity == "CRITICAL" for v in zone_v)

    def test_require_ppe_zone_violation_is_warning(self) -> None:
        zone = ZoneConfig(id="weld", name="Weld bay",
                          polygon=[(100, 100), (300, 100), (300, 300), (100, 300)],
                          rule="require_ppe", required_ppe=["hardhat", "face_shield"])
        engine = RulesEngine(SceneConfig(required_ppe=[], zones=[zone]))
        p = person(x1=150, y1=100, x2=250, y2=300)
        violations = engine.check([p], [det(160, 110, 200, 150, "hardhat")], FRAME_ID)
        assert violations[0].severity == "WARNING"
