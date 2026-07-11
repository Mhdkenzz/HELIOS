# Configuration

## helios.toml

Create a `helios.toml` in your project root. All fields are optional.

```toml
[helios]
host = "0.0.0.0"
port = 6767
dry_run = false
debounce_ms = 50
max_events = 50000

# Deny dangerous commands (takes priority over allow)
deny_commands = ["rm -rf /", "git push --force"]

# Only allow specific commands (leave empty to allow all non-denied)
allow_commands = ["npm", "node", "python", "pip"]

# Auth for /rollback endpoint
rollback_token = ""

# UI customization
title = "Helios Dashboard"
theme = "dark"
accent_color = "#60a5fa"
font_family = "JetBrains Mono, monospace"

# Logging
log_level = "info"
log_file = ""
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `HELIOS_HOST` | Bind address | `0.0.0.0` |
| `HELIOS_PORT` | Dashboard port | `6767` |
| `HELIOS_DRY_RUN` | Dry-run mode | `0` |
| `HELIOS_DENY` | Comma-separated deny list | (empty) |
| `HELIOS_ALLOW` | Comma-separated allow list | (empty) |
| `HELIOS_ROLLBACK_TOKEN` | Auth token for rollback | (empty) |
| `HELIOS_THEME` | UI theme: `dark`, `light`, `auto` | `dark` |
| `HELIOS_LOG_LEVEL` | Logging level | `info` |

## Per-Project vs Global

Helios searches upward from the current directory for `helios.toml`. The first one found wins. This lets you have per-project settings while keeping a global config in your home directory if desired.

## Security Defaults

By default:
- No commands are denied (you opt into restrictions)
- The `/rollback` endpoint requires no auth (localhost-only in dev)
- The `/diff` endpoint validates paths stay within the project root