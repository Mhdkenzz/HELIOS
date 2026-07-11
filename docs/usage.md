# Usage Guide

## Commands

### `helios run`
Run a command under Helios monitoring.

```bash
helios run -- <command>

# With flags after the double dash:
helios run -- --flag1 value1 --flag2 value2
```

### `helios run --dry-run`
Record events without executing the command. Safe preview mode — no subprocess is spawned.

```bash
helios run --dry-run -- dangerous-command
```

### `helios dashboard`
Start the web dashboard (FastAPI + embedded frontend).

```bash
helios dashboard                # default :6767
helios dashboard --port 8080    # custom port
```

### `helios prune`
Remove old snapshots and replay HTML files.

```bash
helios prune --keep 10          # keep the 10 most recent
helios prune --keep 5 --dry-run # preview what would be deleted
```

### `helios info`
Show version, config file path, and environment info.

```bash
helios info
```

## Configuration

Configuration is read from (in order of priority):
1. Command-line flags
2. Environment variables (`HELIOS_*`)
3. `helios.toml` in the current or nearest parent directory

See `helios.toml.example` for all available options.

## How Recording Works

1. **Snapshot**: A Git tag (`helios-YYYYMMDDTHHMMSSZ`) is created at the current HEAD
2. **Execution**: The command runs inside a PTY (pseudo-terminal) for full I/O capture
3. **Monitoring**: Watchdog tracks file changes; metrics sampler captures CPU/RAM
4. **Replay**: Events are streamed via WebSocket to the dashboard and saved as a JSON timeline
5. **Exit**: The recorder stops and the final event log is persisted

## Exit Codes

| Code | Meaning |
|------|---------|
| 0    | Success |
| 1    | Command failed |
| 2    | Helios internal error |
| 3    | Snapshot/rollback error |