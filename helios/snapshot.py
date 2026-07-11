"""Git snapshot & rollback with package.json / LICENSE guard."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from helios.schemas import SnapshotInfo

PROTECTED_FILES = {"package.json", "package-lock.json", "yarn.lock", "LICENSE", "LICENSE.md"}


class SnapshotError(Exception):
    """Raised when a snapshot or rollback operation fails."""


class SnapshotManager:
    """Takes git snapshots and performs guarded rollbacks."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._require_git()

    # ── internals ────────────────────────────────────────────────────────

    def _require_git(self) -> None:
        if not (self.root / ".git").exists():
            raise SnapshotError(f"Not a git repository: {self.root}. Run `git init` first.")

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(self.root), *args],
            capture_output=True,
            text=True,
            check=True,
        )

    @property
    def _is_dirty(self) -> bool:
        return bool(self._git("status", "--porcelain").stdout.strip())

    def _current_commit(self) -> str:
        return self._git("rev-parse", "HEAD").stdout.strip()

    def _branch(self) -> str:
        return self._git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    # ── public API ───────────────────────────────────────────────────────

    def snapshot(self) -> SnapshotInfo:
        """Create a tagged snapshot. Returns SnapshotInfo."""
        commit = self._current_commit()
        branch = self._branch()
        tag = f"helios-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"

        if self._is_dirty:
            # Stash dirty state, tag clean commit
            self._git("stash", "push", "-m", f"helios-snapshot-{tag}")
        else:
            # Tag the current commit
            self._git("tag", tag)

        return SnapshotInfo(tag=tag, commit=commit, branch=branch, ts=time.time())

    def rollback(self, tag: str) -> str:
        """
        Hard-reset to *tag*, clean untracked files.

        Safety: refuses if any protected file has been created/modified
        since the tag was created.
        """
        # Guard
        changed = self._git("diff", "--name-only", tag, "--").stdout.strip().splitlines()
        conflicts = set(changed) & PROTECTED_FILES
        if conflicts:
            raise SnapshotError(
                f"Rollback blocked — protected files changed since {tag}: {conflicts}. "
                f"Stash or commit them first."
            )

        # Reset
        self._git("reset", "--hard", tag)
        self._git("clean", "-fdx")

        # Pop stash if one exists (clean up after ourselves)
        stash_list = self._git("stash", "list", "--format=%gd %gs").stdout
        for line in stash_list.splitlines():
            if "helios-snapshot" in line:
                ref = line.split(":")[0].strip()
                self._git("stash", "pop", ref)
                self._git("stash", "drop", ref)
                break

        return self._git("rev-parse", "--short", "HEAD").stdout.strip()

    def diff(self, path: str = ".") -> str:
        """Return `git diff` for *path* (relative to root)."""
        return self._git("diff", "--", str(path)).stdout