import logging
import queue
import threading

import numpy as np

from src.pipeline.sources import SourceInfo, VideoSource

logger = logging.getLogger(__name__)


class FrameReader:
    def __init__(self, source: VideoSource, maxsize: int = 4) -> None:
        self._source = source
        self._queue: queue.Queue[tuple[bool, np.ndarray]] = queue.Queue(maxsize=maxsize)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def info(self) -> SourceInfo:
        return self._source.info

    def start(self) -> "FrameReader":
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop, daemon=True, name="frame-reader"
        )
        self._thread.start()
        logger.info("Frame reader started (maxsize=%d)", self._queue.maxsize)
        return self

    def _capture_loop(self) -> None:
        while not self._stop_event.is_set():
            ok, frame = self._source.read()
            if not ok:
                logger.info("Source exhausted; stopping capture loop")
                self._queue.put((False, np.empty(0, dtype=np.uint8)))
                break
            if self._queue.full():
                try:
                    self._queue.get_nowait()
                    logger.debug("Queue full; dropped oldest frame")
                except queue.Empty:
                    pass
            self._queue.put((True, frame))

    def read(self, timeout: float = 1.0) -> tuple[bool, np.ndarray]:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            logger.warning("No frame available within %.1fs", timeout)
            return False, np.empty(0, dtype=np.uint8)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        logger.info("Frame reader stopped")

    def __enter__(self) -> "FrameReader":
        return self

    def __exit__(self, *args: object) -> None:
        self.stop()
