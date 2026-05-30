"""
Auth-specific database operations.

Uses the same SQLite connection strategy as EventStore — a single
connection shared across threads with check_same_thread=False.
In Phase 11 this will be swapped for asyncpg.
"""
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.auth.models import Organization, Role, Site, User, create_auth_tables
from src.auth.security import hash_password


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuthDB:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row
        create_auth_tables(self._conn)

    # ── Organizations ────────────────────────────────────────────────────────

    def create_org(self, name: str) -> Organization:
        org_id = uuid.uuid4().hex
        self._conn.execute(
            "INSERT INTO organizations (org_id, name, created_at) VALUES (?, ?, ?)",
            (org_id, name, _now()),
        )
        self._conn.commit()
        return Organization(org_id=org_id, name=name, created_at=_now())

    def get_org(self, org_id: str) -> Organization | None:
        row = self._conn.execute(
            "SELECT * FROM organizations WHERE org_id = ?", (org_id,)
        ).fetchone()
        return Organization(**dict(row)) if row else None

    def list_orgs(self) -> list[Organization]:
        rows = self._conn.execute("SELECT * FROM organizations ORDER BY name").fetchall()
        return [Organization(**dict(r)) for r in rows]

    # ── Sites ────────────────────────────────────────────────────────────────

    def create_site(
        self, org_id: str, name: str,
        timezone: str = "UTC", rtsp_url: str | None = None,
    ) -> Site:
        site_id = uuid.uuid4().hex
        self._conn.execute(
            "INSERT INTO sites (site_id, org_id, name, timezone, rtsp_url, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (site_id, org_id, name, timezone, rtsp_url, _now()),
        )
        self._conn.commit()
        return Site(site_id=site_id, org_id=org_id, name=name,
                    timezone=timezone, rtsp_url=rtsp_url, created_at=_now())

    def list_sites(self, org_id: str) -> list[Site]:
        rows = self._conn.execute(
            "SELECT * FROM sites WHERE org_id = ? ORDER BY name", (org_id,)
        ).fetchall()
        return [Site(**dict(r)) for r in rows]

    def get_site(self, site_id: str) -> Site | None:
        row = self._conn.execute(
            "SELECT * FROM sites WHERE site_id = ?", (site_id,)
        ).fetchone()
        return Site(**dict(row)) if row else None

    # ── Users ────────────────────────────────────────────────────────────────

    def create_user(
        self, org_id: str, email: str, plain_password: str, role: Role,
    ) -> User:
        user_id = uuid.uuid4().hex
        hashed = hash_password(plain_password)
        self._conn.execute(
            "INSERT INTO users "
            "(user_id, org_id, email, hashed_password, role, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, 1, ?)",
            (user_id, org_id, email, hashed, role.value, _now()),
        )
        self._conn.commit()
        return User(
            user_id=user_id, org_id=org_id, email=email,
            hashed_password=hashed, role=role, is_active=True, created_at=_now(),
        )

    def get_user_by_email(self, email: str) -> User | None:
        row = self._conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        return _row_to_user(row) if row else None

    def get_user_by_id(self, user_id: str) -> User | None:
        row = self._conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return _row_to_user(row) if row else None

    def list_users(self, org_id: str) -> list[User]:
        rows = self._conn.execute(
            "SELECT * FROM users WHERE org_id = ? ORDER BY email", (org_id,)
        ).fetchall()
        return [_row_to_user(r) for r in rows]


def _row_to_user(row: sqlite3.Row) -> User:
    d = dict(row)
    d["role"] = Role(d["role"])
    d["is_active"] = bool(d["is_active"])
    return User(**d)
