"""
Snapshot annotation — draws bounding boxes and violation labels on a saved
JPEG frame using OpenCV and returns the result as JPEG bytes.
"""
import logging
from pathlib import Path

import cv2

logger = logging.getLogger(__name__)

# BGR colours
_COLOR_CRITICAL = (30,  30, 220)   # vivid red
_COLOR_WARNING  = (0,  140, 255)   # orange


def annotate_snapshot(
    snapshot_path: Path,
    bbox: tuple[int, int, int, int] | None,
    label: str,
    severity: str = "WARNING",
) -> bytes | None:
    """
    Load *snapshot_path*, draw the person bbox with a labelled tag, and
    return the result as JPEG bytes.  Returns None if the file is missing
    or cannot be decoded.
    """
    if not snapshot_path.exists():
        logger.warning("Snapshot not found for annotation: %s", snapshot_path)
        return None

    frame = cv2.imread(str(snapshot_path))
    if frame is None:
        logger.warning("cv2 could not decode snapshot: %s", snapshot_path)
        return None

    if bbox is not None:
        x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
        h, w = frame.shape[:2]

        # Clamp to frame bounds
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w - 1, x2), min(h - 1, y2)

        color     = _COLOR_CRITICAL if severity == "CRITICAL" else _COLOR_WARNING
        thickness = max(2, round(min(h, w) * 0.004))

        # ── Person bounding box ──────────────────────────────────────────────
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

        # ── Corner accents (makes it feel more like a pro safety system) ─────
        accent_len = max(10, (x2 - x1) // 6)
        for cx, cy, sx, sy in [
            (x1, y1,  1,  1),
            (x2, y1, -1,  1),
            (x1, y2,  1, -1),
            (x2, y2, -1, -1),
        ]:
            cv2.line(frame, (cx, cy), (cx + sx * accent_len, cy), color, thickness + 1)
            cv2.line(frame, (cx, cy), (cx, cy + sy * accent_len), color, thickness + 1)

        # ── Label ────────────────────────────────────────────────────────────
        font       = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = max(0.45, min(w / 1400.0, 0.75))
        text_thick = max(1, thickness - 1)

        (tw, th), baseline = cv2.getTextSize(label, font, font_scale, text_thick)
        pad    = 5
        lx1    = x1
        ly2    = y1
        ly1    = max(0, y1 - th - baseline - pad * 2)
        lx2    = min(w, x1 + tw + pad * 2)

        # Filled label background
        cv2.rectangle(frame, (lx1, ly1), (lx2, ly2), color, -1)
        cv2.putText(
            frame, label,
            (lx1 + pad, ly2 - baseline - pad // 2),
            font, font_scale, (255, 255, 255), text_thick, cv2.LINE_AA,
        )

    # ── Encode to JPEG ────────────────────────────────────────────────────────
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        logger.error("Failed to encode annotated snapshot")
        return None
    return bytes(buf)


def _make_label(event: dict) -> str:
    """Build a short label string from an event dict."""
    etype = event.get("event_type", "")
    sev   = event.get("severity", "WARNING")

    if etype == "missing_ppe":
        missing = event.get("missing_ppe") or []
        ppe_str = ", ".join(missing[:2]) + ("…" if len(missing) > 2 else "")
        return f"[{sev}] Missing: {ppe_str}" if ppe_str else f"[{sev}] Missing PPE"
    else:
        zone = event.get("zone_id") or "zone"
        return f"[{sev}] Zone intrusion: {zone}"
