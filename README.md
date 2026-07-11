# 🔆 Helios

Lightweight watchdog + replay tool for AI coding agents.

**Watch what your agent does. Replay it. Roll back when it breaks.**

![PyPI](https://img.shields.io/pypi/v/helios?color=blue&label=PyPI)
![CI](https://github.com/Mhdkenzz/HELIOS/actions/workflows/ci.yml/badge.svg)
![Python 3.10+](https://img.shields.io/pypi/pyversions/helios?color=green)
![License: MIT](https://img.shields.io/badge/license-MIT-blue)
![Downloads](https://img.shields.io/pypi/dm/helios?color=orange)

---

> *"Helios" — the sun god who sees everything your agent does.*

## Quick Start (30 seconds)

```bash
# One-step install — everything bundled, no npm required
pipx install helios

# Run your agent under Helios monitoring
cd ~/my-project
helios run -- your-agent-command --arg value

# Watch live at http://localhost:6767
```

Helios will:

| Step | What happens |
|------|-------------|
| `helios run -- <cmd>` | Tags the current commit as `helios-YYYYMMDDTHHMMSSZ` |
| During run | Shell I/O, file CRUD, and CPU/RAM are captured via a thread-safe event bus |
| Live dashboard | WebSocket streams events to a React timeline at `localhost:6767` |
| On exit | Auto-generates a **self-contained HTML replay** file |
| Rollback | `git reset --hard <tag>` + `git clean -fdx`, guarded against overwrite of `LICENSE`, `package.json`, `helios.toml`, `pyproject.toml` |

## Commands

```bash
helios run -- <command>              # Run and record a command
helios run -- --dry-run <cmd>        # Record events without executing (safe preview)
helios run -- --deny rm,git          # Block dangerous commands
helios run -- --allow npm,node,python # Only allow specific commands

helios dashboard                     # Launch web UI at :6767
helios prune --keep 10               # Delete old snapshots and replay files
helios info                          # Show version and config summary
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--root`, `-r` | `.` | Project root to watch |
| `--host` | `0.0.0.0` | Bind address |
| `--port`, `-p` | `6767` | Dashboard port |
| `--dry-run` | off | Record events without executing commands |
| `--deny` | `[]` | Comma-separated commands to block |
| `--allow` | `[]` | Comma-separated commands to permit (bypass deny) |
| `--rollback-token` | `""` | Shared secret for `/rollback` auth |
| `--no-dashboard` | off | Run without launching the UI |
| `--verbose`, `-v` | off | Debug logging |

## Configuration

Create `helios.toml` in your project root (see [`helios.toml.example`](helios.toml.example)):

```toml
[helios]
host = "0.0.0.0"
port = 6767
dry_run = false
deny_commands = ["rm -rf /", "git push --force"]
allow_commands = []
rollback_token = ""
theme = "dark"
accent_color = "#60a5fa"
```

Or use environment variables:

```bash
export HELIOS_DENY="rm,git push"
export HELIOS_ALLOW="npm,node,python"
export HELIOS_ROLLBACK_TOKEN="your-secret-token"
```

## Demo

![Dashboard](./docs/demo-dashboard.png)
![Rollback Confirmation](./docs/demo-rollback.png)

## Cross-Platform Notes

| Platform | Support |
|----------|---------|
| Linux | Full — uses stdlib `pty` or `pexpect` |
| macOS | Full — uses stdlib `pty` or `pexpect` |
| Windows | Partial — uses `pywinpty`/ConPTY with `pip install helios[windows-pty]`, falls back to subprocess |

## Architecture

- **CLI** (`helios/cli.py`) — Typer commands: `run`, `dashboard`, `prune`, `info`
- **Backend** (`helios/backend.py`) — FastAPI + WebSocket server with embedded React frontend
- **Recorder** (`helios/recorder.py`) — EventBus, PTY subprocess tracer, file-watch, metrics
- **Snapshot** (`helios/snapshot.py`) — Git tagging, guarded rollback, housekeeping
- **Frontend** (`web/`) — React + Vite + Tailwind, bundled into Python wheel

## Docker

```bash
docker compose up --build
# Backend + frontend on http://localhost:6767
```

## Dev Commands

```bash
make dev          # Backend (uvicorn) + frontend (vite dev)
make install      # pip install -e ".[dev]" + npm install
make test         # pytest tests/ -v
make lint         # syntax check
make clean        # remove caches
```

Or manually:

```bash
# Terminal 1
uvicorn helios.backend:create_app --reload --port 6767

# Terminal 2
cd web && npm run dev
```

## Docs

- [Installation](docs/installation.md)
- [Usage Guide](docs/usage.md)
- [Architecture](docs/architecture.md)
- [Configuration](docs/configuration.md)
- [Plugin API](docs/plugin-api.md)
- [Troubleshooting](docs/troubleshooting.md)
- [FAQ](docs/faq.md)
- [Contributing](docs/contributing.md)

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

---

**Helios** — *see everything your agent did, and undo it in one click.*