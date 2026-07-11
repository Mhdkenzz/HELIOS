"""Async event bus & pluggable recorders for Helios."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil


# ── Data model ────────────────────────────────────────────────────────────

@dataclass
class TimelineEvent:
    ts: float = field(default_factory=lambda: time.time())
    type: str = ""
    detail: str = ""
    pid: int | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ts"] = datetime.fromtimestamp(self.ts, tz=timezone.utc).isoformat()
        return d


@dataclass
class Metrics:
    peak_rss_mb: float = 0.0
    mean_cpu_pct: float = 0.0
    num_events: int = 0


# ── Event bus ─────────────────────────────────────────────────────────────

class EventBus:
    """In-memory event bus with replay buffer.

    Thread-safe: publish() can be called from any thread; the async
    side drains via ``history()`` or ``subscribe()``.
    """

    def __init__(self, max_events: int = 50_000) -> None:
        self._buffer: deque[TimelineEvent] = deque(maxlen=max_events)
        self._lock = threading.Lock()
        self._updated = threading.Event()

    # ── publishing (any thread) ──────────────────────────────────────────

    def publish(self, event: TimelineEvent) -> None:
        with self._lock:
            self._buffer.append(event)
        self._updated.set()

    # ── subscribing (event-loop thread) ──────────────────────────────────

    def history(self) -> list[TimelineEvent]:
        """Return a snapshot of every event published so far."""
        with self._lock:
            return list(self._buffer)

    async def wait_for_update(self, timeout: float = 1.0) -> bool:
        """Block (async) until a new event arrives or *timeout* expires."""
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
    """Orchestrates shell tracing, filesystem watching, and metrics."""

    def __init__(self, cwd: Path) -> None:
        self.cwd = cwd.resolve()
        self.bus = EventBus()
        self.events: list[dict] = []
        self.running = True
        self._metrics: dict[str, list[float]] = {"cpu": [], "rss": []}
        self._proc: subprocess.Popen | None = None

    # ── lifecycle ────────────────────────────────────────────────────

    async def watch(self) -> None:
        """Main async loop — start tracers and collect until stopped."""
        self._emit("system", "recorder.start", {"cwd": str(self.cwd)})

        # Launch background metric sampler
        sampler = asyncio.create_task(self._sample_metrics())

        # Launch filesystem watcher (uses watchdog in a thread)
        watcher_task = asyncio.create_task(self._watch_fs())

        # Drain the bus buffer into self.events as long as we're running
        try:
            while self.running:
                # Drain any events already in the buffer
                for evt in self.bus.history():
                    d = evt.to_dict()
                    if d not in self.events:
                        self.events.append(d)

                # Wait for new events (wakes us when a thread publishes)
                got = await self.bus.wait_for_update(timeout=0.5)
                if not got:
                    continue  # timeout → re-check self.running
        finally:
            sampler.cancel()
            watcher_task.cancel()
            try:
                await watcher_task
            except asyncio.CancelledError:
                pass

            # Final drain — anything published after the last loop tick
            for evt in self.bus.history():
                d = evt.to_dict()
                if d not in self.events:
                    self.events.append(d)

    async def _sample_metrics(self) -> None:
        """Sample CPU/RAM of current process tree every 200 ms."""
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

    async def _watch_fs(self) -> None:
        """Run watchdog FileSystemWatcher in a thread and emit events."""
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class _Handler(FileSystemEventHandler):
            def __init__(self, bus: EventBus, cwd: Path) -> None:
                self.bus = bus
                self.cwd = cwd

            def _rel(self, path: str) -> str:
                try:
                    return str(Path(path).relative_to(self.cwd))
                except ValueError:
                    return path

            def on_created(self, e):
                self.bus.publish(TimelineEvent("fs.create", self._rel(e.src_path)))

            def on_modified(self, e):
                self.bus.publish(TimelineEvent("fs.modify", self._rel(e.src_path)))

            def on_deleted(self, e):
                self.bus.publish(TimelineEvent("fs.delete", self._rel(e.src_path)))

            def on_moved(self, e):
                self.bus.publish(
                    TimelineEvent("fs.move", f"{self._rel(e.src_path)} → {self._rel(e.dest_path)}")
                )

        handler = _Handler(self.bus, self.cwd)
        observer = Observer()
        observer.schedule(handler, str(self.cwd), recursive=True)
        observer.start()
        try:
            while self.running:
                await asyncio.sleep(0.5)
        finally:
            observer.stop()
            observer.join()

    # ── shell tracer (runs synchronously; safe to call from a coroutine) ──

    def trace_shell(self, cmd: str) -> int:
        """Run a shell command, emitting events for stdout/stderr. Returns exit code."""
        self._emit("shell.start", cmd, {"command": cmd})
        t0 = time.monotonic()

        proc = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid,
            cwd=str(self.cwd),
        )
        self._proc = proc

        # Stream output in daemon threads → thread-safe bus.publish()
        def _drain(stream, kind):
            for line in iter(stream.readline, b""):
                self._emit("shell.output", line.decode(errors="replace").rstrip(), {"stream": kind})

        threading.Thread(target=_drain, args=(proc.stdout, "stdout"), daemon=True).start()
        threading.Thread(target=_drain, args=(proc.stderr, "stderr"), daemon=True).start()

        rc = proc.wait()
        elapsed = time.monotonic() - t0
        self._emit("shell.done", f"exit={rc}", {"exit_code": rc, "elapsed_s": round(elapsed, 3)})
        return rc

    # ── helpers ──────────────────────────────────────────────────────

    def _emit(self, event_type: str, detail: str, extra: dict[str, Any] | None = None) -> None:
        evt = TimelineEvent(type=event_type, detail=json.dumps({"detail": detail} | (extra or {})))
        self.bus.publish(evt)

    def summarise(self) -> Metrics:
        cpu = self._metrics["cpu"]
        rss = self._metrics["rss"]
        return Metrics(
            peak_rss_mb=max(rss) if rss else 0.0,
            mean_cpu_pct=(sum(cpu) / len(cpu)) if cpu else 0.0,
            num_events=len(self.events),
        )