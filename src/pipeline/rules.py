import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from src.pipeline.detector import Detection
from src.pipeline.tracker import TrackedObject

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
    zone_rule: str | None = None       # "no_entry" | "require_ppe" | None
    missing_ppe: list[str] = field(default_factory=list)
    confidence: float = 0.0            # detection confidence of the tracked person
    person_detections: list[Detection] = field(default_factory=list)  # PPE detections inside this person's bbox


# ── "No-PPE" indicator classes emitted by the fine-tuned model ───────────────
# Maps the explicit absence class name → canonical PPE name it negates.
_NO_PPE_INDICATORS: dict[str, str] = {
    "no-hardhat": "hardhat",
    "no-vest":    "vest",
    "no-mask":    "mask",
}


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

    def _ppe_present(
        self, person: TrackedObject, detections: list[Detection]
    ) -> tuple[set[str], set[str], list[Detection]]:
        """Return (present, explicitly_absent, overlapping_detections) for this person.

        *present*  — PPE items whose bbox centre overlaps the person bbox.
        *explicitly_absent* — PPE items flagged by a "no-*" indicator class
                              overlapping the same person (e.g. NO-Hardhat).
        *overlapping_detections* — the raw Detection objects inside this person's
                              bbox, used for per-class snapshot annotation.
        Both sets use canonical lowercase names ("hardhat", "vest", …).
        """
        px1, py1, px2, py2 = person.bbox
        present:  set[str] = set()
        absent:   set[str] = set()
        person_dets: list[Detection] = []

        for det in detections:
            if det.class_name == "person":
                continue
            cx = (det.bbox[0] + det.bbox[2]) / 2
            cy = (det.bbox[1] + det.bbox[3]) / 2
            if not (px1 <= cx <= px2 and py1 <= cy <= py2):
                continue

            person_dets.append(det)
            if det.class_name in _NO_PPE_INDICATORS:
                # Explicit absence detector fired → the corresponding PPE is missing
                absent.add(_NO_PPE_INDICATORS[det.class_name])
            else:
                present.add(det.class_name)

        return present, absent, person_dets

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
            ppe_present, ppe_absent, person_dets = self._ppe_present(person, detections)

            # A PPE item is "missing" if:
            #   • the model fired an explicit no-* indicator for it, OR
            #   • it simply wasn't detected inside the person's bbox.
            # We use absent-set OR (required minus present) so either signal fires.
            def _missing_ppe(required: list[str]) -> list[str]:
                return [
                    p for p in required
                    if p in ppe_absent or p not in ppe_present
                ]

            # Global PPE check
            missing = _missing_ppe(self._config.required_ppe)
            if missing:
                violations.append(Violation(
                    type="missing_ppe",
                    track_id=person.track_id,
                    frame_id=frame_id,
                    bbox=person.bbox,
                    severity="WARNING",
                    missing_ppe=missing,
                    confidence=person.confidence,
                    person_detections=person_dets,
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
                        zone_rule="no_entry",
                        confidence=person.confidence,
                        person_detections=person_dets,
                    ))
                elif zone.rule == "require_ppe":
                    zone_missing = _missing_ppe(zone.required_ppe)
                    if zone_missing:
                        violations.append(Violation(
                            type="missing_ppe",
                            track_id=person.track_id,
                            frame_id=frame_id,
                            bbox=person.bbox,
                            severity="WARNING",
                            zone_id=zone.id,
                            zone_rule="require_ppe",
                            missing_ppe=zone_missing,
                            confidence=person.confidence,
                            person_detections=person_dets,
                        ))

        if violations:
            logger.debug("frame=%d violations=%d", frame_id, len(violations))

        return violations
