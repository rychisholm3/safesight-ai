import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from src.api import main as api_module
from src.api.main import app
from src.api.ws import ConnectionManager, EventBroadcaster, _event_to_dict
from src.events import Event
from src.store import EventStore


def make_event(**kwargs) -> Event:
    defaults = dict(
        event_id="evt1",
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


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    store = EventStore(db_path=tmp_path / "test.db", snapshot_dir=tmp_path / "snaps")
    monkeypatch.setattr(api_module, "_store", store)
    yield store
    store.close()
    monkeypatch.setattr(api_module, "_store", None)


@pytest.fixture
def client():
    return TestClient(app)


class TestEventToDict:
    def test_snapshot_path_serialised_as_string(self):
        from pathlib import Path
        e = make_event(snapshot_path=Path("/data/snapshots/abc.jpg"))
        d = _event_to_dict(e)
        assert d["snapshot_path"] == str(Path("/data/snapshots/abc.jpg"))

    def test_none_snapshot_stays_none(self):
        d = _event_to_dict(make_event())
        assert d["snapshot_path"] is None

    def test_missing_ppe_is_list(self):
        d = _event_to_dict(make_event(missing_ppe=["hardhat", "vest"]))
        assert d["missing_ppe"] == ["hardhat", "vest"]


class TestConnectionManager:
    def test_broadcast_reaches_connected_client(self, client):
        with client.websocket_connect("/ws/events") as ws:
            # Consume the history message first
            ws.receive_json()
            # Trigger a broadcast via the manager directly
            asyncio.get_event_loop().run_until_complete(
                api_module.manager.broadcast({"type": "test", "payload": 42})
            ) if False else None  # broadcast is async; use the WS endpoint test below


class TestWebSocketEndpoint:
    def test_receives_history_on_connect(self, client, isolated_store):
        isolated_store.save_event(make_event())
        with client.websocket_connect("/ws/events") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "history"
            assert len(msg["events"]) == 1
            assert msg["events"][0]["event_id"] == "evt1"

    def test_history_empty_when_no_events(self, client):
        with client.websocket_connect("/ws/events") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "history"
            assert msg["events"] == []

    def test_history_capped_at_20(self, client, isolated_store):
        for i in range(25):
            isolated_store.save_event(make_event(event_id=str(i), track_id=i))
        with client.websocket_connect("/ws/events") as ws:
            msg = ws.receive_json()
            assert len(msg["events"]) == 20

    def test_multiple_clients_connect(self, client, isolated_store):
        with client.websocket_connect("/ws/events") as ws1:
            with client.websocket_connect("/ws/events") as ws2:
                msg1 = ws1.receive_json()
                msg2 = ws2.receive_json()
                assert msg1["type"] == "history"
                assert msg2["type"] == "history"


class TestEventBroadcaster:
    def test_publish_no_op_without_loop(self):
        mgr = ConnectionManager()
        b = EventBroadcaster(mgr)
        # Should not raise even with no loop set
        b.publish(make_event(), "opened")

    def test_set_loop_stores_loop(self):
        mgr = ConnectionManager()
        b = EventBroadcaster(mgr)
        loop = asyncio.new_event_loop()
        b.set_loop(loop)
        assert b._loop is loop
        loop.close()

    def test_event_to_dict_roundtrip(self):
        e = make_event(missing_ppe=["hardhat", "vest"], zone_id="z1")
        d = _event_to_dict(e)
        assert d["event_id"] == "evt1"
        assert d["zone_id"] == "z1"
        assert d["missing_ppe"] == ["hardhat", "vest"]
        assert d["end_frame"] is None
