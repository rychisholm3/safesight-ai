"""
Smoke test: webcam -> YOLO26 detection -> ByteTrack -> annotated live window.

Usage:
    python scripts/smoke_test.py                  # webcam 0, yolo26s.pt, imgsz=1280
    python scripts/smoke_test.py --device 1       # different webcam
    python scripts/smoke_test.py --sahi           # sliced inference (better for far-away objects)
    python scripts/smoke_test.py --imgsz 640      # faster inference at lower resolution

Press q in the window to quit.
"""
import argparse
import logging
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.detector import Detector, Detection
from src.reader import FrameReader
from src.sources import WebcamSource
from src.tracker import Tracker, TrackedObject

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("smoke_test")

# Colour palette — cycles through track IDs so each person gets a distinct colour
_PALETTE = [
    (0, 255, 0), (0, 128, 255), (255, 0, 128), (255, 255, 0),
    (0, 255, 255), (255, 0, 255), (128, 255, 0), (0, 64, 255),
]


def _colour(track_id: int) -> tuple[int, int, int]:
    return _PALETTE[track_id % len(_PALETTE)]


def _annotate(frame_rgb: np.ndarray, tracked: list[TrackedObject], detections: list[Detection], fps: float) -> np.ndarray:
    # Work in BGR for OpenCV drawing
    out = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

    # Untracked detections (before tracks are confirmed) shown as grey dashes
    tracked_bboxes = {obj.bbox for obj in tracked}
    for d in detections:
        if d.bbox not in tracked_bboxes:
            x1, y1, x2, y2 = d.bbox
            cv2.rectangle(out, (x1, y1), (x2, y2), (120, 120, 120), 1)

    # Confirmed tracked objects
    for obj in tracked:
        x1, y1, x2, y2 = obj.bbox
        colour = _colour(obj.track_id)
        cv2.rectangle(out, (x1, y1), (x2, y2), colour, 2)
        label = f"ID {obj.track_id}  {obj.class_name}  {obj.confidence:.0%}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(out, (x1, y1 - th - 6), (x1 + tw + 4, y1), colour, -1)
        cv2.putText(out, label, (x1 + 2, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

    # HUD
    cv2.putText(out, f"FPS {fps:4.1f}", (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
    cv2.putText(out, f"det {len(detections):2d}  tracks {len(tracked):2d}", (10, 56),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="SafeSight smoke test — live webcam view")
    parser.add_argument("--device", type=int, default=0, help="Webcam device index (default: 0)")
    parser.add_argument("--model", default="yolo26s.pt", help="YOLO model path/name")
    parser.add_argument("--confidence", type=float, default=0.3, help="Detection confidence threshold")
    parser.add_argument("--imgsz", type=int, default=1280, help="Inference image size (default: 1280)")
    parser.add_argument("--sahi", action="store_true", help="Enable sliced inference for small/distant objects")
    args = parser.parse_args()

    logger.info("Opening webcam device %d", args.device)
    source = WebcamSource(device_index=args.device)
    logger.info("Source: %dx%d @ %.0f fps", source.info.width, source.info.height, source.info.fps)

    logger.info("Loading model %s (downloads on first run if missing)", args.model)
    detector = Detector(
        model_path=args.model,
        confidence=args.confidence,
        imgsz=args.imgsz,
        sahi=args.sahi,
    )
    tracker = Tracker(frame_rate=source.info.fps)

    frame_id = 0
    fps = 0.0
    t_last = time.perf_counter()

    logger.info("Pipeline running — press q in the window to quit")
    with FrameReader(source).start() as reader:
        while True:
            ok, frame = reader.read(timeout=1.0)
            if not ok:
                logger.warning("No frame received — webcam disconnected?")
                break

            detections = detector.detect(frame, frame_id)
            tracked = tracker.update(detections, frame_id)

            now = time.perf_counter()
            fps = 0.9 * fps + 0.1 / max(now - t_last, 1e-6)
            t_last = now

            cv2.imshow("SafeSight — smoke test  (q to quit)", _annotate(frame, tracked, detections, fps))

            if frame_id % 30 == 0:
                logger.info("frame=%d  det=%d  tracks=%d  fps=%.1f", frame_id, len(detections), len(tracked), fps)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

            frame_id += 1

    cv2.destroyAllWindows()
    source.release()
    logger.info("Stopped after %d frames", frame_id)


if __name__ == "__main__":
    main()
