import asyncio
import json
import logging
from dataclasses import asdict
from pathlib import Path

from fastapi import WebSocket, WebSocketDisconnect

from src.pipeline.events import Event

logger = logging.getLogger(__name__)


def _event_to_dict(event: Event) -> dict:
    d = asdict(event)
    if d.get("snapshot_path") is not None:
        d["snapshot_path"] = str(d["snapshot_path"])
    return d


class ConnectionManager:
    """Tracks active WebSocket connections and fans messages out to all of them."""

    def __init__(self) -> None:
        self._queues: dict[WebSocket, asyncio.Queue] = {}

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._queues[ws] = asyncio.Queue()
        logger.info("WS client connected — total=%d", len(self._queues))

    def disconnect(self, ws: WebSocket) -> None:
        self._queues.pop(ws, None)
        logger.info("WS client disconnected — total=%d", len(self._queues))

    async def broadcast(self, message: dict) -> None:
        dead: list[WebSocket] = []
        for ws, q in self._queues.items():
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send_to(self, ws: WebSocket, message: dict) -> None:
        await ws.send_text(json.dumps(message))


class EventBroadcaster:
    """Thread-safe bridge between the pipeline thread and the asyncio event loop.

    The pipeline calls publish() from its thread; this schedules a coroutine
    on the running event loop so all WebSocket clients receive the message.
    An optional notification dispatcher is called for every opened event.
    """

    def __init__(self, manager: ConnectionManager) -> None:
        self._manager = manager
        self._loop: asyncio.AbstractEventLoop | None = None
        self._dispatcher = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def set_dispatcher(self, dispatcher) -> None:
        """Register a NotificationDispatcher; called from api/main.py at startup."""
        self._dispatcher = dispatcher

    def publish(self, event: Event, action: str) -> None:
        """Call from any thread. action is 'opened' or 'closed'."""
        if self._loop is None or not self._loop.is_running():
            logger.debug("EventBroadcaster: no running loop, dropping event")
            return
        message = {"type": "event", "action": action, "event": _event_to_dict(event)}
        asyncio.run_coroutine_threadsafe(self._manager.broadcast(message), self._loop)
        if action == "opened" and self._dispatcher is not None:
            self._dispatcher.dispatch(event)


# Module-level singletons — imported by main.py and by the pipeline.
manager = ConnectionManager()
broadcaster = EventBroadcaster(manager)


async def websocket_endpoint(ws: WebSocket, history: list[dict]) -> None:
    """Handle a single WebSocket connection lifecycle."""
    await manager.connect(ws)
    try:
        # Send recent event history so the dashboard has immediate context.
        await manager.send_to(ws, {"type": "history", "events": history})

        # Keep the connection alive; the client doesn't need to send anything,
        # but we receive to detect disconnection.
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WS error: %s", exc)
    finally:
        manager.disconnect(ws)
