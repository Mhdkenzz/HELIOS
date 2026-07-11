# Coding Checklist — Helios Tightening
# Tracked in order of dependency: infrastructure → core → UI → polish.

- [x] 1. One-step install: embed web UI as package data (pyproject.toml + restructure)
- [x] 2. Hard stops: deny/allow-lists + dry-run flag (config + recorder + CLI)
- [x] 3. Full PTY on Windows: pywinpty / ConPTY fallback
- [x] 4. Debounce file floods: 50ms batching + virtual scroll frontend
- [x] 5. Branding switch: helios.toml logo + colors + dark mode
- [x] 6. Snapshot housekeeping: helios prune --keep N
- [x] 7. README polish: badges, uvicorn path fix, CI section
- [ ] Verify: run tests + build