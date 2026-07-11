"""FastAPI backend: WebSocket streaming, diff, and rollback endpoints."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from helios.recorder import EventBus, Recorder
from helios.schemas import Event
from helios.snapshot import SnapshotManager

# ── App setup ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Helios",
    version="0.1.0",
    description="Watchdog + replay tool for AI coding agents.",
)

# Runtime state (singleton for this process)
_run_state: dict[str, Any] = {}


# ── WebSocket endpoint ────────────────────────────────────────────────────

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    bus: EventBus = _run_state.get("bus")
    if not bus:
        # No active run — send empty history
        await ws.send_json({"type": "info", "msg": "no active run"})
        return

    # Send existing events first
    for evt in bus.history():
        await ws.send_json(evt.serialise())

    # Stream new events
    queue: asyncio.Queue[Event] = asyncio.Queue()

    def _forward(evt: Event):
        try:
            queue.put_nowait(evt)
        except asyncio.QueueFull:
            pass

    bus.subscribe(_forward)
    try:
        while True:
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=1.0)
                await ws.send_json(evt.serialise())
            except asyncio.TimeoutError:
                continue
    except WebSocketDisconnect:
        bus._on_event.remove(_forward)


# ── Diff endpoint ─────────────────────────────────────────────────────────

@app.get("/diff")
async def get_diff(path: str = "."):
    """Return git diff for *path* (relative to repo root)."""
    snap: SnapshotManager | None = _run_state.get("snapshot_manager")
    if not snap:
        return {"error": "no active snapshot"}
    try:
        diff_text = snap.diff(path)
        return {"path": path, "diff": diff_text}
    except Exception as e:
        return {"error": str(e)}


# ── Rollback endpoint ─────────────────────────────────────────────────────

@app.post("/rollback")
async def post_rollback(tag: str):
    """Roll back to snapshot *tag*. Returns new HEAD short hash."""
    snap: SnapshotManager | None = _run_state.get("snapshot_manager")
    if not snap:
        return {"error": "no active snapshot manager"}
    try:
        new_hash = snap.rollback(tag)
        return {"status": "ok", "head": new_hash}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── Info endpoint ─────────────────────────────────────────────────────────

@app.get("/info")
async def get_info():
    """Current run metadata."""
    snap: SnapshotManager | None = _run_state.get("snapshot_manager")
    return {
        "active": snap is not None,
        "tag": snap.root.as_posix() if snap else None,
    }


# ── Serve frontend (dev mode mounts web/ directly) ─────────────────────────

def mount_frontend(app: FastAPI, web_dir: Path) -> None:
    """Mount web/ dir for dev, or serve built SPA in production."""
    if (web_dir / "dist").exists():
        app.mount("/", StaticFiles(directory=str(web_dir / "dist"), html=True), name="frontend")
    elif (web_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="frontend")


# ── Standalone startup ────────────────────────────────────────────────────

def create_app(cwd: Path, bus: EventBus, snapshot_manager: SnapshotManager) -> FastAPI:
    """Build the app with injected dependencies (for programmatic use)."""
    _run_state["bus"] = bus
    _run_state["snapshot_manager"] = snapshot_manager
    mount_frontend(app, cwd / "web")
    return app