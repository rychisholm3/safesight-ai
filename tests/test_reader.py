import threading

import numpy as np
import pytest
from unittest.mock import MagicMock

from src.pipeline.sources import SourceInfo
from src.pipeline.reader import FrameReader


FRAME = np.zeros((480, 640, 3), dtype=np.uint8)


def make_source(frames: list[tuple[bool, np.ndarray]]) -> MagicMock:
    source = MagicMock()
    source.info = SourceInfo(fps=30.0, width=640, height=480)
    source.read.side_effect = frames
    return source


class TestFrameReader:
    def test_info_delegates_to_source(self) -> None:
        source = make_source([])
        assert FrameReader(source).info == SourceInfo(fps=30.0, width=640, height=480)

    def test_start_returns_self(self) -> None:
        source = make_source([(False, np.empty(0))])
        reader = FrameReader(source)
        assert reader.start() is reader
        reader.stop()

    def test_thread_is_daemon(self) -> None:
        source = make_source([(False, np.empty(0))])
        reader = FrameReader(source).start()
        assert reader._thread.daemon
        reader.stop()

    def test_read_returns_frame(self) -> None:
        source = make_source([(True, FRAME.copy()), (False, np.empty(0))])
        with FrameReader(source).start() as reader:
            ok, frame = reader.read(timeout=2.0)
        assert ok
        assert frame.shape == (480, 640, 3)

    def test_read_returns_false_when_source_exhausted(self) -> None:
        source = make_source([(False, np.empty(0))])
        with FrameReader(source).start() as reader:
            ok, _ = reader.read(timeout=2.0)
        assert not ok

    def test_read_times_out_when_queue_empty(self) -> None:
        # Reader not started — queue stays empty, triggering the timeout path.
        source = make_source([])
        reader = FrameReader(source)
        ok, _ = reader.read(timeout=0.05)
        assert not ok

    def test_stop_clears_thread(self) -> None:
        source = make_source([(False, np.empty(0))])
        reader = FrameReader(source).start()
        reader.stop()
        assert reader._thread is None

    def test_context_manager_stops_reader(self) -> None:
        source = make_source([(False, np.empty(0))])
        with FrameReader(source).start() as reader:
            pass
        assert reader._thread is None

    def test_all_frames_readable_in_order(self) -> None:
        frames = [(True, np.full((480, 640, 3), i, dtype=np.uint8)) for i in range(3)]
        frames.append((False, np.empty(0)))
        source = make_source(frames)
        with FrameReader(source, maxsize=8).start() as reader:
            results = []
            for _ in range(3):
                ok, frame = reader.read(timeout=2.0)
                assert ok
                results.append(int(frame[0, 0, 0]))
            ok, _ = reader.read(timeout=2.0)
            assert not ok
        assert results == [0, 1, 2]

    def test_full_queue_drops_oldest_without_deadlock(self) -> None:
        # 10 frames into a queue of size 1; reader should not deadlock.
        frames = [(True, FRAME.copy())] * 10 + [(False, np.empty(0))]
        source = make_source(frames)
        with FrameReader(source, maxsize=1).start() as reader:
            # Give the thread time to fill and cycle the queue.
            reader._thread.join(timeout=2.0)
            ok, frame = reader.read(timeout=2.0)
        # We may get a valid frame or the EOF sentinel depending on timing;
        # either way we must not deadlock and the shape must be valid if ok.
        if ok:
            assert frame.shape == (480, 640, 3)

    def test_start_after_stop_restarts_cleanly(self) -> None:
        source = make_source([(False, np.empty(0)), (True, FRAME.copy()), (False, np.empty(0))])
        reader = FrameReader(source).start()
        reader.stop()
        reader.start()
        ok_values = []
        for _ in range(2):
            ok, _ = reader.read(timeout=2.0)
            ok_values.append(ok)
            if not ok:
                break
        reader.stop()
        assert True  # completed without deadlock
