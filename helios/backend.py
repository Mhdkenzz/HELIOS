"""
Helios Backend — FastAPI server with WebSocket streaming, diff, and rollback.
"""

from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.middleware.cors import CORSMiddleware

from . import version
from .recorder import EventBus
from .schemas import Event
from .snapshot import SnapshotManager, TAG_RE


# ── Frontend embedding helpers ────────────────────────────────────────────────


def _find_web_dist() -> Path | None:
    """Try to locate the bundled web UI."""
    here = Path(__file__).resolve().parent
    candidates = [here / "web", here.parent / "web"]
    for d in candidates:
        if d.is_dir() and (d / "index.html").exists():
            return d
    return None


def _fallback_html() -> str:
    return (
        "<!DOCTYPE html><html><head><title>Helios</title></head>"
        '<body style="font-family:sans-serif;display:flex;align-items:center;'
        'justify-content:center;height:100vh;margin:0;background:#0f172a;'
        'color:#e2e8f0"><div style="text-align:center"><h1>Helios</h1>'
        "<p>Run <code>npm run build</code> in <code>web/</code>.</p>"
        "</div></body></html>"
    )


# ── Cached rollback permission & path-traversal check ────────────────────────


def _normalize_pattern(s: str) -> str:
    return re.sub(r"[*?[\]]+", "?", s)


def _path_is_safe(root: Path, requested: str) -> bool:
    """Return True if the requested path is within the project root."""
    if ".." in requested:
        return False
    resolved = (root / requested).resolve()
    return str(resolved).startswith(str(root.resolve()))


# ── App factory ──────────────────────────────────────────────────────────────


def create_app(
    root: Path,
    bus: EventBus,
    snap: SnapshotManager | None = None,
    config: dict[str, Any] | None = None,
) -> FastAPI:
    config = config or {}
    rollback_token = config.get("rollback_token", "")

    # Shared event queue for WebSocket consumers
    _subscribers: list[asyncio.Queue[Event]] = []
    _sub_lock = asyncio.Lock()

    # Stored loop reference — avoids calling get_event_loop() from a worker
    # thread (deprecated in 3.10, crash in 3.14+).
    _loop: asyncio.AbstractEventLoop | None = None

    def _broadcast(event: Event) -> None:
        """Push event to all subscriber queues (called from sync bus callback)."""
        loop = _loop
        if loop is None or loop.is_closed():
            return
        for q in _subscribers:
            try:
                loop.call_soon_threadsafe(q.put_nowait, event)
            except Exception:
                pass

    # Subscribe the broadcaster to the event bus
    bus.subscribe(_broadcast)

    @asynccontextmanager
    async def _lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        nonlocal _loop
        _loop = asyncio.get_running_loop()
        yield

    app = FastAPI(
        title="Helios",
        docs_url="/docs" if not rollback_token else None,
        redoc_url="/redoc" if not rollback_token else None,
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── WebSocket ──────────────────────────────────────────────────────────

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        q: asyncio.Queue[Event] = asyncio.Queue()
        async with _sub_lock:
            _subscribers.append(q)

        # Send full history on connect
        history = bus.history()
        if history:
            await ws.send_json({"events": [e.to_dict() for e in history]})
        try:
            while True:
                evt = await asyncio.wait_for(q.get(), timeout=1.0)
                await ws.send_json(evt.to_dict())
        except (asyncio.TimeoutError, WebSocketDisconnect):
            async with _sub_lock:
                _subscribers.remove(q)

    # ── Diff endpoint (with path-traversal guard) ──────────────────────────

    @app.get("/diff")
    async def get_diff(path: str = ".") -> JSONResponse:
        if snap is None:
            return JSONResponse({"error": "no snapshot manager"})

        # Security: reject path traversal
        if not _path_is_safe(root, path):
            return JSONResponse({"error": "path outside project root"}, status_code=403)

        resolved = (root / path).resolve()
        rel = resolved.relative_to(root) if resolved != root else Path(".")
        try:
            diff_text = snap.diff(str(rel))
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

        return JSONResponse({"diff": diff_text})

    # ── Rollback endpoint (with token auth) ────────────────────────────────

    @app.post("/rollback")
    async def post_rollback(request: Request, tag: str = "") -> JSONResponse:
        if snap is None:
            return JSONResponse({"error": "no snapshot manager"}, status_code=500)

        # Auth: check header token
        provided = request.headers.get("X-Rollback-Token", "")
        if rollback_token and provided != rollback_token:
            return JSONResponse(
                {"status": "error", "message": "unauthorized"},
                status_code=401,
            )

        if not tag:
            return JSONResponse(
                {"status": "error", "message": "tag is required"},
                status_code=400,
            )

        # Sanity: tag format
        if not TAG_RE.match(tag):
            return JSONResponse(
                {"status": "error", "message": "invalid tag format"},
                status_code=400,
            )

        try:
            snap.rollback(tag)
        except Exception as exc:
            return JSONResponse(
                {"status": "error", "message": str(exc)},
                status_code=500,
            )

        return JSONResponse({"status": "ok", "message": f"rolled back to {tag}"})

    # ── Info endpoint ──────────────────────────────────────────────────────

    @app.get("/info")
    async def get_info() -> JSONResponse:
        return JSONResponse({"app": "helios", "version": version()})

    # ── Embedded frontend ──────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def serve_frontend() -> HTMLResponse:
        web_dir = _find_web_dist()
        if web_dir and (web_dir / "index.html").exists():
            return HTMLResponse(content=(web_dir / "index.html").read_text())
        return HTMLResponse(content=_fallback_html())

    @app.get("/{path:path}", response_class=Response)
    async def serve_static(path: str) -> Response:
        web_dir = _find_web_dist()
        if web_dir:
            target = web_dir / path
            if target.is_file():
                return HTMLResponse(content=target.read_bytes())
        return JSONResponse({"error": "not found"}, status_code=404)

    return app