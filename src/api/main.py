import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.ws import broadcaster, websocket_endpoint
from src.store import EventStore


@asynccontextmanager
async def _lifespan(app: FastAPI):
    broadcaster.set_loop(asyncio.get_running_loop())
    yield


app = FastAPI(title="SafeSight AI", version="0.1.0", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Config from environment (with sensible defaults)
# ---------------------------------------------------------------------------
_DB_PATH = Path(os.environ.get("SAFESIGHT_DB", "data/events.db"))
_SNAPSHOT_DIR = Path(os.environ.get("SAFESIGHT_SNAPSHOTS", "data/snapshots"))
_ZONES_PATH = Path(os.environ.get("SAFESIGHT_ZONES", "config/zones.json"))

# ---------------------------------------------------------------------------
# Static files — serve snapshot JPEGs at /snapshots/<filename>
# ---------------------------------------------------------------------------
_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/snapshots", StaticFiles(directory=str(_SNAPSHOT_DIR)), name="snapshots")

# ---------------------------------------------------------------------------
# Dependency — one shared EventStore for the lifetime of the process
# ---------------------------------------------------------------------------
_store: EventStore | None = None


def get_store() -> EventStore:
    global _store
    if _store is None:
        _store = EventStore(db_path=_DB_PATH, snapshot_dir=_SNAPSHOT_DIR)
    return _store


StoreDep = Annotated[EventStore, Depends(get_store)]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/zones")
def get_zones():
    if not _ZONES_PATH.exists():
        raise HTTPException(status_code=404, detail=f"zones file not found: {_ZONES_PATH}")
    return json.loads(_ZONES_PATH.read_text())


@app.put("/zones")
def put_zones(body: dict):
    _ZONES_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ZONES_PATH.write_text(json.dumps(body, indent=2))
    return body


@app.get("/events")
def list_events(
    store: StoreDep,
    event_type: str | None = Query(default=None, description="Filter by 'missing_ppe' or 'zone_intrusion'"),
    since: datetime | None = Query(default=None, description="ISO datetime — return events after this timestamp"),
    limit: int = Query(default=100, ge=1, le=1000),
):
    return store.get_events(event_type=event_type, since=since, limit=limit)


@app.get("/events/{event_id}")
def get_event(event_id: str, store: StoreDep):
    rows = store.get_events(limit=1000)
    match = next((r for r in rows if r["event_id"] == event_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id!r} not found")
    return match


@app.websocket("/ws/events")
async def ws_events(ws: WebSocket, store: StoreDep):
    history = store.get_events(limit=20)
    await websocket_endpoint(ws, history)


@app.get("/stats")
def get_stats(store: StoreDep):
    all_events = store.get_events(limit=10_000)
    total = len(all_events)
    by_type: dict[str, int] = {}
    open_count = 0
    for e in all_events:
        by_type[e["event_type"]] = by_type.get(e["event_type"], 0) + 1
        if e["end_frame"] is None:
            open_count += 1
    return {
        "total": total,
        "open": open_count,
        "closed": total - open_count,
        "by_type": by_type,
    }
