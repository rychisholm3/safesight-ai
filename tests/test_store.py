import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pytest

from src.events import Event
from src.store import EventStore


def make_event(**kwargs) -> Event:
    defaults = dict(
        event_id="abc123",
        event_type="missing_ppe",
        track_id=1,
        zone_id=None,
        missing_ppe=["hardhat"],
        start_frame=0,
        end_frame=None,
        snapshot_path=None,
    )
    defaults.update(kwargs)
    return Event(**defaults)


@pytest.fixture
def store(tmp_path):
    s = EventStore(db_path=tmp_path / "events.db", snapshot_dir=tmp_path / "snapshots")
    yield s
    s.close()


class TestSaveEvent:
    def test_inserts_row(self, store, tmp_path):
        event = make_event()
        store.save_event(event)
        rows = store.get_events()
        assert len(rows) == 1
        assert rows[0]["event_id"] == "abc123"
        assert rows[0]["event_type"] == "missing_ppe"
        assert rows[0]["track_id"] == 1
        assert rows[0]["end_frame"] is None

    def test_missing_ppe_roundtrips_as_list(self, store):
        store.save_event(make_event(missing_ppe=["hardhat", "vest"]))
        rows = store.get_events()
        assert rows[0]["missing_ppe"] == ["hardhat", "vest"]

    def test_upsert_does_not_duplicate(self, store):
        event = make_event()
        store.save_event(event)
        store.save_event(event)
        assert len(store.get_events()) == 1

    def test_upsert_updates_end_frame(self, store):
        event = make_event()
        store.save_event(event)
        event.end_frame = 99
        store.save_event(event)
        rows = store.get_events()
        assert rows[0]["end_frame"] == 99

    def test_writes_snapshot_jpeg(self, store, tmp_path):
        event = make_event()
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        store.save_event(event, frame=frame)
        assert event.snapshot_path is not None
        assert event.snapshot_path.exists()
        rows = store.get_events()
        assert rows[0]["snapshot_path"] is not None

    def test_does_not_overwrite_existing_snapshot(self, store, tmp_path):
        existing = tmp_path / "snapshots" / "existing.jpg"
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_bytes(b"fake")
        event = make_event(snapshot_path=existing)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        store.save_event(event, frame=frame)
        # snapshot_path unchanged, original bytes preserved
        assert event.snapshot_path == existing
        assert existing.read_bytes() == b"fake"

    def test_no_frame_leaves_snapshot_null(self, store):
        store.save_event(make_event())
        rows = store.get_events()
        assert rows[0]["snapshot_path"] is None


class TestCloseEvent:
    def test_updates_end_frame(self, store):
        event = make_event()
        store.save_event(event)
        event.end_frame = 42
        store.close_event(event)
        rows = store.get_events()
        assert rows[0]["end_frame"] == 42

    def test_no_op_for_unknown_event(self, store):
        event = make_event(event_id="nonexistent")
        event.end_frame = 1
        store.close_event(event)  # should not raise
        assert store.get_events() == []


class TestGetEvents:
    def test_returns_newest_first(self, store):
        store.save_event(make_event(event_id="a", track_id=1))
        store.save_event(make_event(event_id="b", track_id=2))
        rows = store.get_events()
        assert rows[0]["event_id"] == "b"
        assert rows[1]["event_id"] == "a"

    def test_filter_by_event_type(self, store):
        store.save_event(make_event(event_id="a", event_type="missing_ppe"))
        store.save_event(make_event(event_id="b", event_type="zone_intrusion"))
        rows = store.get_events(event_type="zone_intrusion")
        assert len(rows) == 1
        assert rows[0]["event_id"] == "b"

    def test_filter_by_since(self, store):
        store.save_event(make_event(event_id="a"))
        cutoff = datetime.now(timezone.utc)
        store.save_event(make_event(event_id="b", track_id=2))
        rows = store.get_events(since=cutoff)
        assert len(rows) == 1
        assert rows[0]["event_id"] == "b"

    def test_limit(self, store):
        for i in range(5):
            store.save_event(make_event(event_id=str(i), track_id=i))
        rows = store.get_events(limit=3)
        assert len(rows) == 3

    def test_empty_returns_empty_list(self, store):
        assert store.get_events() == []


class TestContextManager:
    def test_usable_as_context_manager(self, tmp_path):
        with EventStore(tmp_path / "e.db", tmp_path / "snaps") as store:
            store.save_event(make_event())
            assert len(store.get_events()) == 1
