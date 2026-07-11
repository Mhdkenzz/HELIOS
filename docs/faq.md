# FAQ

### What is Helios?
A lightweight watchdog and replay tool for AI coding agents. It records what your agent does, streams events to a web dashboard, and generates standalone HTML replays.

### How does it work?
Helios wraps your command execution, captures terminal I/O via PTY, monitors file system changes with watchdog, and streams all events over WebSocket to a React dashboard.

### Why "Helios"?
The sun god who sees everything. Just like Helios watches your agent's every move.

### Is the data sent anywhere?
**No.** Everything runs locally. The dashboard is served from your own machine. No cloud, no telemetry.

### Can I use it with Claude Code / Cursor / Cline?
Yes. Wrap your agent command: `helios run -- claude-code --your-flags`. Any terminal-based agent works.

### How do I delete old replays?
Use `helios prune --keep N` to keep only the N most recent snapshots and their replay files.

### Is it safe?
Helios runs commands exactly as given — no shimming or interception. The deny-list feature lets you block specific commands. The rollback endpoint requires authentication.

### Can I contribute?
Yes! See [Contributing](contributing.md) for guidelines.

### I found a bug
Please open an issue on GitHub with:
- Helios version (`helios info`)
- Python version
- OS and version
- Steps to reproduce
- Any error messages

### Does it work on Windows?
Mostly. PTY support requires `pywinpty` (`pip install helios[windows-pty]`). Without it, Helios falls back to standard subprocess mode.

### How much disk space does it use?
Each replay is a single HTML file (~10–50 KB). Snapshots are just Git tags. You can prune old ones with `helios prune`.

### Can I customize the dashboard?
Yes. See `helios.toml.example` for theme colors, fonts, and other options.