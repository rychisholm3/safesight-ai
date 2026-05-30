import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api import main as api_module
from src.api.main import app
from src.auth.dependencies import require_auth
from src.auth.models import Role, User
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
        severity="WARNING",
    )
    defaults.update(kwargs)
    return Event(**defaults)


def _fake_user() -> User:
    return User(
        user_id="test-user",
        org_id="test-org",
        email="test@example.com",
        hashed_password="hashed",
        role=Role.safety_officer,
        is_active=True,
        created_at="2024-01-01T00:00:00+00:00",
    )


@pytest.fixture(autouse=True)
def bypass_auth():
    """Override require_auth so tests don't need real JWTs."""
    app.dependency_overrides[require_auth] = _fake_user
    yield
    app.dependency_overrides.pop(require_auth, None)


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Replace the shared store with a fresh in-memory one for each test."""
    store = EventStore(db_path=tmp_path / "test.db", snapshot_dir=tmp_path / "snaps")
    monkeypatch.setattr(api_module, "_store", store)
    yield store
    store.close()
    monkeypatch.setattr(api_module, "_store", None)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def zones_file(tmp_path, monkeypatch):
    data = {
        "required_ppe": ["hardhat"],
        "zones": [{"id": "z1", "name": "Zone 1", "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]], "rule": "no_entry"}],
    }
    p = tmp_path / "zones.json"
    p.write_text(json.dumps(data))
    monkeypatch.setattr(api_module, "_ZONES_PATH", p)
    return data


class TestHealth:
    def test_returns_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


class TestZones:
    def test_returns_zones(self, client, zones_file):
        r = client.get("/zones")
        assert r.status_code == 200
        assert r.json()["required_ppe"] == ["hardhat"]
        assert len(r.json()["zones"]) == 1

    def test_404_when_missing(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(api_module, "_ZONES_PATH", tmp_path / "nonexistent.json")
        r = client.get("/zones")
        assert r.status_code == 404


class TestListEvents:
    def test_empty(self, client):
        r = client.get("/events")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_saved_events(self, client, isolated_store):
        isolated_store.save_event(make_event())
        r = client.get("/events")
        assert len(r.json()) == 1
        assert r.json()[0]["event_id"] == "evt1"

    def test_filter_by_event_type(self, client, isolated_store):
        isolated_store.save_event(make_event(event_id="a", event_type="missing_ppe"))
        isolated_store.save_event(make_event(event_id="b", event_type="zone_intrusion"))
        r = client.get("/events?event_type=zone_intrusion")
        assert len(r.json()) == 1
        assert r.json()[0]["event_id"] == "b"

    def test_limit_param(self, client, isolated_store):
        for i in range(5):
            isolated_store.save_event(make_event(event_id=str(i), track_id=i))
        r = client.get("/events?limit=2")
        assert len(r.json()) == 2

    def test_invalid_limit_rejected(self, client):
        assert client.get("/events?limit=0").status_code == 422

    def test_unauthenticated_returns_401(self, client):
        app.dependency_overrides.pop(require_auth, None)
        r = client.get("/events")
        assert r.status_code == 401
        app.dependency_overrides[require_auth] = _fake_user


class TestGetEvent:
    def test_returns_event(self, client, isolated_store):
        isolated_store.save_event(make_event())
        r = client.get("/events/evt1")
        assert r.status_code == 200
        assert r.json()["event_id"] == "evt1"

    def test_404_for_unknown(self, client):
        r = client.get("/events/doesnotexist")
        assert r.status_code == 404


class TestStats:
    def test_empty(self, client):
        r = client.get("/stats")
        assert r.status_code == 200
        assert r.json() == {"total": 0, "open": 0, "closed": 0, "by_type": {}}

    def test_counts_correctly(self, client, isolated_store):
        isolated_store.save_event(make_event(event_id="a", event_type="missing_ppe"))
        e = make_event(event_id="b", event_type="zone_intrusion", end_frame=50)
        isolated_store.save_event(e)
        r = client.get("/stats")
        data = r.json()
        assert data["total"] == 2
        assert data["open"] == 1
        assert data["closed"] == 1
        assert data["by_type"] == {"missing_ppe": 1, "zone_intrusion": 1}
