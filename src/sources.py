import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SourceInfo:
    fps: float
    width: int
    height: int


class VideoSource(ABC):
    @property
    @abstractmethod
    def info(self) -> SourceInfo: ...

    @abstractmethod
    def read(self) -> tuple[bool, np.ndarray]: ...

    @abstractmethod
    def release(self) -> None: ...

    def __enter__(self) -> "VideoSource":
        return self

    def __exit__(self, *args: object) -> None:
        self.release()


class FileSource(VideoSource):
    def __init__(self, path: Path, loop: bool = False) -> None:
        self._path = path
        self._loop = loop
        self._cap = cv2.VideoCapture(str(path))
        if not self._cap.isOpened():
            raise FileNotFoundError(f"Cannot open video file: {path}")
        self._info = SourceInfo(
            fps=self._cap.get(cv2.CAP_PROP_FPS),
            width=int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            height=int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )
        logger.info(
            "Opened file source: %s (%dx%d @ %.1f fps)",
            path, self._info.width, self._info.height, self._info.fps,
        )

    @property
    def info(self) -> SourceInfo:
        return self._info

    def read(self) -> tuple[bool, np.ndarray]:
        ok, frame = self._cap.read()
        if not ok and self._loop:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._cap.read()
        if not ok:
            return False, np.empty(0, dtype=np.uint8)
        return True, cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    def release(self) -> None:
        self._cap.release()
        logger.info("Released file source: %s", self._path)


class WebcamSource(VideoSource):
    def __init__(self, device_index: int = 0) -> None:
        self._device_index = device_index
        self._cap = cv2.VideoCapture(device_index)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open webcam at index {device_index}")
        raw_fps = self._cap.get(cv2.CAP_PROP_FPS)
        self._info = SourceInfo(
            fps=raw_fps if raw_fps > 0 else 30.0,
            width=int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            height=int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )
        logger.info(
            "Opened webcam source: device %d (%dx%d @ %.1f fps)",
            device_index, self._info.width, self._info.height, self._info.fps,
        )

    @property
    def info(self) -> SourceInfo:
        return self._info

    def read(self) -> tuple[bool, np.ndarray]:
        ok, frame = self._cap.read()
        if not ok:
            return False, np.empty(0, dtype=np.uint8)
        return True, cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    def release(self) -> None:
        self._cap.release()
        logger.info("Released webcam source: device %d", self._device_index)


class RTSPSource(VideoSource):
    _INITIAL_BACKOFF: float = 1.0
    _BACKOFF_FACTOR: float = 2.0

    def __init__(self, url: str, max_retries: int = 5) -> None:
        self._url = url
        self._max_retries = max_retries
        self._cap = self._connect()
        raw_fps = self._cap.get(cv2.CAP_PROP_FPS)
        self._info = SourceInfo(
            fps=raw_fps if raw_fps > 0 else 25.0,
            width=int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            height=int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )
        logger.info(
            "Opened RTSP source: %s (%dx%d @ %.1f fps)",
            url, self._info.width, self._info.height, self._info.fps,
        )

    def _connect(self) -> cv2.VideoCapture:
        backoff = self._INITIAL_BACKOFF
        for attempt in range(1, self._max_retries + 1):
            cap = cv2.VideoCapture(self._url)
            if cap.isOpened():
                return cap
            cap.release()
            logger.warning(
                "RTSP connection attempt %d/%d failed for %s; retrying in %.1fs",
                attempt, self._max_retries, self._url, backoff,
            )
            time.sleep(backoff)
            backoff *= self._BACKOFF_FACTOR
        raise ConnectionError(
            f"Failed to connect to RTSP stream after {self._max_retries} attempts: {self._url}"
        )

    @property
    def info(self) -> SourceInfo:
        return self._info

    def read(self) -> tuple[bool, np.ndarray]:
        ok, frame = self._cap.read()
        if not ok:
            logger.warning("RTSP stream lost for %s; attempting reconnect", self._url)
            self._cap.release()
            try:
                self._cap = self._connect()
                ok, frame = self._cap.read()
            except ConnectionError:
                logger.error("Could not reconnect to RTSP stream: %s", self._url)
                return False, np.empty(0, dtype=np.uint8)
        if not ok:
            return False, np.empty(0, dtype=np.uint8)
        return True, cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    def release(self) -> None:
        self._cap.release()
        logger.info("Released RTSP source: %s", self._url)


def open_source(uri: str) -> VideoSource:
    """Route a URI string to the correct VideoSource subclass."""
    if uri.startswith(("rtsp://", "rtsps://")):
        return RTSPSource(uri)
    if uri.isdigit():
        return WebcamSource(int(uri))
    return FileSource(Path(uri))
