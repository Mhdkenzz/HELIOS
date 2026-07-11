from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.snapshot import SnapshotManager
from core.recorder import Recorder, TimelineEvent

app = typer.Typer(
    name="helios",
    help="Lightweight watchdog + replay tool for AI coding agents.",
    add_completion=False,
)
console = Console()


@app.command()
def run(
    command: str = typer.Argument(
        ...,
        help="Shell command to run under Helios observation.",
    ),
    port: int = typer.Option(6767, "--port", "-p", help="Dashboard port."),
    no_dashboard: bool = typer.Option(False, "--no-dashboard", help="Skip web UI."),
):
    """Run a command under Helios observation and record a timeline."""
    cwd = Path.cwd()
    snap = SnapshotManager(cwd)
    recorder = Recorder(cwd)

    # ── 1. Git-level snapshot ──────────────────────────────────────────
    console.print("[bold green]⏳[/] Taking git snapshot …")
    snap.take_snapshot()

    # ── 2. Start async recorder ────────────────────────────────────────
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    task = loop.create_task(recorder.watch())

    # ── 3. Run the user's command ──────────────────────────────────────
    console.print(f"[bold]▶[/] Running: {command}")
    t0 = time.monotonic()
    exit_code = os.system(command) >> 8  # nosec: user-supplied cmd
    elapsed = time.monotonic() - t0

    # ── 4. Flush & stop ────────────────────────────────────────────────
    recorder.running = False
    loop.run_until_complete(asyncio.sleep(0.5))
    task.cancel()
    loop.close()

    # ── 5. Summary ─────────────────────────────────────────────────────
    stats = recorder.summarise()
    table = Table(title="Helios Run Summary")
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    table.add_row("Command", command)
    table.add_row("Exit code", str(exit_code))
    table.add_row("Elapsed", f"{elapsed:.2f}s")
    table.add_row("Events recorded", str(len(recorder.events)))
    table.add_row("Peak RSS (MB)", f"{stats['peak_rss_mb']:.1f}")
    table.add_row("Mean CPU %", f"{stats['mean_cpu_pct']:.1f}")
    console.print(table)

    # ── 6. Export HTML replay ──────────────────────────────────────────
    run_id = time.strftime("run-%Y%m%d-%H%M%S")
    export_path = cwd / f"{run_id}.html"
    html = _build_html(run_id, recorder.events, stats)
    export_path.write_text(html, encoding="utf-8")
    console.print(f"[bold green]✔[/] Replay saved → {export_path}")


@app.command()
def dashboard(
    port: int = typer.Option(6767, "--port", "-p", help="Dashboard port."),
):
    """Serve the replay dashboard (standalone)."""
    from http.server import HTTPServer
    from core.recorder import TimelineEvent

    # Serve static web/ files
    web_dir = Path(__file__).resolve().parent.parent / "web"
    os.chdir(web_dir)

    class Handler(_SimpleHTTPRequestHandlerEtag):
        def end_headers(self):
            # Allow WebSocket upgrade on /ws
            self.send_header("Access-Control-Allow-Origin", "*")
            super().end_headers()

    console.print(Panel(f"[bold]Dashboard[/] → http://localhost:{port}"))
    HTTPServer(("", port), Handler).serve_forever()


# ── Helpers ──────────────────────────────────────────────────────────────

def _build_html(run_id: str, events: list[dict], stats: dict) -> str:
    """Minimal self-contained HTML replay (no server needed)."""
    import json
    import html as html_mod

    payload = json.dumps({"run_id": run_id, "events": events, "stats": stats})
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>Helios Replay — {html_mod.escape(run_id)}</title>
<style>
  body{{font-family:system-ui,sans-serif;max-width:960px;margin:2em auto;background:#0f172a;color:#e2e8f0}}
  h1{{color:#38bdf8}} table{{border-collapse:collapse;width:100%}}
  th,td{{border:1px solid #334155;padding:.5rem;text-align:left}}
  th{{background:#1e293b}} .ok{{color:#4ade80}} .warn{{color:#fbbf24}}
</style></head><body>
<h1>🔆 Helios Replay — {html_mod.escape(run_id)}</h1>
<div id="app"></div>
<script>const DATA={payload};</script>
<script src="https://cdn.jsdelivr.net/npm/preact@10/dist/preact.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/preact/hooks/dist/hooks.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/preact/compat/dist/compat.min.js"></script>
<script>
const {{h, render}} = preact;
const {{useState,useEffect}} = preactHooks;
function App(){{
  const [ev,setEv]=useState([]);
  useEffect(()=>{{setEv(DATA.events)}},[]);
  return h('div',null,
    h('p',null,'Run: '+DATA.run_id),
    h('table',null,
      h('thead',null,h('tr',null,['Time','Type','Detail'].map(c=>h('th',null,c)))),
      h('tbody',null,ev.map((e,i)=>h('tr',{{key:i}},
        [new Date(e.ts).toISOString().slice(11,23),e.type,e.detail||''].map(v=>h('td',null,v)))))
    );
}}
render(h(App),document.getElementById('app'));
</script>
</body></html>"""


class _SimpleHTTPRequestHandlerEtag(
    __import__("http.server", fromlist=["SimpleHTTPRequestHandler"]).SimpleHTTPRequestHandler
):
    """Serve files from cwd with basic CORS headers."""