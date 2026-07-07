"""Tests for auth endpoints and security utilities."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from src.api.main import app, auth_db as _real_auth_db
from src.auth.db import AuthDB
from src.auth.models import Role
from src.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from src.auth import router as auth_router_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    db = AuthDB(conn)
    yield db
    conn.close()


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient with an isolated in-memory AuthDB."""
    import src.api.main as api_module
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    db = AuthDB(conn)
    monkeypatch.setattr(api_module, "auth_db", db)
    # Make the auth router use the same isolated db
    def _get_isolated_db():
        return db
    app.dependency_overrides[auth_router_module._get_auth_db] = _get_isolated_db
    yield TestClient(app)
    app.dependency_overrides.pop(auth_router_module._get_auth_db, None)
    conn.close()


# ---------------------------------------------------------------------------
# Security utilities
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    def test_hash_is_not_plaintext(self):
        assert hash_password("secret") != "secret"

    def test_verify_correct(self):
        h = hash_password("mypassword")
        assert verify_password("mypassword", h)

    def test_verify_wrong(self):
        h = hash_password("mypassword")
        assert not verify_password("wrong", h)


class TestJWT:
    def test_access_token_roundtrip(self):
        token = create_access_token("uid1", "safety_officer", "org1")
        payload = decode_access_token(token)
        assert payload["sub"] == "uid1"
        assert payload["role"] == "safety_officer"
        assert payload["org_id"] == "org1"

    def test_refresh_token_roundtrip(self):
        token = create_refresh_token("uid1")
        uid = decode_refresh_token(token)
        assert uid == "uid1"

    def test_access_token_rejected_as_refresh(self):
        from jose import JWTError
        token = create_access_token("uid1", "safety_officer", "org1")
        with pytest.raises(JWTError):
            decode_refresh_token(token)

    def test_refresh_token_rejected_as_access(self):
        from jose import JWTError
        token = create_refresh_token("uid1")
        with pytest.raises(JWTError):
            decode_access_token(token)


# ---------------------------------------------------------------------------
# AuthDB
# ---------------------------------------------------------------------------

class TestAuthDB:
    def test_create_org(self, mem_db):
        org = mem_db.create_org("Acme Corp")
        assert org.name == "Acme Corp"
        assert len(org.org_id) == 32

    def test_create_user(self, mem_db):
        org = mem_db.create_org("Acme")
        user = mem_db.create_user(org.org_id, "a@b.com", "password123", Role.safety_officer)
        assert user.email == "a@b.com"
        assert user.role == Role.safety_officer
        assert user.hashed_password != "password123"

    def test_get_user_by_email(self, mem_db):
        org = mem_db.create_org("Acme")
        mem_db.create_user(org.org_id, "a@b.com", "pass1234", Role.auditor)
        user = mem_db.get_user_by_email("a@b.com")
        assert user is not None
        assert user.role == Role.auditor

    def test_get_user_by_email_missing(self, mem_db):
        assert mem_db.get_user_by_email("nobody@example.com") is None

    def test_create_site(self, mem_db):
        org = mem_db.create_org("Acme")
        site = mem_db.create_site(org.org_id, "Warehouse A", timezone="America/New_York")
        assert site.name == "Warehouse A"
        assert site.timezone == "America/New_York"

    def test_list_sites(self, mem_db):
        org = mem_db.create_org("Acme")
        mem_db.create_site(org.org_id, "Site A")
        mem_db.create_site(org.org_id, "Site B")
        sites = mem_db.list_sites(org.org_id)
        assert len(sites) == 2

    def test_list_users(self, mem_db):
        org = mem_db.create_org("Acme")
        mem_db.create_user(org.org_id, "a@b.com", "pass1234", Role.safety_officer)
        mem_db.create_user(org.org_id, "c@d.com", "pass5678", Role.auditor)
        assert len(mem_db.list_users(org.org_id)) == 2


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

class TestRegister:
    def test_creates_org_and_user(self, client):
        r = client.post("/auth/register", json={
            "org_name": "Acme Corp",
            "email": "admin@acme.com",
            "password": "securepass",
        })
        assert r.status_code == 201
        data = r.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_duplicate_email_returns_409(self, client):
        body = {"org_name": "Acme", "email": "a@b.com", "password": "securepass"}
        client.post("/auth/register", json=body)
        r = client.post("/auth/register", json={**body, "org_name": "Other"})
        assert r.status_code == 409

    def test_short_password_rejected(self, client):
        r = client.post("/auth/register", json={
            "org_name": "X", "email": "a@b.com", "password": "short",
        })
        assert r.status_code == 422

    def test_invalid_email_rejected(self, client):
        r = client.post("/auth/register", json={
            "org_name": "X", "email": "notanemail", "password": "securepass",
        })
        assert r.status_code == 422


class TestLogin:
    def _register(self, client):
        client.post("/auth/register", json={
            "org_name": "Acme", "email": "a@b.com", "password": "securepass",
        })

    def test_returns_tokens(self, client):
        self._register(client)
        r = client.post("/auth/login", json={"email": "a@b.com", "password": "securepass"})
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_wrong_password_returns_401(self, client):
        self._register(client)
        r = client.post("/auth/login", json={"email": "a@b.com", "password": "wrong"})
        assert r.status_code == 401

    def test_unknown_email_returns_401(self, client):
        r = client.post("/auth/login", json={"email": "nobody@x.com", "password": "pass"})
        assert r.status_code == 401


class TestGuest:
    def test_returns_tokens(self, client):
        r = client.post("/auth/guest")
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_token_authenticates_and_reads_as_auditor(self, client):
        tokens = client.post("/auth/guest").json()
        r = client.get("/auth/me", headers={
            "Authorization": f"Bearer {tokens['access_token']}",
        })
        assert r.status_code == 200
        assert r.json()["role"] == "auditor"
        assert r.json()["email"] == "guest@safesight.demo"

    def test_reuses_same_account_across_calls(self, client):
        first = client.post("/auth/guest").json()
        second = client.post("/auth/guest").json()
        me1 = client.get("/auth/me", headers={
            "Authorization": f"Bearer {first['access_token']}",
        }).json()
        me2 = client.get("/auth/me", headers={
            "Authorization": f"Bearer {second['access_token']}",
        }).json()
        assert me1["user_id"] == me2["user_id"]


class TestRefresh:
    def test_returns_new_access_token(self, client):
        r = client.post("/auth/register", json={
            "org_name": "Acme", "email": "a@b.com", "password": "securepass",
        })
        refresh = r.json()["refresh_token"]
        r2 = client.post("/auth/refresh", json={"refresh_token": refresh})
        assert r2.status_code == 200
        assert "access_token" in r2.json()

    def test_invalid_refresh_token_returns_401(self, client):
        r = client.post("/auth/refresh", json={"refresh_token": "garbage"})
        assert r.status_code == 401


class TestMe:
    def test_returns_user_info(self, client):
        r = client.post("/auth/register", json={
            "org_name": "Acme", "email": "a@b.com", "password": "securepass",
        })
        token = r.json()["access_token"]
        r2 = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code == 200
        assert r2.json()["email"] == "a@b.com"
        assert r2.json()["role"] == "safety_officer"

    def test_no_token_returns_401(self, client):
        r = client.get("/auth/me")
        assert r.status_code == 401

    def test_invalid_token_returns_401(self, client):
        r = client.get("/auth/me", headers={"Authorization": "Bearer garbage"})
        assert r.status_code == 401
