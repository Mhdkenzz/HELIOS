# Troubleshooting

## "Not a git repository"

Helios requires your project to be inside a Git repo. Initialize one:

```bash
cd /path/to/your/project
git init
git add -A
git commit -m "Initial commit"
```

## Dashboard shows "No replay data"

This happens when the frontend can't connect to WebSocket at `/ws`. Check:
1. The backend is running: `curl http://localhost:6767/info`
2. No firewall blocking WebSocket connections
3. If using Docker, ensure ports are mapped: `-p 6767:6767`

## "protected files changed" error on rollback

Helios prevents rollback if `package.json`, `LICENSE`, `helios.toml`, or `pyproject.toml` have been modified since the snapshot. To proceed:
1. Commit or stash your changes to protected files first
2. Or delete the snapshot tag and create a new one

## High memory usage

The recorder stores all events in memory. For long-running processes:
- Set `max_events = 10000` in `helios.toml`
- Prune old snapshots regularly: `helios prune --keep 5`

## Permission denied on Windows (PTY)

Windows requires ConPTY support. Install it:

```bash
pip install helios[windows-pty]
```

If issues persist, Helios falls back to standard subprocess mode (no PTY).

## Terminal output not showing in replay

Ensure your command produces output to stdout/stderr. Some programs buffer output when not connected to a terminal. Use `python -u` for Python scripts.

## "ModuleNotFoundError: No module named 'helios'"

Helios may not be installed correctly. Reinstall:

```bash
pipx reinstall helios
# or
pip install --force-reinstall helios
```

## Tests failing

```bash
# Ensure all deps are installed
pip install -e ".[dev]"

# Run with verbose output
pytest tests/ -v --tb=long

# Reset test state
git clean -fdx tests/
```