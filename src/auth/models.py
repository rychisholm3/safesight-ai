"""
Database schema and Python models for auth.

Tables
------
organizations  – top-level tenant (a company)
sites          – one physical location belonging to an org
users          – a person who can log in; belongs to one org
"""
import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Role(str, Enum):
    safety_officer = "safety_officer"
    site_manager   = "site_manager"
    executive      = "executive"
    auditor        = "auditor"


@dataclass
class Organization:
    org_id:     str
    name:       str
    created_at: str


@dataclass
class Site:
    site_id:    str
    org_id:     str
    name:       str
    timezone:   str
    rtsp_url:   str | None
    created_at: str


@dataclass
class User:
    user_id:       str
    org_id:        str
    email:         str
    hashed_password: str
    role:          Role
    is_active:     bool
    created_at:    str


_DDL = """
CREATE TABLE IF NOT EXISTS organizations (
    org_id     TEXT PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sites (
    site_id    TEXT PRIMARY KEY,
    org_id     TEXT NOT NULL REFERENCES organizations(org_id),
    name       TEXT NOT NULL,
    timezone   TEXT NOT NULL DEFAULT 'UTC',
    rtsp_url   TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    user_id          TEXT PRIMARY KEY,
    org_id           TEXT NOT NULL REFERENCES organizations(org_id),
    email            TEXT NOT NULL UNIQUE,
    hashed_password  TEXT NOT NULL,
    role             TEXT NOT NULL DEFAULT 'safety_officer',
    is_active        INTEGER NOT NULL DEFAULT 1,
    created_at       TEXT NOT NULL
);
"""


def create_auth_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(_DDL)
    conn.commit()
