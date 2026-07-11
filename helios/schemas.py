"""
Helios Schemas — Pydantic models for events and snapshot metadata.
"""

import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ── Core event model ────────────────────────────────────────────────────────


class Event(BaseModel):
    """Represents a single traced event (command, file change, alert, etc.)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    type: str
    body: dict[str, Any] = Field(default_factory=dict)
    ts: float = Field(default_factory=lambda: time.time())

    # ── Serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON / WebSocket transmission."""
        d: dict[str, Any] = {"type": self.type, "ts": self.ts}
        if self.body:
            d["body"] = self.body
        return d

    def serialise(self) -> dict[str, Any]:
        """Alias for ``to_dict`` (backward compat)."""
        return self.to_dict()


# ── Snapshot metadata ───────────────────────────────────────────────────────


class SnapshotInfo(BaseModel):
    """Lightweight metadata about a saved snapshot."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tag: str
    ts: float = Field(default_factory=lambda: time.time())
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"tag": self.tag, "ts": self.ts, "note": self.note}