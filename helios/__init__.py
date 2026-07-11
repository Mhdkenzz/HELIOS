"""
Helios — a watchdog + replay tool for AI coding agents.

One `pipx install helios` to rule them all.
"""

from __future__ import annotations

from typing import Any

__version__ = "0.2.0"

# Default site-level config values (overridden by helios.toml or env vars)
SITE: dict[str, Any] = {
    "deny": [],
    "allow": [],
    "dry_run": False,
    "host": "0.0.0.0",
    "port": 6767,
    "rollback_token": "",
    "debounce_ms": 50,
    "max_events": 50000,
    "theme": "dark",
    "accent_color": "#60a5fa",
    "font_family": "JetBrains Mono, Fira Code, monospace",
}

TAG_RE_PATTERN = r"^helios-\d{8}T\d{6}Z?$"

PROTECTED_FILES: set[str] = {"package.json", "LICENSE", "helios.toml", "pyproject.toml"}


def version() -> str:
    """Return the installed package version string."""
    return __version__