# Architecture

## Overview

Helios is composed of a Python backend, a React web frontend, and a CLI layer built with Typer.

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   CLI        │────▶│   Backend    │────▶│   Git Repo   │
│  (Typer)     │     │  (FastAPI)   │     │  (watchdog)  │
└──────┬───────┘     └──────┬───────┘     └──────────────┘
       │                    │
       │                    ▼
       │            ┌──────────────┐
       │            │ EventBus     │
       │            │ (thread-safe)│
       │            └──────┬───────┘
       │                   │
       ▼                   ▼
┌──────────────┐   ┌──────────────┐
│  Snapshot    │   │  WebSocket   │
│  Manager     │   │  Server      │
│              │   │  (/ws)       │
└──────────────┘   └──────┬───────┘
                          │
                          ▼
                  ┌──────────────┐
                  │  Web Frontend │
                  │  (React + Vite)│
                  └──────────────┘
```

## Components

### CLI (`helios/cli.py`)
- Built with [Typer](https://typer.tiangolo.com/)
- Commands: `run`, `dashboard`, `prune`, `info`
- Reads configuration from `helios.toml` or environment variables

### Recorder (`helios/recorder.py`)
- **EventBus**: Thread-safe publish/subscribe bus with asyncio support
- **Recorder**: Subprocess tracer with PTY capture, file-watch, and metrics
- **FileMonitor**: Debounced watchdog observer (50ms windows)

### Backend (`helios/backend.py`)
- Built with [FastAPI](https://fastapi.tiangolo.com/)
- WebSocket endpoint at `/ws` streams events to the frontend
- REST endpoints for diff, rollback, and static file serving
- Lifespan event handler stores the asyncio event loop

### Snapshot Manager (`helios/snapshot.py`)
- Git tagging with `helios-YYYYMMDDTHHMMSSZ` format
- Guarded rollback protects `helios.toml`, `package.json`, `LICENSE`, `pyproject.toml`
- Prune command removes old snapshots and replay HTML files

### Frontend (`web/`)
- React + TypeScript with Vite build
- Tailwind CSS for styling with dark mode
- Virtual-scrolled timeline for efficient rendering
- Embedded in the Python package for single-install distribution

## Event Flow

1. CLI command starts a `Recorder` attached to an `EventBus`
2. Recorder spawns the subprocess and captures I/O via PTY
3. Watchdog monitors the file system for changes
4. Events are published to the `EventBus`
5. `EventBus` pushes events to all subscribers (WebSocket, log, etc.)
6. Frontend receives events via WebSocket and renders them in real-time