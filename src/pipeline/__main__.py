"""
SafeSight AI — main inference pipeline.

Wires: VideoSource → FrameReader → Detector → Tracker → RulesEngine
       → EventDebouncer → EventStore → WebSocket broadcast

Usage:
    # File
    python -m src.pipeline --source data/input_videos/site.mp4

    # Webcam
    python -m src.pipeline --source 0

    # RTSP (construction site IP camera)
    python -m src.pipeline --source rtsp://192.168.1.64/stream1

    # With custom model and annotated output
    python -m src.pipeline --source rtsp://... --model models/safesight-ppe.pt --output out.mp4

    # Headless (no display window) — for servers / Docker
    python -m src.pipeline --source 0 --no-display
"""
import argparse
import logging
import signal
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from src.pipeline.alerts import WebhookAlerter
from src.api.ws import broadcaster
from src.pipeline.detector import Detection, Detector
from src.pipeline.events import EventDebouncer
from src.osha.matcher import fine_range, match_violation
from src.pipeline.reader import FrameReader
from src.nearmiss.engine import NearMissEngine
from src.pipeline.rules import RulesEngine, SceneConfig
from src.pipeline.sources import open_source
from src.pipeline.store import EventStore
from src.pipeline.tracker import Tracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline")

# ── Annotation helpers ────────────────────────────────────────────────────────

_PALETTE = [
    (0, 220, 0), (0, 140, 255), (255, 0, 140), (255, 215, 0),
    (0, 255, 255), (220, 0, 220), (140, 255, 0), (0, 80, 255),
]
_VIOLATION_COLOUR = (0, 0, 220)   # red (BGR)
_ZONE_COLOUR      = (0, 180, 255) # orange


def _track_colour(track_id: int) -> tuple[int, int, int]:
    return _PALETTE[track_id % len(_PALETTE)]


def _annotate(
    frame_rgb: np.ndarray,
    tracked,
    violations,
    zone_polys: dict,
    fps: float,
    frame_id: int,
) -> np.ndarray:
    out = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

    # Draw zone polygons
    for zone_id, poly in zone_polys.items():
        overlay = out.copy()
        cv2.fillPoly(overlay, [poly], _ZONE_COLOUR)
        cv2.addWeighted(overlay, 0.15, out, 0.85, 0, out)
        cv2.polylines(out, [poly], isClosed=True, color=_ZONE_COLOUR, thickness=2)
        cx = int(poly[:, 0].mean())
        cy = int(poly[:, 1].mean())
        cv2.putText(out, zone_id, (cx, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.6, _ZONE_COLOUR, 2)

    # Collect track IDs that have active violations this frame
    violating_ids = {v.track_id for v in violations}

    for obj in tracked:
        if obj.class_name != "person":
            continue
        x1, y1, x2, y2 = obj.bbox
        colour = _VIOLATION_COLOUR if obj.track_id in violating_ids else _track_colour(obj.track_id)
        cv2.rectangle(out, (x1, y1), (x2, y2), colour, 2)
        label = f"#{obj.track_id}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        cv2.rectangle(out, (x1, y1 - th - 6), (x1 + tw + 4, y1), colour, -1)
        cv2.putText(out, label, (x1 + 2, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1)

        if obj.track_id in violating_ids:
            v_labels = [
                (f"NO {p.upper()}" if v.type == "missing_ppe"
                 else f"NEAR MISS: {v.zone_rule or 'proximity'}" if v.type == "near_miss"
                 else f"ZONE: {v.zone_id}")
                for v in violations
                if v.track_id == obj.track_id
            ]
            for i, vl in enumerate(v_labels):
                cv2.putText(
                    out, vl,
                    (x1, y2 + 16 + i * 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, _VIOLATION_COLOUR, 1,
                )

    # HUD
    cv2.putText(out, f"FPS {fps:4.1f}", (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 210, 255), 2)
    cv2.putText(
        out,
        f"tracks {len([t for t in tracked if t.class_name == 'person'])}  "
        f"violations {len(violations)}  frame {frame_id}",
        (10, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1,
    )
    return out


# ── Person inference from head detections ─────────────────────────────────────

def _persons_from_heads(
    head_dets: list[Detection],
    frame_w: int,
    frame_h: int,
    frame_id: int,
) -> list[Detection]:
    """Infer full-body bounding boxes from hardhat / no-hardhat detections.

    The fine-tuned PPE model detects hardhats reliably (confidence 0.29–0.85)
    but the ``Person`` class only fires at 0.07–0.15 — below any useful
    threshold.  When head detections outnumber person detections we synthesise
    person boxes by expanding each head bbox downward to cover the body
    (≈ 7× head height) and slightly outward for shoulders.
    """
    persons: list[Detection] = []
    for h in head_dets:
        x1, y1, x2, y2 = h.bbox
        head_h = max(y2 - y1, 1)
        head_w = max(x2 - x1, 1)
        body_h = int(head_h * 6)       # typical person ≈ 7× head height
        shoulder_pad = head_w // 3     # widen slightly for shoulders
        px1 = max(0, x1 - shoulder_pad)
        px2 = min(frame_w, x2 + shoulder_pad)
        py2 = min(frame_h, y2 + body_h)
        persons.append(
            Detection(
                bbox=(px1, y1, px2, py2),
                class_name="person",
                confidence=h.confidence,
                frame_id=frame_id,
            )
        )
    return persons


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run(
    source_uri: str,
    config_path: Path,
    model_path: str,
    db_path: Path,
    snapshot_dir: Path,
    output_path: Path | None,
    display: bool,
    confidence: float,
    imgsz: int,
    sahi: bool,
    webhook_url: str | None = None,
) -> None:
    # ── Setup ─────────────────────────────────────────────────────────────────
    scene = SceneConfig.from_json(config_path)
    source = open_source(source_uri)
    fps = source.info.fps or 25.0

    detector = Detector(model_path=model_path, confidence=confidence, imgsz=imgsz, sahi=sahi)
    tracker  = Tracker(frame_rate=fps)
    rules      = RulesEngine(scene)
    near_miss  = NearMissEngine(scene=scene)
    debouncer  = EventDebouncer(fps=fps)
    # Separate debouncer for near-miss: fires faster (2 frames) and shorter cooldown
    nm_debouncer = EventDebouncer(fps=fps, min_duration=2/fps, cooldown_duration=1.0)
    store    = EventStore(db_path=db_path, snapshot_dir=snapshot_dir)
    alerter  = WebhookAlerter(webhook_url) if webhook_url else None

    zone_polys = {
        z.id: np.array(z.polygon, dtype=np.int32) for z in scene.zones
    }

    writer: cv2.VideoWriter | None = None
    if output_path:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(
            str(output_path), fourcc, fps,
            (source.info.width, source.info.height),
        )
        logger.info("Writing annotated output to %s", output_path)

    window = "SafeSight AI  (q / ESC to quit)"

    logger.info(
        "Pipeline started — source=%s model=%s fps=%.1f",
        source_uri, model_path, fps,
    )

    # ── Main loop ─────────────────────────────────────────────────────────────
    quit_flag = False

    def _sigint(*_):
        nonlocal quit_flag
        quit_flag = True

    signal.signal(signal.SIGINT, _sigint)

    frame_id = 0
    smooth_fps = 0.0
    t_last = time.perf_counter()

    with FrameReader(source).start() as reader:
        while not quit_flag:
            ok, frame = reader.read(timeout=2.0)
            if not ok:
                logger.info("Stream ended at frame %d", frame_id)
                break

            # ── Inference ─────────────────────────────────────────────────────
            detections  = detector.detect(frame, frame_id)
            # Only track persons; pass all detections to rules for PPE overlap
            person_dets = [d for d in detections if d.class_name == "person"]
            head_dets   = [d for d in detections if d.class_name in ("hardhat", "no-hardhat")]

            # Fallback: when head detections outnumber person detections, the
            # fine-tuned model's Person class is likely below threshold.  Infer
            # body bounding boxes from hardhat positions so the tracker gets
            # real targets to follow and the rules engine can check PPE.
            if len(head_dets) > len(person_dets):
                person_dets = _persons_from_heads(
                    head_dets, frame.shape[1], frame.shape[0], frame_id
                )

            tracked         = tracker.update(person_dets, frame_id)
            violations      = rules.check(tracked, detections, frame_id)
            nm_violations   = near_miss.check(tracked, detections, frame_id)
            opened, closed  = debouncer.update(violations, frame_id)
            nm_opened, nm_closed = nm_debouncer.update(nm_violations, frame_id)
            opened  = opened  + nm_opened
            closed  = closed  + nm_closed

            # ── Enrich opened events with OSHA codes ──────────────────────────
            for event in opened:
                codes = match_violation(
                    event.event_type,
                    missing_ppe=event.missing_ppe or None,
                    zone_rule=event.zone_rule,
                )
                event.osha_codes = [c.code for c in codes]
                event.fine_min_usd, event.fine_max_usd = fine_range(codes)

            # ── Persist & broadcast ───────────────────────────────────────────
            for event in opened:
                store.save_event(event, frame)
                broadcaster.publish(event, "opened")
                if alerter:
                    alerter.send(event)
                logger.info(
                    "VIOLATION OPENED  type=%-16s severity=%-8s track=#%d zone=%s missing=%s",
                    event.event_type, event.severity, event.track_id,
                    event.zone_id or "—", event.missing_ppe or "—",
                )

            for event in closed:
                store.close_event(event)
                broadcaster.publish(event, "closed")
                logger.info(
                    "VIOLATION CLOSED  type=%-16s track=#%d frames=%d–%d",
                    event.event_type, event.track_id,
                    event.start_frame, event.end_frame,
                )

            # ── FPS ───────────────────────────────────────────────────────────
            now = time.perf_counter()
            smooth_fps = 0.9 * smooth_fps + 0.1 / max(now - t_last, 1e-6)
            t_last = now

            # ── Annotate ──────────────────────────────────────────────────────
            if display or writer:
                annotated = _annotate(frame, tracked, violations, zone_polys, smooth_fps, frame_id)
                if writer:
                    writer.write(annotated)
                if display:
                    cv2.imshow(window, annotated)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (ord("q"), 27):
                        break
                    if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                        break

            if frame_id % 300 == 0:
                logger.info(
                    "frame=%d  fps=%.1f  tracks=%d  violations_this_frame=%d",
                    frame_id, smooth_fps,
                    len([t for t in tracked if t.class_name == "person"]),
                    len(violations),
                )

            frame_id += 1

    # ── Shutdown ──────────────────────────────────────────────────────────────
    flushed = debouncer.flush(frame_id) + nm_debouncer.flush(frame_id)
    for event in flushed:
        store.close_event(event)
        broadcaster.publish(event, "closed")

    store.close()
    source.release()
    if writer:
        writer.release()
    if alerter:
        alerter.shutdown(wait=True)
    cv2.destroyAllWindows()
    logger.info("Pipeline shut down cleanly after %d frames", frame_id)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m src.pipeline",
        description="SafeSight AI — real-time construction site safety monitoring",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--source",     required=True,
                   help="Video source: file path, webcam index (0), or rtsp:// URL")
    p.add_argument("--config",     type=Path, default=Path("config/zones.json"),
                   help="Zone configuration JSON")
    p.add_argument("--model",      default="yolo26s.pt",
                   help="YOLO model path (auto-downloads if not present)")
    p.add_argument("--output",     type=Path, default=None,
                   help="Save annotated video to this path (optional)")
    p.add_argument("--db",         type=Path, default=Path("data/events.db"),
                   help="SQLite database path")
    p.add_argument("--snapshots",  type=Path, default=Path("data/snapshots"),
                   help="Directory for violation snapshot JPEGs")
    p.add_argument("--confidence", type=float, default=0.25,
                   help="Detection confidence threshold")
    p.add_argument("--imgsz",      type=int,   default=640,
                   help="YOLO inference image size (larger = slower but catches distant workers)")
    p.add_argument("--sahi",       action="store_true",
                   help="Enable sliced inference — best for distant workers, costs ~3× FPS")
    p.add_argument("--no-display", action="store_true",
                   help="Suppress live display window (for headless / server use)")
    p.add_argument("--webhook-url", default=None,
                   help="HTTP endpoint to POST violation events to (optional). "
                        "Can also be set via SAFESIGHT_WEBHOOK_URL env var.")
    return p.parse_args()


if __name__ == "__main__":
    import os
    args = _parse_args()
    webhook = args.webhook_url or os.environ.get("SAFESIGHT_WEBHOOK_URL")
    try:
        run(
            source_uri   = args.source,
            config_path  = args.config,
            model_path   = args.model,
            db_path      = args.db,
            snapshot_dir = args.snapshots,
            output_path  = args.output,
            display      = not args.no_display,
            confidence   = args.confidence,
            imgsz        = args.imgsz,
            sahi         = args.sahi,
            webhook_url  = webhook,
        )
    except KeyboardInterrupt:
        sys.exit(0)
