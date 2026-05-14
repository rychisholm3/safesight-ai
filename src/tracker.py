import logging
from dataclasses import dataclass

import numpy as np
import supervision as sv
from trackers import ByteTrackTracker

from src.detector import Detection

logger = logging.getLogger(__name__)


@dataclass
class TrackedObject:
    track_id: int
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2 in pixels
    class_name: str
    confidence: float
    frame_id: int


class Tracker:
    def __init__(
        self,
        lost_track_buffer: int = 60,
        frame_rate: float = 30.0,
        track_activation_threshold: float = 0.5,
        minimum_consecutive_frames: int = 1,
    ) -> None:
        self._bytetrack = ByteTrackTracker(
            lost_track_buffer=lost_track_buffer,
            frame_rate=frame_rate,
            track_activation_threshold=track_activation_threshold,
            minimum_consecutive_frames=minimum_consecutive_frames,
        )
        self._class_name_to_id: dict[str, int] = {}
        self._id_to_class_name: dict[int, str] = {}
        logger.info(
            "Tracker initialised: lost_track_buffer=%d frame_rate=%.1f "
            "activation_threshold=%.2f min_consecutive=%d",
            lost_track_buffer,
            frame_rate,
            track_activation_threshold,
            minimum_consecutive_frames,
        )

    def _class_id(self, class_name: str) -> int:
        """Return a stable integer ID for class_name, registering new names on first sight."""
        if class_name not in self._class_name_to_id:
            cid = len(self._class_name_to_id)
            self._class_name_to_id[class_name] = cid
            self._id_to_class_name[cid] = class_name
        return self._class_name_to_id[class_name]

    def update(self, detections: list[Detection], frame_id: int) -> list[TrackedObject]:
        """Assign persistent track IDs; returns only confirmed tracks (tracker_id >= 0)."""
        if not detections:
            self._bytetrack.update(sv.Detections.empty())
            return []

        xyxy = np.array([[*d.bbox] for d in detections], dtype=float)
        confidences = np.array([d.confidence for d in detections], dtype=float)
        class_ids = np.array([self._class_id(d.class_name) for d in detections], dtype=int)

        sv_dets = sv.Detections(xyxy=xyxy, confidence=confidences, class_id=class_ids)
        tracked = self._bytetrack.update(sv_dets)

        if tracked.tracker_id is None or len(tracked) == 0:
            return []

        objects: list[TrackedObject] = []
        for i in range(len(tracked)):
            tid = int(tracked.tracker_id[i])
            if tid < 0:
                continue
            x1, y1, x2, y2 = tracked.xyxy[i]
            class_name = self._id_to_class_name.get(int(tracked.class_id[i]), "unknown")
            conf = float(tracked.confidence[i]) if tracked.confidence is not None else 0.0
            objects.append(
                TrackedObject(
                    track_id=tid,
                    bbox=(int(x1), int(y1), int(x2), int(y2)),
                    class_name=class_name,
                    confidence=conf,
                    frame_id=frame_id,
                )
            )

        logger.debug(
            "frame=%d detections=%d confirmed_tracks=%d",
            frame_id,
            len(detections),
            len(objects),
        )
        return objects

    def reset(self) -> None:
        """Clear all track state and class name registry."""
        self._bytetrack.reset()
        self._class_name_to_id.clear()
        self._id_to_class_name.clear()
        logger.info("Tracker state reset")
