"""
Performance benchmark: measures per-stage and full-pipeline FPS across YOLO26 model sizes.

YOLO26 is Ultralytics' edge-optimised detector — 43% faster CPU inference than YOLOv8,
NMS-free design, and improved small-object detection via ProgLoss + STAL. All variants
auto-download from Ultralytics on first run.

Usage:
    # Synthetic frames (no video needed)
    python scripts/benchmark.py

    # Against a real video file
    python scripts/benchmark.py --source data/input_videos/sample.mp4

    # Single model, custom resolution
    python scripts/benchmark.py --models yolo26n --width 640 --height 480

    # More frames for stable numbers
    python scripts/benchmark.py --frames 200 --warmup 10
"""
import argparse
import json
import logging
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.pipeline.detector import Detector
from src.pipeline.tracker import Tracker

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("benchmark")

DEFAULT_MODELS = ["yolo26n.pt", "yolo26s.pt", "yolo26m.pt"]
WARMUP_FRAMES  = 5


# ---------------------------------------------------------------------------
# Frame source helpers
# ---------------------------------------------------------------------------

def _frames_from_video(path: Path, n: int) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {path}")
    frames = []
    while len(frames) < n:
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    cap.release()
    return frames


def _synthetic_frames(n: int, width: int, height: int) -> list[np.ndarray]:
    rng = np.random.default_rng(42)
    return [rng.integers(0, 255, (height, width, 3), dtype=np.uint8) for _ in range(n)]


# ---------------------------------------------------------------------------
# Percentile helper (no scipy needed)
# ---------------------------------------------------------------------------

def _percentile(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = (len(sorted_data) - 1) * p / 100
    lo, hi = int(idx), min(int(idx) + 1, len(sorted_data) - 1)
    return sorted_data[lo] + (sorted_data[hi] - sorted_data[lo]) * (idx - lo)


# ---------------------------------------------------------------------------
# Single-model benchmark run
# ---------------------------------------------------------------------------

def _run(
    model_name: str,
    frames: list[np.ndarray],
    warmup: int,
    imgsz: int,
    device: str,
) -> dict:
    h, w = frames[0].shape[:2]
    print(f"  Loading {model_name} …", end="", flush=True)

    detector = Detector(model_path=model_name, confidence=0.3, imgsz=imgsz)
    tracker  = Tracker(frame_rate=30.0)

    # Warm up — let YOLO JIT-compile / load to device
    for i in range(min(warmup, len(frames))):
        detector.detect(frames[i], i)
    print(" done", flush=True)

    detect_times: list[float] = []
    track_times:  list[float] = []
    total_times:  list[float] = []

    for frame_id, frame in enumerate(frames):
        t0 = time.perf_counter()
        detections = detector.detect(frame, frame_id)
        t1 = time.perf_counter()
        tracker.update(detections, frame_id)
        t2 = time.perf_counter()

        detect_ms = (t1 - t0) * 1000
        track_ms  = (t2 - t1) * 1000
        total_ms  = (t2 - t0) * 1000

        detect_times.append(detect_ms)
        track_times.append(track_ms)
        total_times.append(total_ms)

    def _stats(times: list[float]) -> dict:
        return {
            "fps":  round(1000 / (sum(times) / len(times)), 1),
            "mean_ms": round(sum(times) / len(times), 1),
            "p50_ms":  round(_percentile(times, 50), 1),
            "p95_ms":  round(_percentile(times, 95), 1),
            "p99_ms":  round(_percentile(times, 99), 1),
        }

    return {
        "model":      model_name,
        "device":     device,
        "resolution": f"{w}x{h}",
        "imgsz":      imgsz,
        "frames":     len(frames),
        "detect":     _stats(detect_times),
        "track":      _stats(track_times),
        "pipeline":   _stats(total_times),
    }


# ---------------------------------------------------------------------------
# Pretty-print results table
# ---------------------------------------------------------------------------

def _print_table(results: list[dict]) -> None:
    col_w = 14
    header_cols = ["model", "device", "res", "det FPS", "det p95", "pipe FPS", "pipe p95", "pipe p99"]
    sep = "+" + "+".join("-" * (col_w + 2) for _ in header_cols) + "+"

    def row(*cells: str) -> str:
        return "|" + "|".join(f" {str(c):<{col_w}} " for c in cells) + "|"

    print("\n" + sep)
    print(row(*header_cols))
    print(sep)
    for r in results:
        print(row(
            r["model"],
            r["device"],
            r["resolution"],
            f"{r['detect']['fps']} fps",
            f"{r['detect']['p95_ms']} ms",
            f"{r['pipeline']['fps']} fps",
            f"{r['pipeline']['p95_ms']} ms",
            f"{r['pipeline']['p99_ms']} ms",
        ))
    print(sep + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="SafeSight pipeline benchmark")
    parser.add_argument("--source",  type=Path, default=None,    help="Video file to benchmark against (optional)")
    parser.add_argument("--models",  nargs="+", default=DEFAULT_MODELS, help="Model names/paths to benchmark")
    parser.add_argument("--frames",  type=int,  default=100,     help="Frames to measure per model (default: 100)")
    parser.add_argument("--warmup",  type=int,  default=WARMUP_FRAMES, help="Warmup frames before measuring (default: 5)")
    parser.add_argument("--width",   type=int,  default=1280,    help="Synthetic frame width (default: 1280)")
    parser.add_argument("--height",  type=int,  default=720,     help="Synthetic frame height (default: 720)")
    parser.add_argument("--imgsz",   type=int,  default=640,     help="YOLO inference size (default: 640)")
    parser.add_argument("--output",  type=Path, default=Path("benchmark_results.json"), help="JSON output path")
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    total_frames = args.warmup + args.frames

    print(f"\nSafeSight Benchmark")
    print(f"  Device     : {device}" + (f" ({torch.cuda.get_device_name(0)})" if device == "cuda" else ""))
    print(f"  Models     : {', '.join(args.models)}")
    print(f"  Frames     : {args.frames} measured  +  {args.warmup} warmup")
    print(f"  imgsz      : {args.imgsz}")

    if args.source:
        print(f"  Source     : {args.source}")
        all_frames = _frames_from_video(args.source, total_frames)
    else:
        print(f"  Source     : synthetic {args.width}x{args.height} frames")
        all_frames = _synthetic_frames(total_frames, args.width, args.height)

    print()
    results = []
    for model_name in args.models:
        print(f"[{model_name}]")
        try:
            result = _run(
                model_name=model_name,
                frames=all_frames[args.warmup:],  # exclude warmup frames from stats
                warmup=args.warmup,
                imgsz=args.imgsz,
                device=device,
            )
            results.append(result)
            print(f"  detect : {result['detect']['fps']} fps  (p95 {result['detect']['p95_ms']} ms)")
            print(f"  tracker: {result['track']['fps']} fps  (p95 {result['track']['p95_ms']} ms)")
            print(f"  total  : {result['pipeline']['fps']} fps  (p95 {result['pipeline']['p95_ms']} ms)")
        except Exception as exc:
            print(f"  FAILED: {exc}")
        print()

    if results:
        _print_table(results)
        args.output.write_text(json.dumps(results, indent=2))
        print(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()
