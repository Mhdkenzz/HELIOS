"""
Helios Recorder — Event bus, subprocess tracer, file watcher, and metrics sampler.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

import psutil
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .schemas import Event

logger = logging.getLogger(__name__)

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
    _thread_lock: threading.Lock
    _callbacks: list[Callable[[Event], None]]
    _history: list[Event]
    _loop: asyncio.AbstractEventLoop | None

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._thread_lock = threading.Lock()
        self._callbacks = []
        self._history = []
        self._loop = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Store the running event loop for thread-safe dispatching."""
        self._loop = loop

    def subscribe(self, callback: Callable[[Event], None]) -> None:
        with self._thread_lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def unsubscribe(self, callback: Callable[[Event], None]) -> None:
        with self._thread_lock:
            self._callbacks.remove(callback)

    async def publish(self, event: Event) -> None:
        """Async publish — appends to history and dispatches to callbacks."""
        async with self._lock:
            cbs = list(self._callbacks)
            self._history.append(event)
        for cb in cbs:
            try:
                cb(event)
            except Exception:
                logger.exception("EventBus async callback failed")

    def publish_sync(self, event: Event) -> None:
        """Sync publish — safe to call from any thread.

        Appends to history synchronously and dispatches callbacks.
        """
        with self._thread_lock:
            self._history.append(event)
            cbs = list(self._callbacks)
        for cb in cbs:
            try:
                cb(event)
            except Exception:
                logger.exception("EventBus sync callback failed")

    def history(self) -> list[Event]:
        return list(self._history)


# ── File-system watcher with 50 ms debounce ────────────────────────────────

class _WatchHandler(FileSystemEventHandler):
    """Watchdog handler — debounces file events and emits batched events."""

    _bus: EventBus
    _debounce_ms: int
    _buffer: list[tuple[str, str]]  # (action, path) pairs
    _timer_handle: asyncio.TimerHandle | None
    _loop: asyncio.AbstractEventLoop | None

    def __init__(self, bus: EventBus, debounce_ms: int = 50) -> None:
        super().__init__()
        self._bus = bus
        self._debounce_ms = debounce_ms
        self._buffer = []
        self._timer_handle = None
        self._loop = None

    def _emit_batch(self) -> None:
        """Flush the accumulated buffer as a single batched event."""
        if not self._buffer:
            return
        batch = list(self._buffer)
        self._buffer.clear()
        self._bus.publish_sync(
            Event(
                type="file",
                body={
                    "events": [
                        {"action": action, "path": path}
                        for action, path in batch
                    ],
                },
            )
        )

    def _schedule_flush(self) -> None:
        """Schedule a flush after the debounce window."""
        if self._timer_handle is not None:
            self._timer_handle.cancel()
        if self._loop and not self._loop.is_closed():
            self._timer_handle = self._loop.call_later(
                self._debounce_ms / 1000.0, self._emit_batch
            )

    def _record(self, action: str, event: FileSystemEvent) -> None:
        src = getattr(event, "dest_path", None) or event.src_path
        path = str(src).replace("\\", "/")
        # Deduplicate: if same action+path already buffered, skip
        if (action, path) in self._buffer:
            return
        self._buffer.append((action, path))
        self._schedule_flush()

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._record("created", event)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._record("modified", event)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._record("deleted", event)

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._record("moved", event)


# ── Subprocess runner (sync, with PTY support) ────────────────────────────

def _supports_pty() -> bool:
    """Return True if pexpect (or platform PTY) is available."""
    try:
        import pexpect  # noqa: F401
        return True
    except ImportError:
        return False


def _run_process_sync(
    args: list[str],
    cwd: Path,
    bus: EventBus,
    env: dict[str, str] | None = None,
    use_pty: bool = True,
) -> dict[str, Any]:
    """Run *args* synchronously under *cwd*.

    Emits events to *bus* and returns a result dict.
    Uses pexpect when available for PTY capture (better output formatting);
    falls back to plain subprocess.
    """
    _check_command(" ".join(args))

    t0 = time.monotonic()
    merged_env: dict[str, str] = {}
    merged_env.update(os.environ)
    if env:
        merged_env.update(env)

    # Emit start event
    bus.publish_sync(Event(type="cmd", body={"command": args[0]}))

    peak_rss_mb = 0.0
    cpu_samples: list[float] = []
    exit_code: int = -1

    # ── Try PTY path first (pexpect) ──────────────────────────────────
    if use_pty and _supports_pty():
        import pexpect

        try:
            proc = pexpect.spawn(
                args[0],
                args=args[1:],
                cwd=str(cwd),
                env=merged_env,
                encoding="utf-8",
                timeout=None,
            )
            try:
                p = psutil.Process(proc.pid) if proc.pid else None
            except psutil.NoSuchProcess:
                p = None

            while True:
                try:
                    idx = proc.expect(["\n", pexpect.EOF, pexpect.TIMEOUT], timeout=0.05)
                except Exception:
                    break
                if idx == 0:  # newline
                    line = (proc.before or "") + "\n"
                    if line.strip():
                        bus.publish_sync(Event(type="cmd", body={"output": line.rstrip("\n")}))
                    if p is not None:
                        try:
                            mem = p.memory_info().rss / 1e6
                            peak_rss_mb = max(peak_rss_mb, mem)
                            cpu_samples.append(p.cpu_percent(interval=0.0))
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                elif idx == 1:  # EOF
                    break
                elif idx == 2:  # TIMEOUT — still alive, keep sampling
                    if p is not None:
                        try:
                            mem = p.memory_info().rss / 1e6
                            peak_rss_mb = max(peak_rss_mb, mem)
                            cpu_samples.append(p.cpu_percent(interval=0.0))
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass

            exit_code = proc.exitstatus if hasattr(proc, "exitstatus") and proc.exitstatus is not None else -1
            if exit_code is None:
                exit_code = 0
        except Exception as exc:
            logger.warning("PTY failed, falling back to subprocess: %s", exc)
            exit_code = -1  # will be overridden by subprocess fallback below

    # ── Fallback: plain subprocess ────────────────────────────────────
    if exit_code == -1 or not use_pty or not _supports_pty():
        proc = subprocess.Popen(
            args,
            cwd=str(cwd),
            env=merged_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        assert proc.stdout is not None
        try:
            p = psutil.Process(proc.pid)
        except psutil.NoSuchProcess:
            p = None

        for line in proc.stdout:
            bus.publish_sync(Event(type="cmd", body={"output": line.rstrip("\n")}))
            if p is not None:
                try:
                    mem = p.memory_info().rss / 1e6
                    peak_rss_mb = max(peak_rss_mb, mem)
                    cpu_samples.append(p.cpu_percent(interval=0.0))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        exit_code = proc.wait()

    elapsed = time.monotonic() - t0

    mean_cpu = (
        (sum(cpu_samples) / len(cpu_samples))
        if cpu_samples
        else 0.0
    )

    bus.publish_sync(
        Event(
            type="cmd",
            body={
                "command": args[0],
                "exit_code": exit_code,
                "elapsed_s": round(elapsed, 3),
                "peak_rss_mb": round(peak_rss_mb, 1),
                "mean_cpu_pct": round(mean_cpu, 1),
            },
        )
    )

    return {
        "exit_code": exit_code,
        "elapsed_s": round(elapsed, 3),
        "peak_rss_mb": round(peak_rss_mb, 1),
        "mean_cpu_pct": round(mean_cpu, 1),
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
        self._handler: _WatchHandler | None = None

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
        _check_command(" ".join(args))
        t0 = time.monotonic()
        cpu_samples: list[float] = []
        peak_rss_mb = 0.0

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

        try:
            p = psutil.Process(proc.pid) if proc.pid else None
        except psutil.NoSuchProcess:
            p = None

        async for line in proc.stdout:
            decoded = line.decode(errors="replace").rstrip("\n")
            await bus.publish(Event(type="cmd", body={"output": decoded}))
            if p is not None:
                try:
                    mem = p.memory_info().rss / 1e6
                    peak_rss_mb = max(peak_rss_mb, mem)
                    cpu_samples.append(p.cpu_percent(interval=0.0))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        exit_code = await proc.wait()
        elapsed = time.monotonic() - t0

        mean_cpu = (
            (sum(cpu_samples) / len(cpu_samples))
            if cpu_samples
            else 0.0
        )

        await bus.publish(
            Event(
                type="cmd",
                body={
                    "command": args[0],
                    "exit_code": exit_code,
                    "elapsed_s": round(elapsed, 3),
                    "peak_rss_mb": round(peak_rss_mb, 1),
                    "mean_cpu_pct": round(mean_cpu, 1),
                },
            )
        )

        return {
            "exit_code": exit_code,
            "elapsed_s": round(elapsed, 3),
            "peak_rss_mb": round(peak_rss_mb, 1),
            "mean_cpu_pct": round(mean_cpu, 1),
        }

    async def watch(self, timeout: float = 0) -> None:
        """Start watching for file-system events.

        Non-blocking when *timeout* is 0 (poll-and-yield).
        """
        self.running = True
        loop = asyncio.get_running_loop()
        self._bus.set_loop(loop)
        self._handler = _WatchHandler(self._bus, self._config.get("debounce_ms", 50))
        self._handler._loop = loop
        self._watcher.schedule(self._handler, str(self._root), recursive=True)
        self._watcher.start()
        if timeout > 0:
            await asyncio.sleep(timeout)
            self.stop()

    def stop(self) -> None:
        self.running = False
        # Flush any pending debounced events
        if self._handler is not None:
            self._handler._emit_batch()
        self._watcher.stop()
        self._watcher.join()