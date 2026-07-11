"""Integration tests for Helios MVP."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


# ── Snapshot tests ────────────────────────────────────────────────────────


class TestSnapshotManager:
    def test_init_non_git_raises(self, tmp_path: Path) -> None:
        from helios.snapshot import SnapshotManager, SnapshotError

        with pytest.raises(SnapshotError, match="Not a git repository"):
            SnapshotManager(tmp_path)

    def test_snapshot_and_rollback(self, tmp_path: Path) -> None:
        from helios.snapshot import SnapshotManager

        os.system(f"cd {tmp_path} && git init -q && git config user.email test@test.com && git config user.name Test")
        readme = tmp_path / "README.md"
        readme.write_text("# v1")
        os.system(f"cd {tmp_path} && git add . && git commit -q -m 'initial'")

        snap = SnapshotManager(tmp_path)
        snapshot = snap.snapshot()
        assert snapshot.tag.startswith("helios-")

        readme.write_text("# v2 — modified")
        assert "# v2" in readme.read_text()

        snap.rollback(snapshot.tag)
        assert "# v1" in readme.read_text()

    def test_rollback_protects_package_json(self, tmp_path: Path) -> None:
        from helios.snapshot import SnapshotManager, SnapshotError

        os.system(f"cd {tmp_path} && git init -q && git config user.email test@test.com && git config user.name Test")
        pkg = tmp_path / "package.json"
        pkg.write_text('{"name":"test"}')
        os.system(f"cd {tmp_path} && git add . && git commit -q -m 'init'")

        snap = SnapshotManager(tmp_path)
        snapshot = snap.snapshot()
        pkg.write_text('{"name":"modified"}')
        os.system(f"cd {tmp_path} && git add package.json")

        with pytest.raises(SnapshotError, match="protected files changed"):
            snap.rollback(snapshot.tag)

    def test_diff_returns_text(self, tmp_path: Path) -> None:
        from helios.snapshot import SnapshotManager

        os.system(f"cd {tmp_path} && git init -q && git config user.email test@test.com && git config user.name Test")
        readme = tmp_path / "README.md"
        readme.write_text("# v1")
        os.system(f"cd {tmp_path} && git add . && git commit -q -m 'initial'")
        readme.write_text("# v2")

        snap = SnapshotManager(tmp_path)
        diff = snap.diff("README.md")
        assert "v1" in diff or "v2" in diff or len(diff) > 0


# ── Recorder tests ────────────────────────────────────────────────────────


class TestRecorder:
    def test_smoke(self, tmp_path: Path) -> None:
        import asyncio
        from helios.recorder import Recorder

        async def _run():
            rec = Recorder(tmp_path)
            task = asyncio.create_task(rec.watch())
            await asyncio.sleep(0)
            rec.trace_command('echo "hello"')
            rec.running = False
            await asyncio.sleep(0.5)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            events = rec.bus.history()
            assert len(events) > 0, f"Expected events, got {rec.bus.history()}"
            event_types = {e.type for e in events}
            assert "cmd" in event_types

        asyncio.run(_run())

    def test_cmd_event_has_command(self, tmp_path: Path) -> None:
        import asyncio
        from helios.recorder import Recorder

        async def _run():
            rec = Recorder(tmp_path)
            task = asyncio.create_task(rec.watch())
            await asyncio.sleep(0)
            rec.trace_command('echo "hello world"')
            rec.running = False
            await asyncio.sleep(0.5)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            events = rec.bus.history()
            cmd_events = [e for e in events if e.type == "cmd" and "command" in (e.body or {})]
            assert len(cmd_events) >= 1
            assert "echo" in cmd_events[0].body["command"]

        asyncio.run(_run())

    def test_fs_events(self, tmp_path: Path) -> None:
        import asyncio
        from helios.recorder import Recorder

        async def _run():
            rec = Recorder(tmp_path)
            task = asyncio.create_task(rec.watch())
            await asyncio.sleep(0)

            test_file = tmp_path / "test_file.txt"
            test_file.write_text("hello")
            await asyncio.sleep(0.5)

            rec.running = False
            await asyncio.sleep(0.3)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            events = rec.bus.history()
            types = {e.type for e in events}
            assert "file" in types

        asyncio.run(_run())

    def test_event_json_roundtrip(self) -> None:
        from helios.schemas import Event

        evt = Event(type="cmd", body={"command": 'echo "hi"', "exit_code": 0})
        d = evt.serialise()
        assert d["type"] == "cmd"
        assert "exit_code" in d["body"]
        assert isinstance(d["ts"], float)


# ── Backend / WebSocket tests ──────────────────────────────────────────────


class TestBackend:
    def test_create_app(self, tmp_path: Path) -> None:
        from helios.backend import create_app
        from helios.recorder import EventBus

        bus = EventBus()
        snap = None  # type: ignore
        app = create_app(tmp_path, bus, snap)
        assert app is not None
        routes = [r.path for r in app.routes]
        assert "/ws" in routes
        assert "/diff" in routes

    def test_diff_endpoint_no_snapshot(self, tmp_path: Path) -> None:
        from helios.backend import create_app
        from helios.recorder import EventBus

        bus = EventBus()
        app = create_app(tmp_path, bus, None)
        try:
            from starlette.testclient import TestClient
        except ImportError:
            pytest.skip("starlette not installed")
        client = TestClient(app)
        resp = client.get("/diff?path=.")
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data


# ── CLI smoke tests ────────────────────────────────────────────────────────


class TestCLI:
    """CLI smoke tests via subprocess."""

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python", "-m", "helios"] + list(args),
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_helios_help(self) -> None:
        result = self._run("--help")
        assert result.returncode == 0
        combined = (result.stdout + result.stderr).lower()
        assert "helios" in combined

    def test_helios_run_help(self) -> None:
        result = self._run("run", "--help")
        assert result.returncode == 0
        combined = (result.stdout + result.stderr).lower()
        assert "command" in combined

    def test_helios_dashboard_help(self) -> None:
        result = self._run("dashboard", "--help")
        assert result.returncode == 0
        combined = (result.stdout + result.stderr).lower()
        assert "port" in combined