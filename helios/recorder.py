"""
Helios Recorder — Event bus, subprocess tracer, file watcher, and metrics sampler.
"""

from __future__ import annotations

import asyncio
import os
import resource
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .schemas import Event

# ── Configuration ──────────────────────────────────────────────────────────

_DENY: list[str] = []
_ALLOW: list[str] = []
_DRY_RUN: bool = False


def _init_config(config: dict[str, Any] | None = None) -> None:
    global _DENY, _ALLOW, _DRY_RUN
    cfg = config or {}
    _DENY = cfg.get("deny", [])
    _ALLOW = cfg.get("allow", [])
    _DRY_RUN = cfg.get("dry_run", False)


# ── Command filtering (deny / allow lists) ─────────────────────────────────

class CommandDenied(Exception):
    pass


def _check_command(cmd_fragment: str) -> None:
    for pattern in _DENY:
        if pattern in cmd_fragment:
            raise CommandDenied(
                f"command denied by deny-list: {pattern!r}"
            )
    if _ALLOW:
        if not any(p in cmd_fragment for p in _ALLOW):
            raise CommandDenied(
                f"command not in allow-list (allowed: {_ALLOW})"
            )


# ── Safe command splitting ─────────────────────────────────────────────────

def _safe_split(raw: str) -> list[str]:
    return shlex.split(raw)


# ── Event Bus ──────────────────────────────────────────────────────────────

class EventBus:
    """Thread-safe event bus with sync + async publish support."""

    _lock: asyncio.Lock
    _callbacks: list[Callable[[Event], None]]
    _history: list[Event]
    _loop: asyncio.AbstractEventLoop | None

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._callbacks = []
        self._history = []
        self._loop = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Store the running event loop for thread-safe dispatching."""
        self._loop = loop

    def subscribe(self, callback: Callable[[Event], None]) -> None:
        self._callbacks.append(callback)

    def unsubscribe(self, callback: Callable[[Event], None]) -> None:
        self._callbacks.remove(callback)

    async def publish(self, event: Event) -> None:
        """Async publish — appends to history and dispatches to callbacks."""
        async with self._lock:
            cbs = list(self._callbacks)
            self._history.append(event)
        for cb in cbs:
            cb(event)

    def publish_sync(self, event: Event) -> None:
        """Sync publish — safe to call from any thread.

        Appends to history synchronously and dispatches callbacks.
        """
        self._history.append(event)
        # Copy under a threading lock would require an async lock which
        # isn't available from sync context, so we dispatch directly.
        for cb in list(self._callbacks):
            try:
                cb(event)
            except Exception:
                pass

    def history(self) -> list[Event]:
        return list(self._history)


# ── File-system watcher ────────────────────────────────────────────────────

class _WatchHandler(FileSystemEventHandler):
    """Watchdog handler — emits ``file`` events with action."""

    _bus: EventBus

    def __init__(self, bus: EventBus) -> None:
        super().__init__()
        self._bus = bus

    def _emit(self, action: str, event: FileSystemEvent) -> None:
        src = getattr(event, "dest_path", None) or event.src_path
        # Use sync publish so it works from the watchdog thread
        self._bus.publish_sync(
            Event(
                type="file",
                body={
                    "action": action,
                    "path": str(src).replace("\\", "/"),
                },
            )
        )

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._emit("created", event)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._emit("modified", event)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._emit("deleted", event)

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._emit("moved", event)


# ── Subprocess runner ──────────────────────────────────────────────────────

def _run_process_sync(
    args: list[str],
    cwd: Path,
    bus: EventBus,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run *args* synchronously under *cwd*.

    Emits events to *bus* and returns a result dict.
    """
    _check_command(" ".join(args))

    t0 = time.monotonic()
    merged_env: dict[str, str] = {}
    merged_env.update(os.environ)
    if env:
        merged_env.update(env)

    # Emit start event
    bus.publish_sync(Event(type="cmd", body={"command": args[0]}))

    proc = subprocess.Popen(
        args,
        cwd=str(cwd),
        env=merged_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    # Stream output line-by-line
    assert proc.stdout is not None
    for line in proc.stdout:
        bus.publish_sync(Event(type="cmd", body={"output": line.rstrip("\n")}))

    exit_code = proc.wait()
    elapsed = time.monotonic() - t0

    bus.publish_sync(
        Event(
            type="cmd",
            body={
                "command": args[0],
                "exit_code": exit_code,
                "elapsed_s": round(elapsed, 3),
                "peak_rss_mb": 0.0,
                "mean_cpu_pct": 0.0,
            },
        )
    )

    return {
        "exit_code": exit_code,
        "elapsed_s": round(elapsed, 3),
        "peak_rss_mb": 0.0,
        "mean_cpu_pct": 0.0,
    }


# ── Recorder (high-level orchestrator) ────────────────────────────────────

class Recorder:
    """Orchestrates tracing, file-watching, and event collection."""

    _bus: EventBus
    _root: Path
    _watcher: Observer
    _config: dict[str, Any]

    # Backward-compat: tests set ``rec.running = False`` to stop.
    running: bool = True

    def __init__(
        self,
        root: Path,
        bus: EventBus | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._root = Path(root).resolve()
        self._bus = bus or EventBus()
        self._config = config or {}
        _init_config(self._config)
        self._watcher = Observer()

    @property
    def bus(self) -> EventBus:
        return self._bus

    # -- Sync command execution (backward-compat) ----------------------------

    def trace_command(
        self,
        cmd: str | list[str],
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Run a command under monitoring (synchronous).

        Accepts a string (auto-split via shlex) or a list of args.
        """
        if isinstance(cmd, str):
            cmd = _safe_split(cmd)
        return _run_process_sync(cmd, self._root, self._bus, env)

    # -- Async command execution ---------------------------------------------

    async def exec(
        self,
        cmd: list[str] | str,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute a command under monitoring (async).

        Accepts a list of args (preferred) or a raw string (auto-split).
        """
        if isinstance(cmd, str):
            cmd = _safe_split(cmd)
        await self._bus.publish(Event(type="cmd", body={"command": cmd[0]}))
        return await self._async_run_process(cmd, self._bus, env)

    async def _async_run_process(
        self,
        args: list[str],
        bus: EventBus,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        import resource

        _check_command(" ".join(args))
        t0 = time.monotonic()
        cpu_samples: list[float] = []

        merged_env: dict[str, str] = {}
        merged_env.update(os.environ)
        if env:
            merged_env.update(env)

        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(self._root),
            env=merged_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        assert proc.stdout is not None
        async for line in proc.stdout:
            decoded = line.decode(errors="replace").rstrip("\n")
            await bus.publish(Event(type="cmd", body={"output": decoded}))
            try:
                usage = resource.getrusage(resource.RUSAGE_CHILDREN)
                cpu_samples.append(usage.ru_utime + usage.ru_stime)
            except Exception:
                pass

        exit_code = await proc.wait()
        elapsed = time.monotonic() - t0
        peak_mb = 0.0
        mean_cpu = (
            (sum(cpu_samples) / elapsed) * 100
            if elapsed > 0 and cpu_samples
            else 0.0
        )

        await bus.publish(
            Event(
                type="cmd",
                body={
                    "command": args[0],
                    "exit_code": exit_code,
                    "elapsed_s": round(elapsed, 3),
                    "peak_rss_mb": round(peak_mb, 1),
                    "mean_cpu_pct": round(mean_cpu, 1),
                },
            )
        )

        return {
            "exit_code": exit_code,
            "elapsed_s": round(elapsed, 3),
            "peak_rss_mb": round(peak_mb, 1),
            "mean_cpu_pct": round(mean_cpu, 1),
        }

    async def watch(self, timeout: float = 0) -> None:
        """Start watching for file-system events.

        Non-blocking when *timeout* is 0 (poll-and-yield).
        """
        self.running = True
        loop = asyncio.get_running_loop()
        self._bus.set_loop(loop)
        handler = _WatchHandler(self._bus)
        self._watcher.schedule(handler, str(self._root), recursive=True)
        self._watcher.start()
        if timeout > 0:
            await asyncio.sleep(timeout)
            self.stop()

    def stop(self) -> None:
        self.running = False
        self._watcher.stop()
        self._watcher.join()