"""
Proximity utilities for near-miss detection.

Provides bbox distance calculations and the constants that define
"too close" thresholds between workers and vehicles.
"""
import math
from dataclasses import dataclass, field

# ── Vehicle classes detectable by the base YOLO model (COCO) ─────────────────
# When Phase 13 adds forklift fine-tuning, those class names will be detected
# automatically since we check membership in this set.
VEHICLE_CLASSES: frozenset[str] = frozenset({
    "car", "truck", "bus", "motorcycle", "bicycle",
    "forklift", "excavator", "scissor_lift",          # Phase 13 fine-tuned
})


@dataclass
class ProximityConfig:
    """Tunable thresholds for near-miss proximity detection."""
    # Person ↔ vehicle edge-to-edge distance thresholds (pixels at typical cam resolution)
    vehicle_critical_px: int = 50    # imminent — CRITICAL near-miss
    vehicle_warning_px:  int = 150   # approaching — WARNING near-miss

    # Person ↔ person (crowding / collision) thresholds
    person_critical_px:  int = 0     # overlapping bboxes
    person_warning_px:   int = 30    # nearly touching

    # Trajectory prediction
    trajectory_frames_ahead:  int = 60   # look this many frames forward (~2 s at 30 fps)
    trajectory_critical_px:   int = 60   # predicted to be this close → CRITICAL
    trajectory_warning_px:    int = 120  # predicted to be this close → WARNING

    # Minimum history frames before trajectory prediction fires
    trajectory_min_history:   int = 5


def bbox_min_distance(
    a: tuple[int, int, int, int],
    b: tuple[int, int, int, int],
) -> float:
    """
    Edge-to-edge minimum pixel distance between two axis-aligned bboxes.
    Returns 0.0 if the boxes overlap or touch.
    """
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    dx = max(0, max(bx1 - ax2, ax1 - bx2))
    dy = max(0, max(by1 - ay2, ay1 - by2))
    return math.sqrt(dx * dx + dy * dy)


def bbox_center(bbox: tuple[int, int, int, int]) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
