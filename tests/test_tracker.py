from unittest.mock import MagicMock, patch

import numpy as np
import supervision as sv
import pytest

from src.detector import Detection
from src.tracker import TrackedObject, Tracker

FRAME_ID = 10


def det(x1=0, y1=0, x2=100, y2=200, class_name="person", conf=0.9) -> Detection:
    return Detection(bbox=(x1, y1, x2, y2), class_name=class_name, confidence=conf, frame_id=FRAME_ID)


def tracked_sv(rows: list[tuple]) -> sv.Detections:
    """Build a sv.Detections with tracker_id set. rows: (x1,y1,x2,y2, cls_id, conf, track_id)"""
    if not rows:
        return sv.Detections.empty()
    arr = np.array(rows, dtype=float)
    return sv.Detections(
        xyxy=arr[:, :4],
        confidence=arr[:, 5],
        class_id=arr[:, 4].astype(int),
        tracker_id=arr[:, 6].astype(int),
    )


@pytest.fixture
def mock_bytetrack():
    with patch("src.tracker.ByteTrackTracker") as mock_cls:
        yield mock_cls


class TestTrackedObject:
    def test_fields_stored_correctly(self) -> None:
        obj = TrackedObject(track_id=7, bbox=(10, 20, 100, 200), class_name="person", confidence=0.9, frame_id=5)
        assert obj.track_id == 7
        assert obj.bbox == (10, 20, 100, 200)
        assert obj.class_name == "person"
        assert obj.confidence == 0.9
        assert obj.frame_id == 5


class TestTracker:
    def test_empty_detections_returns_empty_list(self, mock_bytetrack: MagicMock) -> None:
        mock_bytetrack.return_value.update.return_value = tracked_sv([])
        assert Tracker().update([], frame_id=0) == []

    def test_empty_detections_still_advances_tracker(self, mock_bytetrack: MagicMock) -> None:
        mock_bytetrack.return_value.update.return_value = tracked_sv([])
        Tracker().update([], frame_id=0)
        mock_bytetrack.return_value.update.assert_called_once()

    def test_confirmed_track_returned(self, mock_bytetrack: MagicMock) -> None:
        mock_bytetrack.return_value.update.return_value = tracked_sv(
            [(0.0, 0.0, 100.0, 200.0, 0, 0.9, 1)]
        )
        tracker = Tracker()
        tracker._class_id("person")  # register so reverse lookup works
        result = tracker.update([det()], frame_id=FRAME_ID)
        assert len(result) == 1
        assert result[0].track_id == 1

    def test_unconfirmed_track_filtered_out(self, mock_bytetrack: MagicMock) -> None:
        mock_bytetrack.return_value.update.return_value = tracked_sv(
            [(0.0, 0.0, 100.0, 200.0, 0, 0.9, -1)]
        )
        tracker = Tracker()
        tracker._class_id("person")
        result = tracker.update([det()], frame_id=FRAME_ID)
        assert result == []

    def test_frame_id_stamped_on_output(self, mock_bytetrack: MagicMock) -> None:
        mock_bytetrack.return_value.update.return_value = tracked_sv(
            [(0.0, 0.0, 50.0, 50.0, 0, 0.8, 3)]
        )
        tracker = Tracker()
        tracker._class_id("person")
        result = tracker.update([det()], frame_id=42)
        assert result[0].frame_id == 42

    def test_class_name_preserved_through_id_mapping(self, mock_bytetrack: MagicMock) -> None:
        mock_bytetrack.return_value.update.return_value = tracked_sv(
            [(0.0, 0.0, 50.0, 50.0, 0, 0.85, 2)]
        )
        tracker = Tracker()
        result = tracker.update([det(class_name="hardhat")], frame_id=FRAME_ID)
        assert result[0].class_name == "hardhat"

    def test_multiple_tracks_returned(self, mock_bytetrack: MagicMock) -> None:
        mock_bytetrack.return_value.update.return_value = tracked_sv([
            (0.0,   0.0,  50.0,  50.0, 0, 0.9, 1),
            (100.0, 0.0, 200.0, 150.0, 1, 0.8, 2),
        ])
        tracker = Tracker()
        tracker._class_id("person")
        tracker._class_id("hardhat")
        result = tracker.update([det(), det(class_name="hardhat")], frame_id=FRAME_ID)
        assert len(result) == 2
        assert {r.track_id for r in result} == {1, 2}

    def test_bbox_coords_are_ints(self, mock_bytetrack: MagicMock) -> None:
        mock_bytetrack.return_value.update.return_value = tracked_sv(
            [(10.7, 20.3, 100.9, 200.1, 0, 0.8, 5)]
        )
        tracker = Tracker()
        tracker._class_id("person")
        obj = tracker.update([det()], frame_id=FRAME_ID)[0]
        assert all(isinstance(v, int) for v in obj.bbox)

    def test_confidence_is_float(self, mock_bytetrack: MagicMock) -> None:
        mock_bytetrack.return_value.update.return_value = tracked_sv(
            [(0.0, 0.0, 50.0, 50.0, 0, 0.75, 4)]
        )
        tracker = Tracker()
        tracker._class_id("person")
        obj = tracker.update([det()], frame_id=FRAME_ID)[0]
        assert isinstance(obj.confidence, float)
        assert abs(obj.confidence - 0.75) < 1e-6

    def test_reset_clears_class_registry(self, mock_bytetrack: MagicMock) -> None:
        tracker = Tracker()
        tracker._class_id("person")
        tracker._class_id("hardhat")
        tracker.reset()
        assert tracker._class_name_to_id == {}
        assert tracker._id_to_class_name == {}

    def test_reset_calls_bytetrack_reset(self, mock_bytetrack: MagicMock) -> None:
        tracker = Tracker()
        tracker.reset()
        mock_bytetrack.return_value.reset.assert_called_once()

    def test_track_activation_threshold_forwarded(self, mock_bytetrack: MagicMock) -> None:
        Tracker(track_activation_threshold=0.3)
        _, kwargs = mock_bytetrack.call_args
        assert kwargs["track_activation_threshold"] == 0.3

    def test_minimum_consecutive_frames_forwarded(self, mock_bytetrack: MagicMock) -> None:
        Tracker(minimum_consecutive_frames=3)
        _, kwargs = mock_bytetrack.call_args
        assert kwargs["minimum_consecutive_frames"] == 3

    def test_lost_track_buffer_computed_from_seconds_and_fps(self, mock_bytetrack: MagicMock) -> None:
        Tracker(frame_rate=10.0, lost_track_seconds=3.0)
        _, kwargs = mock_bytetrack.call_args
        assert kwargs["lost_track_buffer"] == 30  # 3.0s * 10fps

    def test_lost_track_buffer_minimum_is_one(self, mock_bytetrack: MagicMock) -> None:
        Tracker(frame_rate=30.0, lost_track_seconds=0.0)
        _, kwargs = mock_bytetrack.call_args
        assert kwargs["lost_track_buffer"] == 1

    def test_defaults_stable_across_frame_rates(self, mock_bytetrack: MagicMock) -> None:
        Tracker(frame_rate=5.0)
        _, kwargs5 = mock_bytetrack.call_args
        Tracker(frame_rate=30.0)
        _, kwargs30 = mock_bytetrack.call_args
        # 2s default: 10 frames at 5fps, 60 frames at 30fps
        assert kwargs5["lost_track_buffer"] == 10
        assert kwargs30["lost_track_buffer"] == 60
        assert kwargs5["minimum_consecutive_frames"] == 2
        assert kwargs5["track_activation_threshold"] == 0.5

    def test_class_registry_stable_across_frames(self, mock_bytetrack: MagicMock) -> None:
        mock_bytetrack.return_value.update.return_value = tracked_sv([
            (0.0, 0.0, 50.0, 50.0, 0, 0.9, 1)
        ])
        tracker = Tracker()
        # First call registers "person" as id 0
        tracker.update([det(class_name="person")], frame_id=0)
        # Second call: id 0 must still map to "person"
        result = tracker.update([det(class_name="person")], frame_id=1)
        assert result[0].class_name == "person"
