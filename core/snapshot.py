"""Git snapshot & rollback helpers for Helios."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Snapshot:
    """Represents a point-in-time snapshot of a git repo."""

    commit: str
    branch: str
    tag: str | None
    dirty: bool
    stash_ref: str | None = None


class SnapshotError(Exception):
    """Raised when a snapshot or rollback operation fails."""


class SnapshotManager:
    """Take and restore git-level snapshots with rollback guards."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._validate_git_repo()

    # ── internal ────────────────────────────────────────────────────────

    def _validate_git_repo(self) -> None:
        if not (self.root / ".git").exists():
            raise SnapshotError(
                f"Not a git repository: {self.root}. "
                "Run `git init` first."
            )

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(self.root), *args],
            capture_output=True,
            text=True,
            check=check,
        )

    # ── public API ──────────────────────────────────────────────────────

    def take_snapshot(self) -> Snapshot:
        """Create a git stash or tag and return the current Snapshot."""
        # Current branch / commit
        branch_proc = self._run("rev-parse", "--abbrev-ref", "HEAD")
        commit_proc = self._run("rev-parse", "HEAD")
        branch = branch_proc.stdout.strip()
        commit = commit_proc.stdout.strip()

        # Check for uncommitted changes
        status_proc = self._run("status", "--porcelain")
        dirty = bool(status_proc.stdout.strip())

        tag = None
        stash_ref = None

        if dirty:
            stash_proc = self._run("stash", "push", "-m", "helios-snapshot")
            stash_ref = stash_proc.stdout.strip().split()[-1] if stash_proc.stdout.strip() else None
            # Re-capture the original commit after stash
            commit = self._run("rev-parse", "HEAD").stdout.strip()
        else:
            # Tag the current commit for easy rollback
            tag = f"helios/{int(__import__('time').time())}"
            self._run("tag", tag)

        return Snapshot(commit=commit, branch=branch, tag=tag, dirty=dirty, stash_ref=stash_ref)

    def rollback(self, snapshot: Snapshot) -> None:
        """
        Restore the working tree to the state captured in *snapshot*.

        Safety guard: refuses to roll back if `package.json` or `LICENSE`
        would be overwritten (protects config / legal files).
        """
        protected = {"package.json", "package-lock.json", "LICENSE", "LICENSE.md"}
        root_files = {p.name for p in self.root.iterdir() if p.is_file()}
        conflict = protected & root_files
        if conflict:
            raise SnapshotError(
                f"Rollback blocked — protected files present: {conflict}. "
                "Remove or stash them first."
            )

        # Hard reset to snapshot commit
        self._run("reset", "--hard", snapshot.commit)

        # Restore stashed changes if any
        if snapshot.stash_ref:
            self._run("stash", "pop")

        # Clean up temp tag
        if snapshot.tag:
            self._run("tag", "-d", snapshot.tag, check=False)

    def current_hash(self) -> str:
        """Return the current HEAD commit hash (short)."""
        return self._run("rev-parse", "--short", "HEAD").stdout.strip()