"""
Snapshot annotation — draws colour-coded bounding boxes on a saved JPEG frame.

Box colour scheme
-----------------
Blue   (person bbox)    — the tracked worker
Green  (PPE present)    — a PPE item the model detected on this person
Red    (PPE absent)     — a "no-*" indicator class (model explicitly flagged absence)

This gives auditors an at-a-glance view: green = compliant, red = violation.
"""
import logging
from pathlib import Path

import cv2

logger = logging.getLogger(__name__)

# BGR colour palette
_COLOR_PERSON  = (220, 100,  30)   # blue-orange (person outline)
_COLOR_PRESENT = ( 40, 180,  40)   # green — PPE detected
_COLOR_ABSENT  = ( 30,  30, 210)   # red — no-PPE indicator fired

# Maps class_name → display label shown in the image
_CLASS_LABELS: dict[str, str] = {
    "hardhat":      "Hardhat OK",
    "vest":         "Vest OK",
    "mask":         "Mask OK",
    "gloves":       "Gloves OK",
    "safety_shoes": "Boots OK",
    "no-hardhat":   "NO Hardhat",
    "no-vest":      "NO Vest",
    "no-mask":      "NO Mask",
}

# Which classes are "no-*" absence indicators
_ABSENT_CLASSES = {"no-hardhat", "no-vest", "no-mask"}


def _box_color(class_name: str) -> tuple[int, int, int]:
    if class_name in _ABSENT_CLASSES:
        return _COLOR_ABSENT
    return _COLOR_PRESENT


def _draw_box(
    frame,
    bbox: tuple[int, int, int, int],
    label: str,
    color: tuple[int, int, int],
    thickness: int,
    font_scale: float,
) -> None:
    h, w = frame.shape[:2]
    x1 = max(0, int(bbox[0]))
    y1 = max(0, int(bbox[1]))
    x2 = min(w - 1, int(bbox[2]))
    y2 = min(h - 1, int(bbox[3]))

    font       = cv2.FONT_HERSHEY_SIMPLEX
    text_thick = max(1, thickness - 1)

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

    (tw, th), baseline = cv2.getTextSize(label, font, font_scale, text_thick)
    pad  = 4
    lx1  = x1
    ly2  = y1
    ly1  = max(0, y1 - th - baseline - pad * 2)
    lx2  = min(w, x1 + tw + pad * 2)

    cv2.rectangle(frame, (lx1, ly1), (lx2, ly2), color, -1)
    cv2.putText(
        frame, label,
        (lx1 + pad, ly2 - baseline - pad // 2),
        font, font_scale, (255, 255, 255), text_thick, cv2.LINE_AA,
    )


def annotate_snapshot(
    snapshot_path: Path,
    bbox: tuple[int, int, int, int] | None,
    label: str,
    severity: str = "WARNING",
    person_detections: list[dict] | None = None,
) -> bytes | None:
    """
    Load *snapshot_path* and draw:
      • The person bounding box (coloured by severity)
      • Per-class PPE detection boxes (green = present, red = absent)

    Returns JPEG bytes, or None if the file is missing / unreadable.
    """
    if not snapshot_path.exists():
        logger.warning("Snapshot not found for annotation: %s", snapshot_path)
        return None

    frame = cv2.imread(str(snapshot_path))
    if frame is None:
        logger.warning("cv2 could not decode snapshot: %s", snapshot_path)
        return None

    h, w = frame.shape[:2]
    thickness  = max(2, round(min(h, w) * 0.004))
    font_scale = max(0.4, min(w / 1400.0, 0.7))

    # ── Person bbox ──────────────────────────────────────────────────────────
    if bbox is not None:
        x1, y1, x2, y2 = (
            max(0, int(bbox[0])), max(0, int(bbox[1])),
            min(w - 1, int(bbox[2])), min(h - 1, int(bbox[3])),
        )
        person_color = (30, 30, 210) if severity == "CRITICAL" else (200, 100, 30)

        cv2.rectangle(frame, (x1, y1), (x2, y2), person_color, thickness)

        # Corner accents
        accent_len = max(10, (x2 - x1) // 6)
        for cx, cy, sx, sy in [
            (x1, y1,  1,  1), (x2, y1, -1,  1),
            (x1, y2,  1, -1), (x2, y2, -1, -1),
        ]:
            cv2.line(frame, (cx, cy), (cx + sx * accent_len, cy), person_color, thickness + 1)
            cv2.line(frame, (cx, cy), (cx, cy + sy * accent_len), person_color, thickness + 1)

        # Main label
        _draw_box(frame, (x1, y1, x2, y2), label, person_color, 0, font_scale)
        # (draw label only — rectangle already drawn above, so use thickness=0 trick below)
        # Re-draw label properly without double rectangle:
        font       = cv2.FONT_HERSHEY_SIMPLEX
        text_thick = max(1, thickness - 1)
        (tw, th), baseline = cv2.getTextSize(label, font, font_scale, text_thick)
        pad = 4
        lx1, ly2 = x1, y1
        ly1 = max(0, y1 - th - baseline - pad * 2)
        lx2 = min(w, x1 + tw + pad * 2)
        cv2.rectangle(frame, (lx1, ly1), (lx2, ly2), person_color, -1)
        cv2.putText(frame, label, (lx1 + pad, ly2 - baseline - pad // 2),
                    font, font_scale, (255, 255, 255), text_thick, cv2.LINE_AA)

    # ── Per-class PPE detection boxes ────────────────────────────────────────
    for det in (person_detections or []):
        cls_name  = det.get("class_name", "")
        det_bbox  = det.get("bbox")
        if not det_bbox or len(det_bbox) < 4:
            continue

        color     = _box_color(cls_name)
        det_label = _CLASS_LABELS.get(cls_name, cls_name)
        det_thick = max(1, thickness - 1)

        dx1 = max(0, int(det_bbox[0]))
        dy1 = max(0, int(det_bbox[1]))
        dx2 = min(w - 1, int(det_bbox[2]))
        dy2 = min(h - 1, int(det_bbox[3]))

        cv2.rectangle(frame, (dx1, dy1), (dx2, dy2), color, det_thick)

        fs = max(0.35, font_scale * 0.8)
        font       = cv2.FONT_HERSHEY_SIMPLEX
        (tw, th), baseline = cv2.getTextSize(det_label, font, fs, 1)
        pad = 3
        lx1, ly2 = dx1, dy1
        ly1 = max(0, dy1 - th - baseline - pad * 2)
        lx2 = min(w, dx1 + tw + pad * 2)
        cv2.rectangle(frame, (lx1, ly1), (lx2, ly2), color, -1)
        cv2.putText(frame, det_label, (lx1 + pad, ly2 - baseline - pad // 2),
                    font, fs, (255, 255, 255), 1, cv2.LINE_AA)

    # ── Encode to JPEG ────────────────────────────────────────────────────────
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        logger.error("Failed to encode annotated snapshot")
        return None
    return bytes(buf)


def _make_label(event: dict) -> str:
    """Build a short violation label string from an event dict."""
    etype   = event.get("event_type", "")
    sev     = event.get("severity", "WARNING")
    missing = event.get("missing_ppe") or []

    if etype == "missing_ppe":
        ppe_str = ", ".join(missing[:2]) + ("..." if len(missing) > 2 else "")
        return f"[{sev}] Missing: {ppe_str}" if ppe_str else f"[{sev}] Missing PPE"
    else:
        zone = event.get("zone_id") or "zone"
        return f"[{sev}] Zone: {zone}"
