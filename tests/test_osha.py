"""Tests for the OSHA rule engine (Phase 4)."""

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.auth.dependencies import require_auth
from src.auth.models import Role, User
from src.osha.matcher import fine_range, match_violation
from src.osha.rules import OSHA_DB


# ── Auth fixtures ─────────────────────────────────────────────────────────────

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


@pytest.fixture()
def client():
    """Unauthenticated test client — for testing 401 responses."""
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture()
def auth_client():
    """Test client with auth bypassed."""
    app.dependency_overrides[require_auth] = _fake_user
    c = TestClient(app, raise_server_exceptions=True)
    yield c
    app.dependency_overrides.pop(require_auth, None)


# ── Database integrity ────────────────────────────────────────────────────────

def test_db_not_empty():
    assert len(OSHA_DB) >= 8


def test_all_codes_have_required_fields():
    for key, code in OSHA_DB.items():
        assert code.code,        f"{key}: code is empty"
        assert code.title,       f"{key}: title is empty"
        assert code.description, f"{key}: description is empty"
        assert code.corrective_actions, f"{key}: no corrective actions"
        assert code.plain_english,      f"{key}: plain_english is empty"
        assert code.fine_min_usd >= 0,  f"{key}: negative fine min"
        assert code.fine_max_usd >= code.fine_min_usd, f"{key}: fine_max < fine_min"
        assert code.willful_max_usd >= code.fine_max_usd, f"{key}: willful_max < fine_max"


# ── Matcher: missing_ppe violations ──────────────────────────────────────────

def test_missing_hardhat_returns_head_protection_code():
    codes = match_violation("missing_ppe", missing_ppe=["hardhat"])
    code_strs = [c.code for c in codes]
    assert any("1926.100" in c for c in code_strs)


def test_missing_vest_returns_ppe_code():
    codes = match_violation("missing_ppe", missing_ppe=["vest"])
    code_strs = [c.code for c in codes]
    assert any("1926.28" in c or "1926.95" in c for c in code_strs)


def test_missing_mask_returns_respiratory_code():
    codes = match_violation("missing_ppe", missing_ppe=["mask"])
    code_strs = [c.code for c in codes]
    assert any("1910.134" in c for c in code_strs)


def test_missing_gloves_returns_hand_protection_code():
    codes = match_violation("missing_ppe", missing_ppe=["gloves"])
    code_strs = [c.code for c in codes]
    assert any("1910.138" in c for c in code_strs)


def test_multiple_missing_ppe_deduplicates():
    codes = match_violation("missing_ppe", missing_ppe=["hardhat", "vest"])
    seen = [c.code for c in codes]
    assert len(seen) == len(set(seen)), "Duplicate OSHA codes returned"


def test_missing_ppe_no_items_returns_generic_codes():
    codes = match_violation("missing_ppe", missing_ppe=[])
    assert len(codes) >= 1


def test_unknown_ppe_item_falls_back_to_generic():
    codes = match_violation("missing_ppe", missing_ppe=["face_shield"])
    assert len(codes) >= 1


# ── Matcher: zone_intrusion violations ───────────────────────────────────────

def test_no_entry_zone_returns_signage_code():
    codes = match_violation("zone_intrusion", zone_rule="no_entry")
    code_strs = [c.code for c in codes]
    assert any("1926.200" in c for c in code_strs)


def test_require_ppe_zone_returns_ppe_code():
    codes = match_violation("zone_intrusion", zone_rule="require_ppe")
    code_strs = [c.code for c in codes]
    assert any("1926.95" in c or "1926.21" in c for c in code_strs)


def test_zone_intrusion_no_rule_returns_codes():
    codes = match_violation("zone_intrusion")
    assert len(codes) >= 1


# ── Matcher: unknown event type ───────────────────────────────────────────────

def test_unknown_event_type_returns_general_duty():
    codes = match_violation("some_future_violation_type")
    assert any("5(a)(1)" in c.code for c in codes)


# ── Fine range helper ─────────────────────────────────────────────────────────

def test_fine_range_empty_list():
    assert fine_range([]) == (0, 0)


def test_fine_range_single_code():
    code = OSHA_DB["1926.100(a)"]
    lo, hi = fine_range([code])
    assert lo == code.fine_min_usd
    assert hi == code.fine_max_usd


def test_fine_range_multiple_takes_maximum():
    codes = match_violation("missing_ppe", missing_ppe=["hardhat", "vest"])
    lo, hi = fine_range(codes)
    assert hi >= lo > 0


# ── API smoke tests ───────────────────────────────────────────────────────────

def test_osha_lookup_missing_ppe(auth_client):
    resp = auth_client.get("/osha/lookup?event_type=missing_ppe&missing_ppe=hardhat")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert "code" in data[0]
    assert "corrective_actions" in data[0]
    assert "fine_min_usd" in data[0]
    assert "plain_english" in data[0]


def test_osha_lookup_zone_intrusion(auth_client):
    resp = auth_client.get("/osha/lookup?event_type=zone_intrusion&zone_rule=no_entry")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any("1926.200" in d["code"] for d in data)


def test_osha_lookup_multiple_ppe(auth_client):
    resp = auth_client.get("/osha/lookup?event_type=missing_ppe&missing_ppe=hardhat,vest")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2


def test_osha_codes_endpoint_returns_full_db(auth_client):
    resp = auth_client.get("/osha/codes")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 8
    for item in data:
        assert "code" in item
        assert "title" in item
        assert "corrective_actions" in item


def test_osha_lookup_requires_auth(client):
    resp = client.get("/osha/lookup?event_type=missing_ppe&missing_ppe=hardhat")
    assert resp.status_code == 401


def test_osha_codes_requires_auth(client):
    resp = client.get("/osha/codes")
    assert resp.status_code == 401
