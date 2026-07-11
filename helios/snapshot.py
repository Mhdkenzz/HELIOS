"""
Helios Snapshot — Git tagging, guarded rollback, and housekeeping.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .schemas import SnapshotInfo
from . import TAG_RE_PATTERN, PROTECTED_FILES

TAG_RE = re.compile(TAG_RE_PATTERN)


class SnapshotError(Exception):
    """Raised when a snapshot or rollback operation fails."""


class SnapshotManager:
    """Manages Git snapshots and rollbacks for a project directory."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        if not self._is_git_repo():
            raise SnapshotError("Not a git repository")

    def snapshot(self, tag: str = "") -> SnapshotInfo:
        """Create a tagged snapshot of the current working tree."""
        if not tag:
            tag = self._generate_tag()
        else:
            tag = tag.strip()

        subprocess.run(
            ["git", "tag", tag],
            cwd=str(self.root),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "add", "-A"],
            cwd=str(self.root),
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", f"snapshot: {tag}", "--allow-empty"],
            cwd=str(self.root),
            capture_output=True,
        )
        return SnapshotInfo(tag=tag, root=str(self.root))

    def rollback(self, tag: str) -> str:
        """Reset to a tagged snapshot. Returns new HEAD SHA."""
        if not re.match(TAG_RE_PATTERN, tag):
            raise SnapshotError(
                f"Invalid tag name '{tag}'. Must match {TAG_RE_PATTERN}"
            )
        self._validate_rollback(tag)

        subprocess.run(
            ["git", "reset", "--hard", tag],
            cwd=str(self.root),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "clean", "-fdx"],
            cwd=str(self.root),
            capture_output=True,
        )

        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return sha

    def diff(self, path: str = ".") -> str:
        """Return git diff for a given file/dir relative to HEAD."""
        result = subprocess.run(
            ["git", "diff", "HEAD", "--", path],
            cwd=str(self.root),
            capture_output=True,
            text=True,
        )
        return result.stdout

    def list_tags(self) -> list[str]:
        """List all Helios snapshot tags, newest first."""
        result = subprocess.run(
            ["git", "tag", "--list", "helios-*", "--sort", "-version:refname"],
            cwd=str(self.root),
            capture_output=True,
            text=True,
        )
        return [t.strip() for t in result.stdout.splitlines() if t.strip()]

    def purge(
        self,
        keep: int = 10,
        delete_tags: bool = True,
        delete_html: bool = True,
    ) -> dict[str, object]:
        """Purge old snapshots and reclaim disk space."""
        tags = self.list_tags()
        to_delete = tags[keep:]
        deleted_tags = 0
        deleted_html = 0

        if delete_tags and to_delete:
            for tag in to_delete:
                subprocess.run(
                    ["git", "tag", "-d", tag],
                    cwd=str(self.root),
                    capture_output=True,
                )
                deleted_tags += 1

        if delete_html:
            for f in self.root.glob("*-run-*.html"):
                f.unlink(missing_ok=True)
                deleted_html += 1

        return {"deleted_tags": deleted_tags, "deleted_html": deleted_html}

    def _is_git_repo(self) -> bool:
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=str(self.root),
                capture_output=True,
                text=True,
            )
            return r.returncode == 0
        except Exception:
            return False

    def _validate_rollback(self, tag: str) -> None:
        """Refuse rollback if protected files changed since the tag."""
        for fname in PROTECTED_FILES:
            fp = self.root / fname
            if not fp.exists():
                continue
            result = subprocess.run(
                ["git", "diff", tag, "--", fname],
                cwd=str(self.root),
                capture_output=True,
                text=True,
            )
            if result.stdout.strip():
                raise SnapshotError(
                    f"protected files changed: '{fname}' modified since snapshot {tag}"
                )

    def _generate_tag(self) -> str:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"helios-{ts}"