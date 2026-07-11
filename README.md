# 🔆 Helios

Lightweight watchdog + replay tool for AI coding agents.

**Watch what your agent does. Replay it. Roll back when it breaks.**

[![CI](https://github.com/yourorg/helios/actions/workflows/ci.yml/badge.svg)](https://github.com/yourorg/helios/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/helios.svg)](https://pypi.org/project/helios/)
[![Python 3.10+](https://img.shields.io/pypi/pyversions/helios.svg)](https://pypi.org/project/helios/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## Quick Start (30 seconds)

```bash
# One-step install — everything included
pipx install helios

# Go to a git repo and run your agent under Helios
cd ~/my-project
helios run -- your-agent-command --arg value

# Watch the live dashboard (opens automatically)
#    → http://localhost:6767

# When done, a standalone HTML replay is auto-generated:
#    run-20250711-143022.html
```

That's it. Helios will:

| Step | What happens |
|------|-------------|
| `helios run -- <cmd>` | Tags the current commit as `helios-<iso-utc>` |
| During run | Shell I/O, file CRUD, and CPU/RAM are captured via a thread-safe event bus |
| Dashboard | WebSocket streams events to a React timeline at `localhost:6767` |
| Exit | Auto-generates a **self-contained HTML replay** file |
| Rollback | `git reset --hard <tag>` + `git clean -fdx`, guarded against `package.json`/`LICENSE` overwrite |

## Commands

```bash
helios run -- <command>           # Run and record a command
helios run -- --dry-run <cmd>     # Record without executing (safe preview)
helios run -- --deny rm,git      # Block dangerous commands
helios run -- --allow npm,node    # Only allow specific commands

helios dashboard                  # Launch web UI only
helios prune --keep 10            # Delete old snapshots
helios info                       # Show setup info
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
| `--rollback-token` | `""` | Shared secret for `/rollback` endpoint |
| `--no-dashboard` | off | Run without launching the UI |
| `--verbose`, `-v` | off | Debug logging |

## Cross-Platform Notes

| Platform | Notes |
|----------|-------|
| **Linux** | Full support — uses PTY for terminal I/O |
| **macOS** | Full support — uses PTY for terminal I/O |
| **Windows** | ConPTY support via `pywinpty`; subprocess fallback |

## Architecture

```
helios/
├── cli.py                  # Typer CLI: helios run | dashboard | prune | info
├── schemas.py              # Pydantic event & snapshot models
├── snapshot.py             # Git snapshot + guarded rollback + prune
├── recorder.py             # Event bus, PTY tracer, watchdog watcher, metrics
├── backend.py              # FastAPI: /ws, /diff, /rollback, static frontend
├── __init__.py             # Default config (SITE), version
├── web/                    # Bundled React frontend (Vite + Tailwind)
│   ├── index.html
│   ├── src/
│   │   ├── main.tsx        # Entry point
│   │   └── App.tsx         # Timeline + diff modal + restore bar + virtual scroll
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   └── tsconfig.json
├── tests/
│   └── test_helios.py      # Pytest integration (CI on ubuntu/mac/windows)
├── Makefile
├── Dockerfile + docker-compose.yml
└── README.md
```

## Event Schema

Every event is a small JSON object:

```json
{ "ts": 1752234567.123, "type": "cmd"|"file"|"alert"|"system", "body": { ... } }
```

| Type  | Body fields                                              | Example                                         |
|-------|----------------------------------------------------------|-------------------------------------------------|
| `cmd` | `command`, `output`, `exit_code`, `elapsed_s`, `mode`  | `{"command":"npm test","exit_code":0}`          |
| `file`| `action`, `path` (or `from`/`to`)                       | `{"action":"modified","path":"src/app.tsx"}`   |
| `alert`| `msg`                                                  | `{"msg":"disk > 90%"}`                          |
| `system`| `msg`                                                 | `{"msg":"recorder.start"}`                      |

## Configuration

Create a `helios.toml` in your project root to customize:

```toml
[helios]
host = "0.0.0.0"
port = 6767
dry_run = false
deny_commands = ["rm", "git push"]
allow_commands = ["npm", "node", "python"]
rollback_token = "change-me-in-production"
debounce_ms = 50
max_events = 50000
```

Or use environment variables:

```bash
export HELIOS_ALLOW_ALL=0                    # disable all if allow-list set
export HELIOS_ROLLBACK_TOKEN="your-secret"   # auth for /rollback
```

## Dev Commands

```bash
make dev          # backend (uvicorn --reload) + frontend (vite dev)
make install      # pip install -e ".[dev]" + npm install
make test         # pytest tests/ -v
make lint         # syntax check
make clean        # remove caches
```

Or manually:

```bash
# Terminal 1 — backend + hot-reload
uvicorn helios.cli:app --reload --port 6767

# Terminal 2 — frontend
cd web && npm run dev
```

## Docker

```bash
docker compose up --build
# Backend on :6767, frontend on :5173
```

## Stretch Goals (parking lot)

- [ ] GPU/RAM charts in dashboard
- [ ] VS Code extension
- [ ] Signed snapshots (GPG/SSH)
- [x] ~~Windows PTY support~~ → ConPTY via pywinpty
- [ ] Binary distribution

---

**Helios** — *see everything your agent did, and undo it in one click.*