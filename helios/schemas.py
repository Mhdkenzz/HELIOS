"""Shared event schema for Helios."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from typing import Any

from pydantic import BaseModel, Field


EventTypes = Literal["cmd", "file", "alert", "system"]


class Event(BaseModel):
    """A single timeline event."""

    ts: float = Field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    type: EventTypes = "system"
    body: dict[str, Any] = Field(default_factory=dict)

    # ── helpers ────────────────────────────────────────────────────────

    @property
    def iso(self) -> str:
        return datetime.fromtimestamp(self.ts, tz=timezone.utc).isoformat()

    def serialise(self) -> dict:
        return self.model_dump(mode="json")


class SnapshotInfo(BaseModel):
    """Metadata about a git snapshot."""

    tag: str
    commit: str
    branch: str
    ts: float
    protected: bool = False  # True when package.json or LICENSE changed