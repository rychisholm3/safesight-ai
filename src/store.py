import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from src.events import Event

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    event_id      TEXT PRIMARY KEY,
    event_type    TEXT NOT NULL,
    track_id      INTEGER NOT NULL,
    zone_id       TEXT,
    missing_ppe   TEXT NOT NULL DEFAULT '[]',
    severity      TEXT NOT NULL DEFAULT 'WARNING',
    start_frame   INTEGER NOT NULL,
    end_frame     INTEGER,
    snapshot_path TEXT,
    created_at    TEXT NOT NULL,
    zone_rule     TEXT,
    osha_codes    TEXT NOT NULL DEFAULT '[]',
    fine_min_usd  INTEGER NOT NULL DEFAULT 0,
    fine_max_usd  INTEGER NOT NULL DEFAULT 0
)
"""

_MIGRATE_ADD_SEVERITY = """
ALTER TABLE events ADD COLUMN severity TEXT NOT NULL DEFAULT 'WARNING'
"""

_MIGRATIONS: list[tuple[str, str]] = [
    ("severity",     "ALTER TABLE events ADD COLUMN severity TEXT NOT NULL DEFAULT 'WARNING'"),
    ("zone_rule",    "ALTER TABLE events ADD COLUMN zone_rule TEXT"),
    ("osha_codes",   "ALTER TABLE events ADD COLUMN osha_codes TEXT NOT NULL DEFAULT '[]'"),
    ("fine_min_usd", "ALTER TABLE events ADD COLUMN fine_min_usd INTEGER NOT NULL DEFAULT 0"),
    ("fine_max_usd", "ALTER TABLE events ADD COLUMN fine_max_usd INTEGER NOT NULL DEFAULT 0"),
    ("confidence",   "ALTER TABLE events ADD COLUMN confidence REAL NOT NULL DEFAULT 0.0"),
    ("bbox",               "ALTER TABLE events ADD COLUMN bbox TEXT"),
    ("person_detections",  "ALTER TABLE events ADD COLUMN person_detections TEXT"),
]


class EventStore:
    def __init__(self, db_path: Path, snapshot_dir: Path) -> None:
        self._snapshot_dir = snapshot_dir
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()
        self._migrate()
        logger.info("EventStore ready: db=%s snapshots=%s", db_path, snapshot_dir)

    def _migrate(self) -> None:
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(events)")}
        for col_name, sql in _MIGRATIONS:
            if col_name not in cols:
                self._conn.execute(sql)
                self._conn.commit()
                logger.info("DB migrated: added %s column", col_name)

    def save_event(self, event: Event, frame: np.ndarray | None = None) -> None:
        """Insert or update the event row. Writes a snapshot JPEG if frame is provided."""
        if frame is not None and event.snapshot_path is None:
            snap_path = self._snapshot_dir / f"{event.event_id}.jpg"
            cv2.imwrite(str(snap_path), frame)
            event.snapshot_path = snap_path
            logger.debug("Snapshot written: %s", snap_path)

        bbox_json  = json.dumps(list(event.bbox)) if event.bbox is not None else None
        dets_json  = json.dumps(event.person_detections) if event.person_detections else None
        self._conn.execute(
            """
            INSERT INTO events
                (event_id, event_type, track_id, zone_id, missing_ppe,
                 severity, start_frame, end_frame, snapshot_path, created_at,
                 zone_rule, osha_codes, fine_min_usd, fine_max_usd, confidence,
                 bbox, person_detections)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                end_frame     = excluded.end_frame,
                snapshot_path = excluded.snapshot_path
            """,
            (
                event.event_id,
                event.event_type,
                event.track_id,
                event.zone_id,
                json.dumps(event.missing_ppe),
                event.severity,
                event.start_frame,
                event.end_frame,
                str(event.snapshot_path) if event.snapshot_path else None,
                datetime.now(timezone.utc).isoformat(),
                event.zone_rule,
                json.dumps(event.osha_codes),
                event.fine_min_usd,
                event.fine_max_usd,
                event.confidence,
                bbox_json,
                dets_json,
            ),
        )
        self._conn.commit()

    def close_event(self, event: Event) -> None:
        """Update end_frame for an already-stored event."""
        cursor = self._conn.execute(
            "UPDATE events SET end_frame = ? WHERE event_id = ?",
            (event.end_frame, event.event_id),
        )
        self._conn.commit()
        if cursor.rowcount == 0:
            logger.warning(
                "close_event called for unknown event_id=%s — save_event first",
                event.event_id,
            )

    def get_events(
        self,
        event_type: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Return stored events as dicts, newest first."""
        clauses: list[str] = []
        params: list[object] = []

        if event_type is not None:
            clauses.append("event_type = ?")
            params.append(event_type)
        if since is not None:
            clauses.append("created_at >= ?")
            params.append(since.isoformat())

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)

        rows = self._conn.execute(
            f"SELECT * FROM events {where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()

        return [
            {
                **dict(row),
                "missing_ppe": json.loads(row["missing_ppe"]),
                "osha_codes":  json.loads(row["osha_codes"]) if row["osha_codes"] else [],
                "bbox":               json.loads(row["bbox"]) if row["bbox"] else None,
                "person_detections":  json.loads(row["person_detections"]) if row["person_detections"] else [],
            }
            for row in rows
        ]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "EventStore":
        return self

    def __exit__(self, *_) -> None:
        self.close()
