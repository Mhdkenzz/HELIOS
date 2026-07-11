"""Async event bus, PTY command tracer, watchdog file watcher, and metrics."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import psutil

from helios.schemas import Event, SnapshotInfo

try:
    from ptyprocess.ptyprocess import PtyProcessError
except ImportError:
    PtyProcessError = Exception  # type: ignore


# ── Event Bus ─────────────────────────────────────────────────────────────

class EventBus:
    """Thread-safe in-memory event bus with async drain support."""

    def __init__(self, max_events: int = 50_000) -> None:
        self._buffer: deque[Event] = deque(maxlen=max_events)
        self._lock = threading.Lock()
        self._updated = threading.Event()
        self._on_event: list[Callable[[Event], None]] = []

    def publish(self, event: Event) -> None:
        with self._lock:
            self._buffer.append(event)
        self._updated.set()
        for cb in self._on_event:
            try:
                cb(event)
            except Exception:
                pass

    def subscribe(self, cb: Callable[[Event], None]) -> None:
        self._on_event.append(cb)

    def history(self) -> list[Event]:
        with self._lock:
            return list(self._buffer)

    async def wait_for_update(self, timeout: float = 1.0) -> bool:
        loop = asyncio.get_running_loop()
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, self._updated.wait, timeout),
                timeout=timeout + 0.5,
            )
            self._updated.clear()
            return True
        except asyncio.TimeoutError:
            return False


# ── Recorder ──────────────────────────────────────────────────────────────

class Recorder:
    """Orchestrates PTY command tracing, filesystem watching, and metrics."""

    def __init__(self, cwd: Path, bus: EventBus | None = None) -> None:
        self.cwd = cwd.resolve()
        self.bus = bus or EventBus()
        self.running = True
        self._metrics: dict[str, list[float]] = {"cpu": [], "rss": []}

    # ── lifecycle ────────────────────────────────────────────────────

    async def watch(self) -> None:
        """Main async loop — collect events until stopped."""
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        self.bus.publish(Event(type="system", body={"msg": "recorder.start", "cwd": str(self.cwd)}))

        sampler = asyncio.create_task(self._sample_metrics())

        class _Handler(FileSystemEventHandler):
            def __init__(self, bus: EventBus, cwd: Path):
                self.bus = bus
                self.cwd = cwd

            def _rel(self, p: str) -> str:
                try:
                    return str(Path(p).relative_to(self.cwd))
                except ValueError:
                    return p

            def on_created(self, e):
                self.bus.publish(Event(type="file", body={"action": "created", "path": self._rel(e.src_path)}))

            def on_modified(self, e):
                if not e.is_directory:
                    self.bus.publish(Event(type="file", body={"action": "modified", "path": self._rel(e.src_path)}))

            def on_deleted(self, e):
                self.bus.publish(Event(type="file", body={"action": "deleted", "path": self._rel(e.src_path)}))

            def on_moved(self, e):
                self.bus.publish(Event(type="file", body={
                    "action": "moved",
                    "from": self._rel(e.src_path),
                    "to": self._rel(e.dest_path),
                }))

        handler = _Handler(self.bus, self.cwd)
        observer = Observer()
        observer.schedule(handler, str(self.cwd), recursive=True)
        observer.start()

        try:
            while self.running:
                got = await self.bus.wait_for_update(timeout=0.5)
                if not got:
                    continue
        finally:
            observer.stop()
            observer.join()
            sampler.cancel()
            try:
                await sampler
            except asyncio.CancelledError:
                pass
            self.bus.publish(Event(type="system", body={"msg": "recorder.stop"}))

    async def _sample_metrics(self) -> None:
        proc = psutil.Process()
        while self.running:
            try:
                cpu = proc.cpu_percent(interval=None)
                rss = proc.memory_info().rss / (1024 * 1024)
                self._metrics["cpu"].append(cpu)
                self._metrics["rss"].append(rss)
            except psutil.NoSuchProcess:
                break
            await asyncio.sleep(0.2)

    # ── command tracer ──────────────────────────────────────────────

    def trace_command(self, cmd: str) -> int:
        """Run *cmd* via PTY (UNIX) or subprocess (Windows); stream events."""
        if sys.platform != "win32":
            return self._trace_pty(cmd)
        return self._trace_subprocess(cmd)

    def _trace_pty(self, cmd: str) -> int:
        """PTY-based tracer for UNIX."""
        try:
            import ptyprocess  # noqa: F401
        except ImportError:
            return self._trace_subprocess(cmd)

        self.bus.publish(Event(type="cmd", body={"command": cmd, "mode": "pty"}))
        t0 = time.monotonic()

        child = ptyprocess.PtyProcessUnicode.spawn(
            ["/bin/bash", "-c", cmd],
            cwd=str(self.cwd),
        )

        def _drain() -> None:
            while True:
                try:
                    chunk = child.read_nonblocking(4096, timeout=0.25)
                    if chunk:
                        self.bus.publish(Event(type="cmd", body={"output": chunk}))
                except PtyProcessError:
                    break
                except Exception:
                    break
                if not child.isalive():
                    # one final non-blocking drain
                    try:
                        tail = child.read_nonblocking(4096, timeout=0.1)
                        if tail:
                            self.bus.publish(Event(type="cmd", body={"output": tail}))
                    except Exception:
                        pass
                    break

        thr = threading.Thread(target=_drain, daemon=True)
        thr.start()

        rc = child.wait()
        thr.join(timeout=2)
        elapsed = time.monotonic() - t0
        self.bus.publish(Event(type="cmd", body={"exit_code": rc, "elapsed_s": round(elapsed, 3), "mode": "pty"}))
        return rc

    def _trace_subprocess(self, cmd: str) -> int:
        """Subprocess-based tracer — cross-platform fallback."""
        self.bus.publish(Event(type="cmd", body={"command": cmd, "mode": "subprocess"}))
        t0 = time.monotonic()

        popen_kwargs: dict[str, Any] = {
            "cwd": str(self.cwd),
            "shell": True,
        }

        if sys.platform != "win32":
            popen_kwargs.update(
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid,
            )

        proc = subprocess.Popen(cmd, **popen_kwargs)

        if sys.platform != "win32" and proc.stdout:
            def _drain() -> None:
                for line in iter(proc.stdout.readline, b""):
                    self.bus.publish(Event(type="cmd", body={"output": line.decode(errors="replace").rstrip()}))
            threading.Thread(target=_drain, daemon=True).start()

        rc = proc.wait()
        elapsed = time.monotonic() - t0
        self.bus.publish(Event(type="cmd", body={"exit_code": rc, "elapsed_s": round(elapsed, 3), "mode": "subprocess"}))
        return rc

    # ── helpers ──────────────────────────────────────────────────────

    def alert(self, msg: str) -> None:
        self.bus.publish(Event(type="alert", body={"msg": msg}))

    @property
    def recent_events(self) -> list[dict]:
        return [e.serialise() for e in self.bus.history()]