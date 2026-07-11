# Installation

## Prerequisites

- Python 3.10 or higher
- Git
- pip, pipx, or conda

## Install with pipx (recommended)

```bash
pipx install helios
```

This installs the Helios CLI with the bundled web UI — no Node.js or npm required.

## Install with pip

```bash
pip install helios
```

Or in development mode:

```bash
git clone https://github.com/yourorg/helios.git
cd helios
pip install -e ".[dev]"
```

## Verify

```bash
helios info
# Should display version, config path, and Python version
```

## Docker

```bash
docker compose up --build
# Backend on :6767, frontend served from the same container
```

## Platform Support

| Platform | Support |
|----------|---------|
| Linux    | Full — uses stdlib `pty` or `pexpect` |
| macOS    | Full — uses stdlib `pty` or `pexpect` |
| Windows  | Partial — uses `pywinpty`/ConPTY if installed, falls back to subprocess |

For Windows PTY support:

```bash
pip install helios[windows-pty]
```