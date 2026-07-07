import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from src.pipeline.rules import Violation

logger = logging.getLogger(__name__)

# Debounce key: one state machine per (track_id, event_type, zone_id) tuple.
_DebounceKey = tuple[int, str, str | None]


@dataclass
class Event:
    event_id: str
    event_type: str                 # "missing_ppe" | "zone_intrusion"
    track_id: int
    zone_id: str | None             # None for global PPE violations
    missing_ppe: list[str]          # empty for zone_intrusion events
    start_frame: int
    end_frame: int | None           # None while the violation is still active
    snapshot_path: Path | None      # filled in by store.py
    severity: str = "WARNING"       # "WARNING" | "CRITICAL"
    zone_rule: str | None = None    # "no_entry" | "require_ppe" | None
    osha_codes: list[str] = field(default_factory=list)   # e.g. ["29 CFR 1926.100(a)"]
    fine_min_usd: int = 0
    fine_max_usd: int = 0
    confidence: float = 0.0         # detection confidence of the tracked person (0–1)
    bbox: tuple[int, int, int, int] | None = None  # (x1,y1,x2,y2) person bbox in frame
    person_detections: list[dict] = field(default_factory=list)  # serialised per-class detections


@dataclass
class _ViolationState:
    """Per-key debounce state."""
    pending_frames: int = 0         # consecutive frames seen, not yet opened
    active_event: Event | None = None
    cooldown_frames: int = 0        # consecutive frames absent while active
    last_missing_ppe: list[str] = field(default_factory=list)


class EventDebouncer:
    def __init__(
        self,
        fps: float,
        min_duration: float = 0.5,
        cooldown_duration: float = 2.0,
    ) -> None:
        self._min_frames = max(1, round(fps * min_duration))
        self._cooldown_frames = max(1, round(fps * cooldown_duration))
        self._states: dict[_DebounceKey, _ViolationState] = {}
        logger.info(
            "EventDebouncer ready: fps=%.1f min_frames=%d cooldown_frames=%d",
            fps,
            self._min_frames,
            self._cooldown_frames,
        )

    def _key(self, v: Violation) -> _DebounceKey:
        return (v.track_id, v.type, v.zone_id)

    def update(
        self,
        violations: list[Violation],
        frame_id: int,
    ) -> tuple[list[Event], list[Event]]:
        """Process one frame's violations. Returns (newly_opened, newly_closed)."""
        opened: list[Event] = []
        closed: list[Event] = []

        seen: dict[_DebounceKey, Violation] = {self._key(v): v for v in violations}

        # Advance states for keys seen this frame.
        for key, violation in seen.items():
            state = self._states.setdefault(key, _ViolationState())
            state.cooldown_frames = 0
            state.last_missing_ppe = list(violation.missing_ppe)

            if state.active_event is not None:
                continue  # already open, nothing to do

            state.pending_frames += 1
            if state.pending_frames >= self._min_frames:
                event = Event(
                    event_id=uuid.uuid4().hex,
                    event_type=violation.type,
                    track_id=violation.track_id,
                    zone_id=violation.zone_id,
                    missing_ppe=list(violation.missing_ppe),
                    start_frame=frame_id - self._min_frames + 1,
                    end_frame=None,
                    snapshot_path=None,
                    severity=violation.severity,
                    zone_rule=violation.zone_rule,
                    confidence=violation.confidence,
                    bbox=violation.bbox,
                    person_detections=[
                        {
                            "class_name": d.class_name,
                            "bbox":       list(d.bbox),
                            "confidence": float(d.confidence),
                        }
                        for d in violation.person_detections
                    ],
                )
                state.active_event = event
                state.pending_frames = 0
                opened.append(event)
                logger.debug(
                    "Event opened: %s track_id=%d zone=%s",
                    event.event_type,
                    event.track_id,
                    event.zone_id,
                )

        # Advance cooldown for keys not seen this frame.
        for key, state in list(self._states.items()):
            if key in seen:
                continue

            state.pending_frames = 0

            if state.active_event is None:
                del self._states[key]
                continue

            state.cooldown_frames += 1
            if state.cooldown_frames >= self._cooldown_frames:
                state.active_event.end_frame = frame_id
                closed.append(state.active_event)
                logger.debug(
                    "Event closed: %s track_id=%d zone=%s",
                    state.active_event.event_type,
                    state.active_event.track_id,
                    state.active_event.zone_id,
                )
                del self._states[key]

        return opened, closed

    def flush(self, frame_id: int) -> list[Event]:
        """Force-close all open events. Call when stream ends."""
        flushed: list[Event] = []
        for state in self._states.values():
            if state.active_event is not None:
                state.active_event.end_frame = frame_id
                flushed.append(state.active_event)
                logger.debug(
                    "Event flushed: %s track_id=%d",
                    state.active_event.event_type,
                    state.active_event.track_id,
                )
        self._states.clear()
        return flushed
