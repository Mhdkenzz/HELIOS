# 🔆 Helios

Lightweight watchdog + replay tool for AI coding agents.

**Watch what your agent does. Replay it. Roll back when it breaks.**

---

## Quick Start (30 seconds)

```bash
# 1. Clone & install
pip install -e ".[dev]"
cd web && npm install && cd ..

# 2. Go to a git repo and run your agent under Helios
cd ~/my-project
helios run -- your-agent-command --arg value

# 3. Watch the live dashboard (opens automatically)
#    → http://localhost:6767

# 4. When done, a standalone HTML replay is saved:
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

## Cross-Platform Notes

| Platform | Notes |
|----------|-------|
| **Linux** | Full support — uses PTY for terminal I/O |
| **macOS** | Full support — uses PTY for terminal I/O |
| **Windows** | Subprocess fallback (no PTY); file watcher still works |

## Architecture

```
helios/
├── cli.py                  # Typer CLI: helios run | helios dashboard
├── schemas.py              # Pydantic event & snapshot models
├── snapshot.py             # Git snapshot + guarded rollback
├── recorder.py             # Event bus, PTY tracer, watchdog watcher, metrics
├── backend.py              # FastAPI: /ws, /diff, /rollback, static frontend
├── web/
│   ├── index.html
│   ├── src/
│   │   ├── main.tsx        # Entry point
│   │   └── App.tsx         # Timeline + diff modal + restore bar
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

## Event Schema

Every event is a small JSON object:

```json
{ "ts": 1752234567.123, "type": "cmd"|"file"|"alert"|"system", "body": { ... } }
```

| Type  | Body fields                              | Example |
|-------|------------------------------------------|---------|
| `cmd` | `command`, `output`, `exit_code`, `elapsed_s`, `mode` | `{"command":"npm test","exit_code":0}` |
| `file`| `action`, `path` (or `from`/`to`)        | `{"action":"modified","path":"src/app.tsx"}` |
| `alert`| `msg`                                   | `{"msg":"disk > 90%"}` |
| `system`| `msg`                                  | `{"msg":"recorder.start"}` |

## Constraints

- **Pure local** — no telemetry, no cloud uploads
- **≤ 200 MB RAM** idle
- **Zero native deps** — pure Python + Node
- **MIT licensed**

## Docker

```bash
docker compose up --build
# Backend on :6767, frontend on :5173
```

## Stretch Goals (parking lot)

- [ ] GPU/RAM charts in dashboard
- [ ] VS Code extension
- [ ] Signed snapshots (GPG/SSH)
- [ ] Windows PTY support
- [ ] Binary distribution

---

**Helios** — *see everything your agent did, and undo it in one click.*