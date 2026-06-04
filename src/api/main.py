import asyncio
import json
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
load_dotenv()  # loads .env from the project root before anything else reads os.environ

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.cameras import router as cameras_router
from src.rootcause.router import (
    _get_conn as _rootcause_get_conn,
    router as rootcause_router,
)
from src.timeline.compliance import ComplianceEngine
from src.timeline.notes import NotesDB
from src.timeline.router import (
    _get_store      as _timeline_get_store,
    _get_notes_db   as _timeline_get_notes_db,
    _get_compliance as _timeline_get_compliance,
    router as timeline_router,
)
from src.evidence.router import (
    _get_event_store  as _evidence_get_event_store,
    _get_snapshot_dir as _evidence_get_snapshot_dir,
    router as evidence_router,
)
from src.copilot.router import (
    _get_event_store as _copilot_get_event_store,
    _get_risk_engine as _copilot_get_risk_engine,
    _get_zones_path  as _copilot_get_zones_path,
    router as copilot_router,
)
from src.osha.router import router as osha_router
from src.api.ws import broadcaster, websocket_endpoint
from src.auth.db import AuthDB
from src.auth.dependencies import require_auth
from src.auth.models import User
from src.auth.router import router as auth_router
from src.notifications.channels.email_channel import EmailConfig
from src.notifications.channels.sms_channel import TwilioConfig
from src.notifications.db import NotificationDB
from src.notifications.dispatcher import NotificationDispatcher
from src.notifications.router import _get_notification_db
from src.notifications.router import router as notifications_router
from src.risk.engine import RiskEngine
from src.risk.router import _get_risk_engine
from src.risk.router import router as risk_router
from src.store import EventStore


@asynccontextmanager
async def _lifespan(app: FastAPI):
    broadcaster.set_loop(asyncio.get_running_loop())
    broadcaster.set_dispatcher(_notification_dispatcher)
    yield


app = FastAPI(title="SafeSight AI", version="0.2.0", lifespan=_lifespan)

_cors_origins = os.environ.get("SAFESIGHT_CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------
_DB_PATH      = Path(os.environ.get("SAFESIGHT_DB",        "data/events.db"))
_SNAPSHOT_DIR = Path(os.environ.get("SAFESIGHT_SNAPSHOTS", "data/snapshots"))
_ZONES_PATH   = Path(os.environ.get("SAFESIGHT_ZONES",     "config/zones.json"))

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/snapshots", StaticFiles(directory=str(_SNAPSHOT_DIR)), name="snapshots")

# ---------------------------------------------------------------------------
# Shared singletons — one connection, one store, one auth_db
# ---------------------------------------------------------------------------
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
_shared_conn: sqlite3.Connection = sqlite3.connect(
    str(_DB_PATH), check_same_thread=False
)
_shared_conn.row_factory = sqlite3.Row

_store: EventStore           = EventStore(db_path=_DB_PATH, snapshot_dir=_SNAPSHOT_DIR)
auth_db: AuthDB              = AuthDB(_shared_conn)
notification_db: NotificationDB = NotificationDB(_shared_conn)
risk_engine: RiskEngine      = RiskEngine(_shared_conn)
notes_db: NotesDB            = NotesDB(_shared_conn)
compliance_engine: ComplianceEngine = ComplianceEngine(_shared_conn)

_notification_dispatcher = NotificationDispatcher(
    notification_db  = notification_db,
    auth_db          = auth_db,
    email_config     = EmailConfig.from_env(),
    twilio_config    = TwilioConfig.from_env(),
)


def get_store() -> EventStore:
    return _store


def _get_notification_db_impl() -> NotificationDB:
    return notification_db


def _get_risk_engine_impl() -> RiskEngine:
    return risk_engine


StoreDep = Annotated[EventStore, Depends(get_store)]

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth_router)
app.include_router(notifications_router)
app.include_router(risk_router)
app.include_router(cameras_router)
app.include_router(osha_router)
app.include_router(evidence_router)
app.include_router(copilot_router)
app.include_router(timeline_router)
app.include_router(rootcause_router)
app.dependency_overrides[_get_notification_db]     = _get_notification_db_impl
app.dependency_overrides[_get_risk_engine]         = _get_risk_engine_impl
app.dependency_overrides[_evidence_get_event_store]  = get_store
app.dependency_overrides[_rootcause_get_conn]        = lambda: _shared_conn
app.dependency_overrides[_timeline_get_store]        = get_store
app.dependency_overrides[_timeline_get_notes_db]     = lambda: notes_db
app.dependency_overrides[_timeline_get_compliance]   = lambda: compliance_engine
app.dependency_overrides[_evidence_get_snapshot_dir] = lambda: _SNAPSHOT_DIR
app.dependency_overrides[_copilot_get_event_store]   = get_store
app.dependency_overrides[_copilot_get_risk_engine] = _get_risk_engine_impl
app.dependency_overrides[_copilot_get_zones_path]  = lambda: _ZONES_PATH


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/zones")
def get_zones(_: User = Depends(require_auth)):
    if not _ZONES_PATH.exists():
        raise HTTPException(status_code=404, detail=f"zones file not found: {_ZONES_PATH}")
    return json.loads(_ZONES_PATH.read_text())


@app.put("/zones")
def put_zones(body: dict, _: User = Depends(require_auth)):
    _ZONES_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ZONES_PATH.write_text(json.dumps(body, indent=2))
    return body


@app.get("/events")
def list_events(
    store: StoreDep,
    _: User = Depends(require_auth),
    event_type: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
):
    return store.get_events(event_type=event_type, since=since, limit=limit)


@app.get("/events/{event_id}")
def get_event(event_id: str, store: StoreDep, _: User = Depends(require_auth)):
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
def get_stats(store: StoreDep, _: User = Depends(require_auth)):
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


@app.get("/orgs/sites")
def list_sites(current_user: User = Depends(require_auth)):
    sites = auth_db.list_sites(current_user.org_id)
    return [{"site_id": s.site_id, "name": s.name, "timezone": s.timezone,
             "rtsp_url": s.rtsp_url} for s in sites]
