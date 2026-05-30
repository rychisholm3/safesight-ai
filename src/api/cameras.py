"""
Camera discovery and snapshot endpoints.

GET /cameras                  → list of connected cameras with metadata
GET /cameras/{index}/snapshot → single JPEG frame from that camera

Used by the setup wizard to show live camera thumbnails and provide a
background image for the polygon zone-drawing canvas.
"""
import logging
import sys
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

import cv2

from src.auth.dependencies import require_auth
from src.auth.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cameras", tags=["cameras"])

# DirectShow is much faster than MSMF for camera probing on Windows
_BACKEND = cv2.CAP_DSHOW if sys.platform == "win32" else 0
_MAX_INDEX = 6  # probe indices 0–5


def _open(index: int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(index, _BACKEND)
    if not cap.isOpened() and _BACKEND != 0:
        cap = cv2.VideoCapture(index)  # fallback to default backend
    return cap


@router.get("")
def list_cameras(_: User = Depends(require_auth)) -> list[dict]:
    """Return metadata for every camera index that successfully opens."""
    cameras: list[dict] = []
    for idx in range(_MAX_INDEX):
        cap = _open(idx)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))  or 640
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
            cameras.append({
                "index": idx,
                "label": f"Camera {idx}",
                "width": w,
                "height": h,
            })
        cap.release()
    return cameras


@router.get("/{index}/snapshot")
def camera_snapshot(index: int, _: User = Depends(require_auth)):
    """Return a JPEG frame from camera *index*."""
    cap = _open(index)
    if not cap.isOpened():
        raise HTTPException(404, detail=f"Camera {index} not found or already in use")

    frame = None
    for _ in range(5):          # skip early frames which can be dark/blank
        ok, f = cap.read()
        if ok and f is not None:
            frame = f
    cap.release()

    if frame is None:
        raise HTTPException(503, detail=f"Could not read a frame from camera {index}")

    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise HTTPException(500, detail="JPEG encode failed")

    return Response(content=buf.tobytes(), media_type="image/jpeg")
