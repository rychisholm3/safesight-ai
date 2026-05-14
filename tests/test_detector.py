from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.detector import Detection, Detector

FRAME = np.zeros((480, 640, 3), dtype=np.uint8)
NAMES = {0: "person", 1: "hardhat", 2: "vest"}


def make_mock_result(rows: list[tuple[float, float, float, float, int, float]]) -> MagicMock:
    """Build a mock ultralytics Results object. rows: (x1, y1, x2, y2, cls_id, conf)"""
    result = MagicMock()
    result.names = NAMES
    boxes = MagicMock()
    boxes.__len__.return_value = len(rows)
    if rows:
        arr = np.array(rows, dtype=float)
        boxes.xyxy.cpu.return_value.numpy.return_value = arr[:, :4]
        boxes.cls.cpu.return_value.numpy.return_value.astype.return_value = arr[:, 4].astype(int)
        boxes.conf.cpu.return_value.numpy.return_value = arr[:, 5]
    result.boxes = boxes
    return result


@pytest.fixture
def mock_yolo():
    with patch("src.detector.YOLO") as mock_cls:
        yield mock_cls


class TestDetection:
    def test_fields_stored_correctly(self) -> None:
        d = Detection(bbox=(10, 20, 100, 200), class_name="person", confidence=0.9, frame_id=3)
        assert d.bbox == (10, 20, 100, 200)
        assert d.class_name == "person"
        assert d.confidence == 0.9
        assert d.frame_id == 3


class TestDetector:
    def test_model_loaded_on_init(self, mock_yolo: MagicMock) -> None:
        Detector("yolo26n.pt")
        mock_yolo.assert_called_once_with("yolo26n.pt")

    def test_accepts_path_object(self, mock_yolo: MagicMock) -> None:
        Detector(Path("models/yolo26n.pt"))
        mock_yolo.assert_called_once_with("models/yolo26n.pt")

    def test_detect_no_boxes_returns_empty_list(self, mock_yolo: MagicMock) -> None:
        mock_yolo.return_value.return_value = [make_mock_result([])]
        assert Detector().detect(FRAME, frame_id=0) == []

    def test_detect_single_detection_fields(self, mock_yolo: MagicMock) -> None:
        mock_yolo.return_value.return_value = [
            make_mock_result([(10.0, 20.0, 100.0, 200.0, 0, 0.85)])
        ]
        detections = Detector().detect(FRAME, frame_id=5)
        assert len(detections) == 1
        det = detections[0]
        assert det.bbox == (10, 20, 100, 200)
        assert det.class_name == "person"
        assert abs(det.confidence - 0.85) < 1e-6
        assert det.frame_id == 5

    def test_frame_id_stamped_on_all_detections(self, mock_yolo: MagicMock) -> None:
        rows = [(0.0, 0.0, 50.0, 50.0, 0, 0.9), (60.0, 60.0, 110.0, 110.0, 1, 0.8)]
        mock_yolo.return_value.return_value = [make_mock_result(rows)]
        detections = Detector().detect(FRAME, frame_id=42)
        assert all(d.frame_id == 42 for d in detections)

    def test_detect_multiple_detections(self, mock_yolo: MagicMock) -> None:
        rows = [
            (0.0, 0.0, 50.0, 50.0, 0, 0.9),
            (100.0, 100.0, 200.0, 200.0, 1, 0.75),
            (300.0, 300.0, 400.0, 400.0, 2, 0.6),
        ]
        mock_yolo.return_value.return_value = [make_mock_result(rows)]
        detections = Detector().detect(FRAME, frame_id=0)
        assert len(detections) == 3
        assert {d.class_name for d in detections} == {"person", "hardhat", "vest"}

    def test_bbox_coords_are_ints(self, mock_yolo: MagicMock) -> None:
        mock_yolo.return_value.return_value = [
            make_mock_result([(10.7, 20.3, 100.9, 200.1, 0, 0.8)])
        ]
        det = Detector().detect(FRAME, frame_id=0)[0]
        assert all(isinstance(v, int) for v in det.bbox)

    def test_confidence_threshold_forwarded_to_model(self, mock_yolo: MagicMock) -> None:
        mock_yolo.return_value.return_value = [make_mock_result([])]
        Detector(confidence=0.7).detect(FRAME, frame_id=0)
        mock_yolo.return_value.assert_called_once_with(FRAME, conf=0.7, verbose=False)
