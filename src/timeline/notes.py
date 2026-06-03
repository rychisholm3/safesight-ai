"""
Supervisor intervention notes — stored per event in a dedicated SQLite table.

Notes give safety officers a way to record what action was taken in response
to a violation or near-miss, creating a complete audit trail per incident.
"""
import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_CREATE = """
CREATE TABLE IF NOT EXISTS supervisor_notes (
    note_id    TEXT PRIMARY KEY,
    event_id   TEXT NOT NULL,
    user_id    TEXT NOT NULL,
    note       TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""
_IDX = "CREATE INDEX IF NOT EXISTS idx_notes_event ON supervisor_notes(event_id)"


@dataclass
class SupervisorNote:
    note_id:    str
    event_id:   str
    user_id:    str
    note:       str
    created_at: str


class NotesDB:
    """Lightweight wrapper around the supervisor_notes table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        conn.row_factory = sqlite3.Row
        conn.execute(_CREATE)
        conn.execute(_IDX)
        conn.commit()
        logger.info("NotesDB ready")

    def add_note(self, event_id: str, user_id: str, note: str) -> SupervisorNote:
        note_id    = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO supervisor_notes (note_id, event_id, user_id, note, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (note_id, event_id, user_id, note, created_at),
        )
        self._conn.commit()
        logger.debug("Note added: event=%s user=%s", event_id, user_id)
        return SupervisorNote(
            note_id=note_id, event_id=event_id,
            user_id=user_id, note=note, created_at=created_at,
        )

    def get_notes(self, event_id: str) -> list[SupervisorNote]:
        rows = self._conn.execute(
            "SELECT * FROM supervisor_notes WHERE event_id = ? ORDER BY created_at ASC",
            (event_id,),
        ).fetchall()
        return [SupervisorNote(**dict(r)) for r in rows]

    def get_notes_bulk(self, event_ids: list[str]) -> dict[str, list[SupervisorNote]]:
        """Fetch notes for multiple events in one query."""
        if not event_ids:
            return {}
        placeholders = ",".join("?" * len(event_ids))
        rows = self._conn.execute(
            f"SELECT * FROM supervisor_notes "
            f"WHERE event_id IN ({placeholders}) ORDER BY created_at ASC",
            event_ids,
        ).fetchall()
        result: dict[str, list[SupervisorNote]] = {eid: [] for eid in event_ids}
        for r in rows:
            n = SupervisorNote(**dict(r))
            result[n.event_id].append(n)
        return result

    def delete_note(self, note_id: str) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM supervisor_notes WHERE note_id = ?", (note_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0
