# 🔆 Helios

Lightweight watchdog + replay tool for AI coding agents.

**Watch what your agent does. Replay it. Roll back when it breaks.**

---

## Quick Start (15 seconds)

```bash
# Install
pip install helios

# Run your agent under Helios
helios run -- your-agent-command --arg value

# Open the dashboard (live or after the run)
helios dashboard

# Open the generated replay file in your browser
open run-*.html
```

That's it. Helios will:

1. Take a **git-level snapshot** of your repo
2. **Record** every shell command, file change, Git diff, and test output
3. **Stream** a live timeline to the dashboard at `http://localhost:6767`
4. **Export** a self-contained HTML replay file you can share or archive

---

## Architecture

```
helios/
├── cli/              # Typer CLI entrypoint
│   └── main.py       # helios run | helios dashboard
├── core/
│   ├── __init__.py
│   ├── snapshot.py   # Git snapshot + rollback with file-protect guards
│   └── recorder.py   # Async event bus, shell tracer, fs watcher, metrics
├── web/              # React + Vite + Tailwind dashboard
│   ├── index.html
│   ├── src/
│   │   ├── main.tsx  # Entry point
│   │   └── App.tsx   # Timeline UI with WebSocket stream
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   └── tsconfig.json
├── tests/
│   └── test_helios.py
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## How It Works

| Step | What happens |
|------|-------------|
| `helios run -- <cmd>` | Snapshots current git state (stash or tag), starts fs watcher + metrics sampler |
| During run | Shell I/O, file CRUD events, and resource usage are captured via an async event bus |
| Dashboard | WebSocket streams events to a React timeline UI with "Restore to this point" button |
| Exit | Auto-generates a standalone `run-YYYYMMDD-HHMMSS.html` replay file |
| Rollback | `git reset --hard` + guard that refuses to overwrite `package.json` or `LICENSE` |

## Constraints

- **Pure local** — no external telemetry, no cloud uploads
- **≤ 200 MB RAM** idle footprint
- **MIT licensed**
- Linux/macOS only for v0.1 (Windows parking lot)

## Dev Setup

```bash
# Clone & install dev deps
pip install -e ".[dev]"

# Install frontend deps
cd web && npm install && cd ..

# Run tests
pytest tests/ -v

# Dev mode (backend + frontend)
helios run -- your-command-here  # terminal 1
helios dashboard                 # terminal 2 → http://localhost:6767
```

## Docker

```bash
docker compose up --build
```

## Stretch Goals (parking lot)

- [ ] GPU/RAM charts in dashboard
- [ ] VS Code extension for one-click replay
- [ ] Signed snapshots (GPG/SSH)
- [ ] Windows support
- [ ] Binary distribution (PyInstaller / Nuitka)

---

**Helios** — *see everything your agent did, and undo it in one click.*