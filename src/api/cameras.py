"""
Camera discovery, video-file discovery, and snapshot endpoints.

GET /cameras                         → list of connected webcams
GET /cameras/{index}/snapshot        → JPEG frame from a webcam
GET /cameras/video-files             → .mp4/.avi/.mov files in data/input_videos/
GET /cameras/video-snapshot?path=…   → JPEG frame from a video file

Used by the setup wizard and zone editor to provide live background images
for the polygon zone-drawing canvas.
"""
import logging
import sys
from pathlib import Path

import cv2
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from src.auth.dependencies import require_auth
from src.auth.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cameras", tags=["cameras"])

# DirectShow is much faster than MSMF for camera probing on Windows
_BACKEND    = cv2.CAP_DSHOW if sys.platform == "win32" else 0
_MAX_INDEX  = 6                                    # probe indices 0–5
_VIDEO_DIR  = Path("data/input_videos")
_VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _open_cam(index: int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(index, _BACKEND)
    if not cap.isOpened() and _BACKEND != 0:
        cap = cv2.VideoCapture(index)
    return cap


def _encode_jpg(frame) -> bytes:
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise HTTPException(500, detail="JPEG encode failed")
    return buf.tobytes()


# ── Webcam endpoints ──────────────────────────────────────────────────────────

@router.get("")
def list_cameras(_: User = Depends(require_auth)) -> list[dict]:
    """Return metadata for every webcam index that opens successfully."""
    cameras: list[dict] = []
    for idx in range(_MAX_INDEX):
        cap = _open_cam(idx)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))  or 640
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
            cameras.append({"index": idx, "label": f"Camera {idx}", "width": w, "height": h})
        cap.release()
    return cameras


@router.get("/{index}/snapshot")
def camera_snapshot(index: int, _: User = Depends(require_auth)):
    """Return a single JPEG frame from webcam *index*."""
    cap = _open_cam(index)
    if not cap.isOpened():
        raise HTTPException(404, detail=f"Camera {index} not found or already in use")

    frame = None
    for _ in range(5):          # skip dark early frames
        ok, f = cap.read()
        if ok and f is not None:
            frame = f
    cap.release()

    if frame is None:
        raise HTTPException(503, detail=f"Could not read from camera {index}")

    return Response(content=_encode_jpg(frame), media_type="image/jpeg")


# ── Video-file endpoints ──────────────────────────────────────────────────────

@router.get("/video-files")
def list_video_files(_: User = Depends(require_auth)) -> list[dict]:
    """Return video files found in data/input_videos/."""
    if not _VIDEO_DIR.exists():
        return []
    result = []
    for p in sorted(_VIDEO_DIR.iterdir()):
        if p.suffix.lower() not in _VIDEO_EXTS:
            continue
        cap = cv2.VideoCapture(str(p))
        fps    = cap.get(cv2.CAP_PROP_FPS) or 30
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w      = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))  or 1920
        h      = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
        cap.release()
        result.append({
            "path":       str(p),
            "name":       p.stem,
            "filename":   p.name,
            "duration_s": round(frames / fps, 1) if fps > 0 else 0,
            "width":      w,
            "height":     h,
        })
    return result


@router.get("/video-snapshot")
def video_snapshot(
    path: str = Query(..., description="Relative path to video file"),
    _: User = Depends(require_auth),
):
    """Return a representative JPEG frame from a video file."""
    p = Path(path)
    if not p.exists() or p.suffix.lower() not in _VIDEO_EXTS:
        raise HTTPException(404, detail=f"Video file not found: {path}")

    cap    = cv2.VideoCapture(str(p))
    total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    target = max(0, total // 3)      # 1/3 through — usually people are visible
    cap.set(cv2.CAP_PROP_POS_FRAMES, target)

    frame = None
    for _ in range(3):
        ok, f = cap.read()
        if ok and f is not None:
            frame = f
    cap.release()

    if frame is None:
        raise HTTPException(503, detail="Could not read frame from video")

    return Response(content=_encode_jpg(frame), media_type="image/jpeg")
