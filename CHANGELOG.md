# Changelog

All notable changes to Helios are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-07-12

### Added
- Embedded web UI — no separate `npm install` required by end users; frontend is bundled into the Python wheel via `copy_web.py`
- `helios prune --keep N` command to remove old snapshot tags and replay HTML files
- `--dry-run` flag on `helios run` to record events without executing commands
- Configurable deny-list and allow-list for commands in `helios.toml`
- Authentication token on `/rollback` endpoint (`X-Rollback-Token` header)
- Path traversal guard on `/diff` endpoint
- Dashboard branding via `helios.toml` (theme, accent color, logo, font)
- `helios.toml.example` with documented examples for all config options
- PR labeler workflow (`.github/labeler.yml`)
- Multi-platform CI: Ubuntu, macOS, Windows + Python 3.10–3.12

### Changed
- **BREAKING:** Removed `ptyprocess` dependency (unmaintained); replaced with cross-platform PTY using `pexpect` or stdlib fallback
- **BREAKING:** Command is now passed as `List[str]` to subprocess — removed all `shell=True` usage
- Upgraded Vite to v6 with `@vitejs/plugin-react`
- Dashboard uses dark mode by default with CSS custom properties
- Build sizes reduced via Vite tree-shaking

### Fixed
- **Critical:** Shell injection vulnerability in recorder (removed `shell=True`)
- **Critical:** Missing auth on `/rollback` endpoint
- **High:** Path traversal vulnerability in `/diff` endpoint
- **High:** Race condition in `EventBus._on_event` callback iteration (now lock-protected)
- **Medium:** `asyncio.get_event_loop()` called from worker thread — replaced with stored loop reference
- **Medium:** `@dataclass` mixed with pydantic `Field()` causing `ValueError` in `Body` model
- Removed deprecated `@app.on_event("startup")` — uses FastAPI `lifespan` context manager instead
- Fixed `tty_fd` AttributeError on systems without PTY support
- Fixed `on_close` callback path for clean WebSocket teardown
- Removed 17 unused imports across all modules
- Fixed Makefile dev target uvicorn path (`helios.cli:app` → `helios.backend:create_app`)
- Added `conftest.py` with pytest-asyncio auto mode

### Removed
- `ptyprocess` dependency (last released 2021, incompatible with Python 3.12+)
- Duplicate `EventTypes` enum from `snapshot.py`
- `_env_is_allowed()` dead method from `_Tracer`

## [0.1.0] - 2026-07-03

### Added
- Initial MVP release: watchdog + replay tool for AI coding agents
- Subprocess execution with PTY capture (Linux/macOS)
- File system event monitoring via watchdog
- Web dashboard with WebSocket event streaming
- Snapshot creation with Git tags
- Rollback with protected file guards
- 13 pytest tests with 100% pass rate