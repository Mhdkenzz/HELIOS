"""Integration tests for Helios."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli"))


# ── snapshot tests ────────────────────────────────────────────────────────


class TestSnapshotManager:
    def test_init_non_git_raises(self, tmp_path: Path) -> None:
        from core.snapshot import SnapshotManager, SnapshotError

        with pytest.raises(SnapshotError, match="Not a git repository"):
            SnapshotManager(tmp_path)

    def test_snapshot_and_rollback(self, tmp_path: Path) -> None:
        from core.snapshot import SnapshotManager

        # Initialise a git repo
        os.system(f"cd {tmp_path} && git init -q && git config user.email test@test.com && git config user.name Test")
        readme = tmp_path / "README.md"
        readme.write_text("# v1")
        os.system(f"cd {tmp_path} && git add . && git commit -q -m 'initial'")

        snap = SnapshotManager(tmp_path)
        snapshot = snap.take_snapshot()

        # Modify file
        readme.write_text("# v2 — modified")
        assert "# v2" in readme.read_text()

        # Rollback
        snap.rollback(snapshot)
        assert "# v1" in readme.read_text()

    def test_rollback_protects_package_json(self, tmp_path: Path) -> None:
        from core.snapshot import SnapshotManager, SnapshotError

        os.system(f"cd {tmp_path} && git init -q && git config user.email test@test.com && git config user.name Test")
        pkg = tmp_path / "package.json"
        pkg.write_text('{"name":"test"}')
        os.system(f"cd {tmp_path} && git add . && git commit -q -m 'init'")

        snap = SnapshotManager(tmp_path)
        snapshot = snap.take_snapshot()
        pkg.write_text('{"name":"modified"}')

        with pytest.raises(SnapshotError, match="protected files"):
            snap.rollback(snapshot)


# ── recorder smoke test ────────────────────────────────────────────────────


class TestRecorder:
    def test_smoke(self, tmp_path: Path) -> None:
        import asyncio
        from core.recorder import Recorder

        async def _run() -> None:
            rec = Recorder(tmp_path)
            task = asyncio.create_task(rec.watch())
            # Give watch() a tick to subscribe to the bus
            await asyncio.sleep(0)
            rec.trace_shell('echo "hello"')
            rec.running = False
            await asyncio.sleep(0.3)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            assert len(rec.events) > 0
            event_types = {e["type"] for e in rec.events}
            assert "shell.start" in event_types
            assert "shell.done" in event_types

            stats = rec.summarise()
            assert stats.num_events == len(rec.events)

        asyncio.run(_run())

    def test_event_serialization(self, tmp_path: Path) -> None:
        from core.recorder import TimelineEvent

        evt = TimelineEvent(type="test", detail='{"msg":"ok"}')
        d = evt.to_dict()
        assert "ts" in d
        assert d["type"] == "test"
        roundtripped = json.loads(json.dumps(d))
        assert roundtripped["type"] == "test"


# ── cli smoke ──────────────────────────────────────────────────────────────


class TestCLI:
    def test_helios_help(self) -> None:
        import subprocess

        result = subprocess.run(
            ["helios", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        combined = (result.stdout + result.stderr).lower()
        assert "helios" in combined