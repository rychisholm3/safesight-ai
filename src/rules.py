import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from src.detector import Detection
from src.tracker import TrackedObject

logger = logging.getLogger(__name__)


@dataclass
class ZoneConfig:
    id: str
    name: str
    polygon: list[tuple[int, int]]
    rule: str                          # "no_entry" | "require_ppe"
    required_ppe: list[str] = field(default_factory=list)


@dataclass
class SceneConfig:
    required_ppe: list[str]
    zones: list[ZoneConfig]

    @classmethod
    def from_json(cls, path: Path) -> "SceneConfig":
        data = json.loads(Path(path).read_text())
        zones = [
            ZoneConfig(
                id=z["id"],
                name=z["name"],
                polygon=[tuple(p) for p in z["polygon"]],
                rule=z["rule"],
                required_ppe=z.get("required_ppe", []),
            )
            for z in data.get("zones", [])
        ]
        return cls(required_ppe=data.get("required_ppe", []), zones=zones)


@dataclass
class Violation:
    type: str                          # "missing_ppe" | "zone_intrusion"
    track_id: int
    frame_id: int
    bbox: tuple[int, int, int, int]
    severity: str = "WARNING"          # "WARNING" | "CRITICAL"
    zone_id: str | None = None
    missing_ppe: list[str] = field(default_factory=list)


class RulesEngine:
    def __init__(self, config: SceneConfig, ppe_overlap_threshold: float = 0.3) -> None:
        self._config = config
        self._zone_polys: dict[str, np.ndarray] = {
            z.id: np.array(z.polygon, dtype=np.int32) for z in config.zones
        }
        logger.info(
            "RulesEngine initialised: %d zone(s), global_ppe=%s",
            len(config.zones),
            config.required_ppe,
        )

    def _ppe_present(self, person: TrackedObject, detections: list[Detection]) -> set[str]:
        """Return PPE class names whose centre point falls inside the person's bbox."""
        px1, py1, px2, py2 = person.bbox
        found: set[str] = set()
        for det in detections:
            if det.class_name == "person":
                continue
            cx = (det.bbox[0] + det.bbox[2]) / 2
            cy = (det.bbox[1] + det.bbox[3]) / 2
            if px1 <= cx <= px2 and py1 <= cy <= py2:
                found.add(det.class_name)
        return found

    def _foot_in_zone(self, bbox: tuple[int, int, int, int], zone_id: str) -> bool:
        x1, _, x2, y2 = bbox
        foot = ((x1 + x2) / 2, float(y2))
        return cv2.pointPolygonTest(self._zone_polys[zone_id], foot, measureDist=False) >= 0

    def check(
        self,
        tracked: list[TrackedObject],
        detections: list[Detection],
        frame_id: int,
    ) -> list[Violation]:
        """Return one Violation per person per rule broken this frame. No debouncing."""
        violations: list[Violation] = []

        for person in tracked:
            ppe = self._ppe_present(person, detections)

            # Global PPE check
            missing = [p for p in self._config.required_ppe if p not in ppe]
            if missing:
                violations.append(Violation(
                    type="missing_ppe",
                    track_id=person.track_id,
                    frame_id=frame_id,
                    bbox=person.bbox,
                    severity="WARNING",
                    missing_ppe=missing,
                ))

            # Zone checks
            for zone in self._config.zones:
                if not self._foot_in_zone(person.bbox, zone.id):
                    continue
                if zone.rule == "no_entry":
                    violations.append(Violation(
                        type="zone_intrusion",
                        track_id=person.track_id,
                        frame_id=frame_id,
                        bbox=person.bbox,
                        severity="CRITICAL",
                        zone_id=zone.id,
                    ))
                elif zone.rule == "require_ppe":
                    zone_missing = [p for p in zone.required_ppe if p not in ppe]
                    if zone_missing:
                        violations.append(Violation(
                            type="missing_ppe",
                            track_id=person.track_id,
                            frame_id=frame_id,
                            bbox=person.bbox,
                            severity="WARNING",
                            zone_id=zone.id,
                            missing_ppe=zone_missing,
                        ))

        if violations:
            logger.debug("frame=%d violations=%d", frame_id, len(violations))

        return violations
