import cv2
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.sources import FileSource, WebcamSource, RTSPSource, SourceInfo, open_source


# A BGR frame with red=255 (channel 2 in BGR). After BGR→RGB it becomes channel 0=255.
BGR_FRAME = np.zeros((480, 640, 3), dtype=np.uint8)
BGR_FRAME[:, :, 2] = 255


def make_cap(*, opens: bool = True, fps: float = 30.0, width: int = 640, height: int = 480) -> MagicMock:
    cap = MagicMock()
    cap.isOpened.return_value = opens
    cap.get.side_effect = lambda prop: {
        cv2.CAP_PROP_FPS: fps,
        cv2.CAP_PROP_FRAME_WIDTH: float(width),
        cv2.CAP_PROP_FRAME_HEIGHT: float(height),
    }.get(prop, 0.0)
    cap.read.return_value = (True, BGR_FRAME.copy())
    return cap


# ── SourceInfo ────────────────────────────────────────────────────────────────

def test_source_info_fields() -> None:
    info = SourceInfo(fps=25.0, width=1920, height=1080)
    assert info.fps == 25.0
    assert info.width == 1920
    assert info.height == 1080


# ── FileSource ────────────────────────────────────────────────────────────────

class TestFileSource:
    @patch("src.sources.cv2.VideoCapture")
    def test_info_populated(self, mock_vc: MagicMock) -> None:
        mock_vc.return_value = make_cap(fps=25.0, width=1920, height=1080)
        with FileSource(Path("video.mp4")) as src:
            assert src.info == SourceInfo(fps=25.0, width=1920, height=1080)

    @patch("src.sources.cv2.VideoCapture")
    def test_read_returns_rgb(self, mock_vc: MagicMock) -> None:
        mock_vc.return_value = make_cap()
        with FileSource(Path("video.mp4")) as src:
            ok, frame = src.read()
        assert ok
        assert frame[0, 0, 0] == 255  # red channel in RGB
        assert frame[0, 0, 2] == 0    # blue channel in RGB

    @patch("src.sources.cv2.VideoCapture")
    def test_eof_returns_false(self, mock_vc: MagicMock) -> None:
        cap = make_cap()
        cap.read.return_value = (False, np.empty(0))
        mock_vc.return_value = cap
        with FileSource(Path("video.mp4")) as src:
            ok, _ = src.read()
        assert not ok

    @patch("src.sources.cv2.VideoCapture")
    def test_loop_resets_at_eof(self, mock_vc: MagicMock) -> None:
        cap = make_cap()
        cap.read.side_effect = [(False, np.empty(0)), (True, BGR_FRAME.copy())]
        mock_vc.return_value = cap
        with FileSource(Path("video.mp4"), loop=True) as src:
            ok, _ = src.read()
        assert ok
        cap.set.assert_called_once_with(cv2.CAP_PROP_POS_FRAMES, 0)

    @patch("src.sources.cv2.VideoCapture")
    def test_raises_on_missing_file(self, mock_vc: MagicMock) -> None:
        mock_vc.return_value = make_cap(opens=False)
        with pytest.raises(FileNotFoundError):
            FileSource(Path("missing.mp4"))

    @patch("src.sources.cv2.VideoCapture")
    def test_context_manager_releases(self, mock_vc: MagicMock) -> None:
        cap = make_cap()
        mock_vc.return_value = cap
        with FileSource(Path("video.mp4")):
            pass
        cap.release.assert_called()


# ── WebcamSource ──────────────────────────────────────────────────────────────

class TestWebcamSource:
    @patch("src.sources.cv2.VideoCapture")
    def test_info_populated(self, mock_vc: MagicMock) -> None:
        mock_vc.return_value = make_cap(fps=30.0, width=640, height=480)
        with WebcamSource(device_index=0) as src:
            assert src.info == SourceInfo(fps=30.0, width=640, height=480)

    @patch("src.sources.cv2.VideoCapture")
    def test_read_returns_rgb(self, mock_vc: MagicMock) -> None:
        mock_vc.return_value = make_cap()
        with WebcamSource() as src:
            ok, frame = src.read()
        assert ok
        assert frame[0, 0, 0] == 255
        assert frame[0, 0, 2] == 0

    @patch("src.sources.cv2.VideoCapture")
    def test_raises_on_no_device(self, mock_vc: MagicMock) -> None:
        mock_vc.return_value = make_cap(opens=False)
        with pytest.raises(RuntimeError):
            WebcamSource(device_index=99)

    @patch("src.sources.cv2.VideoCapture")
    def test_zero_fps_defaults_to_30(self, mock_vc: MagicMock) -> None:
        mock_vc.return_value = make_cap(fps=0.0)
        with WebcamSource() as src:
            assert src.info.fps == 30.0

    @patch("src.sources.cv2.VideoCapture")
    def test_context_manager_releases(self, mock_vc: MagicMock) -> None:
        cap = make_cap()
        mock_vc.return_value = cap
        with WebcamSource():
            pass
        cap.release.assert_called()


# ── RTSPSource ────────────────────────────────────────────────────────────────

class TestRTSPSource:
    @patch("src.sources.time.sleep")
    @patch("src.sources.cv2.VideoCapture")
    def test_connects_successfully(self, mock_vc: MagicMock, mock_sleep: MagicMock) -> None:
        mock_vc.return_value = make_cap(fps=25.0, width=1280, height=720)
        with RTSPSource("rtsp://cam/stream") as src:
            assert src.info == SourceInfo(fps=25.0, width=1280, height=720)
        mock_sleep.assert_not_called()

    @patch("src.sources.time.sleep")
    @patch("src.sources.cv2.VideoCapture")
    def test_retries_on_initial_failure(self, mock_vc: MagicMock, mock_sleep: MagicMock) -> None:
        mock_vc.side_effect = [make_cap(opens=False), make_cap()]
        with RTSPSource("rtsp://cam/stream", max_retries=2) as src:
            assert src.info.fps == 30.0
        mock_sleep.assert_called_once()

    @patch("src.sources.time.sleep")
    @patch("src.sources.cv2.VideoCapture")
    def test_raises_after_max_retries(self, mock_vc: MagicMock, mock_sleep: MagicMock) -> None:
        mock_vc.return_value = make_cap(opens=False)
        with pytest.raises(ConnectionError):
            RTSPSource("rtsp://cam/stream", max_retries=2)
        assert mock_sleep.call_count == 2

    @patch("src.sources.time.sleep")
    @patch("src.sources.cv2.VideoCapture")
    def test_reconnects_on_stream_loss(self, mock_vc: MagicMock, mock_sleep: MagicMock) -> None:
        cap1 = make_cap()
        cap1.read.return_value = (False, np.empty(0))
        cap2 = make_cap()
        cap2.read.return_value = (True, BGR_FRAME.copy())
        mock_vc.side_effect = [cap1, cap2]
        with RTSPSource("rtsp://cam/stream", max_retries=1) as src:
            ok, frame = src.read()
        assert ok
        assert frame.shape == (480, 640, 3)

    @patch("src.sources.time.sleep")
    @patch("src.sources.cv2.VideoCapture")
    def test_context_manager_releases(self, mock_vc: MagicMock, mock_sleep: MagicMock) -> None:
        cap = make_cap()
        mock_vc.return_value = cap
        with RTSPSource("rtsp://cam/stream"):
            pass
        cap.release.assert_called()


# ── open_source factory ───────────────────────────────────────────────────────

class TestOpenSource:
    @patch("src.sources.cv2.VideoCapture")
    def test_rtsp_uri(self, mock_vc: MagicMock) -> None:
        mock_vc.return_value = make_cap()
        assert isinstance(open_source("rtsp://192.168.1.1/stream"), RTSPSource)

    @patch("src.sources.cv2.VideoCapture")
    def test_rtsps_uri(self, mock_vc: MagicMock) -> None:
        mock_vc.return_value = make_cap()
        assert isinstance(open_source("rtsps://192.168.1.1/stream"), RTSPSource)

    @patch("src.sources.cv2.VideoCapture")
    def test_digit_opens_webcam(self, mock_vc: MagicMock) -> None:
        mock_vc.return_value = make_cap()
        assert isinstance(open_source("0"), WebcamSource)

    @patch("src.sources.cv2.VideoCapture")
    def test_file_path(self, mock_vc: MagicMock) -> None:
        mock_vc.return_value = make_cap()
        assert isinstance(open_source("data/input_videos/sample.mp4"), FileSource)
