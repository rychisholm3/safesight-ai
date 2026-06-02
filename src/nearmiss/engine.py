"""
NearMissEngine — detects near-miss hazards that fall outside the standard
PPE / zone-intrusion rules.

Near-miss categories
--------------------
proximity     — person is within a dangerous distance of a detected vehicle
               (CRITICAL < 50 px edge-to-edge; WARNING < 150 px)
trajectory    — two persons' extrapolated paths converge within N frames
               (CRITICAL ≤ 60 px predicted; WARNING ≤ 120 px)
zone_entry    — person's foot crosses a no_entry zone boundary (any entry,
               even a single frame, is logged before the full debouncer
               threshold fires for zone_intrusion)

All near-miss detections produce Violation objects with event_type="near_miss".
They flow through the normal EventDebouncer (with a shorter min_frames so
brief contacts are captured).
"""
import logging
from dataclasses import dataclass, field

import numpy as np

from src.detector import Detection
from src.nearmiss.proximity import (
    VEHICLE_CLASSES,
    ProximityConfig,
    bbox_min_distance,
)
from src.nearmiss.trajectory import TrajectoryTracker
from src.rules import SceneConfig, Violation
from src.tracker import TrackedObject

logger = logging.getLogger(__name__)


class NearMissEngine:
    """
    Stateful near-miss detector.  One instance per pipeline run.

    Maintain a TrajectoryTracker to accumulate per-person position history
    across frames, then on each frame check three hazard categories.
    """

    def __init__(
        self,
        scene: SceneConfig | None = None,
        config: ProximityConfig | None = None,
    ) -> None:
        self._scene  = scene
        self._cfg    = config or ProximityConfig()
        self._traj   = TrajectoryTracker()

        # Pre-build zone polygons for fast point-in-polygon tests
        self._zone_polys: dict[str, np.ndarray] = {}
        if scene:
            import cv2  # noqa: F401 — only needed if scene provided
            self._zone_polys = {
                z.id: np.array(z.polygon, dtype=np.int32)
                for z in scene.zones
                if z.rule == "no_entry"
            }

        logger.info(
            "NearMissEngine ready: %d no-entry zones, thresholds vehicle=%d/%d px "
            "trajectory=%d/%d px look-ahead=%d frames",
            len(self._zone_polys),
            self._cfg.vehicle_critical_px, self._cfg.vehicle_warning_px,
            self._cfg.trajectory_critical_px, self._cfg.trajectory_warning_px,
            self._cfg.trajectory_frames_ahead,
        )

    # ── Public interface ──────────────────────────────────────────────────────

    def check(
        self,
        tracked: list[TrackedObject],
        detections: list[Detection],
        frame_id: int,
    ) -> list[Violation]:
        """
        Return near-miss Violations for this frame.
        Call once per frame after the normal rules engine check.
        """
        violations: list[Violation] = []
        persons = [t for t in tracked if t.class_name == "person"]

        # Update trajectory history for all persons this frame
        for p in persons:
            self._traj.update(p.track_id, p.bbox)
        self._traj.evict_stale({p.track_id for p in persons})

        # 1. Person ↔ vehicle proximity
        violations.extend(self._check_vehicle_proximity(persons, detections, frame_id))

        # 2. Person ↔ person trajectory convergence
        violations.extend(self._check_trajectory(persons, frame_id))

        # 3. Zone entry (brief — even a single frame)
        if self._zone_polys:
            violations.extend(self._check_zone_entry(persons, frame_id))

        if violations:
            logger.debug("frame=%d near_miss_violations=%d", frame_id, len(violations))

        return violations

    # ── Internal checks ───────────────────────────────────────────────────────

    def _check_vehicle_proximity(
        self,
        persons: list[TrackedObject],
        detections: list[Detection],
        frame_id: int,
    ) -> list[Violation]:
        vehicles = [d for d in detections if d.class_name in VEHICLE_CLASSES]
        if not vehicles:
            return []

        viols: list[Violation] = []
        for person in persons:
            closest_dist = float("inf")
            closest_vehicle: Detection | None = None

            for veh in vehicles:
                dist = bbox_min_distance(person.bbox, veh.bbox)
                if dist < closest_dist:
                    closest_dist = dist
                    closest_vehicle = veh

            if closest_dist < self._cfg.vehicle_critical_px:
                sev = "CRITICAL"
            elif closest_dist < self._cfg.vehicle_warning_px:
                sev = "WARNING"
            else:
                continue

            viols.append(Violation(
                type      = "near_miss",
                track_id  = person.track_id,
                frame_id  = frame_id,
                bbox      = person.bbox,
                severity  = sev,
                zone_rule = "proximity",
                confidence= person.confidence,
                missing_ppe = [],
            ))
            logger.debug(
                "Near-miss PROXIMITY frame=%d track=#%d vehicle=%s dist=%.1f sev=%s",
                frame_id, person.track_id,
                closest_vehicle.class_name if closest_vehicle else "?",
                closest_dist, sev,
            )

        return viols

    def _check_trajectory(
        self,
        persons: list[TrackedObject],
        frame_id: int,
    ) -> list[Violation]:
        if len(persons) < 2:
            return []

        viols: list[Violation] = []
        seen: set[frozenset[int]] = set()

        for i, pa in enumerate(persons):
            for pb in persons[i + 1:]:
                pair = frozenset({pa.track_id, pb.track_id})
                if pair in seen:
                    continue
                seen.add(pair)

                # Check CRITICAL threshold
                ttc_crit = self._traj.time_to_convergence(
                    pa.track_id, pb.track_id,
                    threshold_px  = self._cfg.trajectory_critical_px,
                    frames_ahead  = self._cfg.trajectory_frames_ahead,
                    min_history   = self._cfg.trajectory_min_history,
                )
                if ttc_crit is not None:
                    # Both persons involved; log violation for the one with lower track_id
                    for person in (pa, pb):
                        viols.append(Violation(
                            type      = "near_miss",
                            track_id  = person.track_id,
                            frame_id  = frame_id,
                            bbox      = person.bbox,
                            severity  = "CRITICAL",
                            zone_rule = "trajectory",
                            confidence= person.confidence,
                            missing_ppe = [],
                        ))
                    logger.debug(
                        "Near-miss TRAJECTORY CRITICAL frame=%d tracks=#%d,#%d ttc=%d frames",
                        frame_id, pa.track_id, pb.track_id, ttc_crit,
                    )
                    continue

                # Check WARNING threshold
                ttc_warn = self._traj.time_to_convergence(
                    pa.track_id, pb.track_id,
                    threshold_px  = self._cfg.trajectory_warning_px,
                    frames_ahead  = self._cfg.trajectory_frames_ahead,
                    min_history   = self._cfg.trajectory_min_history,
                )
                if ttc_warn is not None:
                    for person in (pa, pb):
                        viols.append(Violation(
                            type      = "near_miss",
                            track_id  = person.track_id,
                            frame_id  = frame_id,
                            bbox      = person.bbox,
                            severity  = "WARNING",
                            zone_rule = "trajectory",
                            confidence= person.confidence,
                            missing_ppe = [],
                        ))
                    logger.debug(
                        "Near-miss TRAJECTORY WARNING frame=%d tracks=#%d,#%d ttc=%d frames",
                        frame_id, pa.track_id, pb.track_id, ttc_warn,
                    )

        return viols

    def _check_zone_entry(
        self,
        persons: list[TrackedObject],
        frame_id: int,
    ) -> list[Violation]:
        """Fire a near_miss for any person whose foot touches a no_entry zone."""
        import cv2

        viols: list[Violation] = []
        for person in persons:
            x1, _, x2, y2 = person.bbox
            foot = ((x1 + x2) / 2.0, float(y2))

            for zone_id, poly in self._zone_polys.items():
                inside = cv2.pointPolygonTest(poly, foot, measureDist=False) >= 0
                if inside:
                    viols.append(Violation(
                        type      = "near_miss",
                        track_id  = person.track_id,
                        frame_id  = frame_id,
                        bbox      = person.bbox,
                        severity  = "WARNING",
                        zone_id   = zone_id,
                        zone_rule = "zone_entry",
                        confidence= person.confidence,
                        missing_ppe = [],
                    ))
                    logger.debug(
                        "Near-miss ZONE_ENTRY frame=%d track=#%d zone=%s",
                        frame_id, person.track_id, zone_id,
                    )

        return viols
