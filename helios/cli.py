"""Helios CLI — Typer entrypoint for `helios run` and `helios dashboard`."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from helios.backend import create_app, mount_frontend
from helios.recorder import Recorder
from helios.snapshot import SnapshotManager

app = typer.Typer(
    name="helios",
    help="Lightweight watchdog + replay tool for AI coding agents.",
    add_completion=False,
    pretty_exceptions_show_locals=False,
)
console = Console()


# ── `helios run` ────────────────────────────────────────────────────────────

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

    # ── 1. Snapshot ──────────────────────────────────────────────────
    try:
        snap = SnapshotManager(cwd)
    except Exception as e:
        console.print(f"[bold red]✘[/] Snapshot failed: {e}")
        raise typer.Exit(1)

    console.print("[bold green]⏳[/] Taking git snapshot …")
    snapshot_info = snap.snapshot()
    console.print(f"    Tagged → {snapshot_info.tag}")

    # ── 2. Recorder + event bus ──────────────────────────────────────
    recorder = Recorder(cwd)

    # Build FastAPI app so the dashboard can stream the same bus
    backend_app = create_app(cwd, recorder.bus, snap)
    mount_frontend(backend_app, cwd / "web")

    # ── 3. Start dashboard server in background thread ───────────────
    if not no_dashboard:
        import uvicorn

        server_thread = threading.Thread(
            target=lambda: uvicorn.run(
                backend_app,
                host="0.0.0.0",
                port=port,
                log_level="warning",
            ),
            daemon=True,
        )
        server_thread.start()
        console.print(Panel(
            f"[bold]Dashboard[/] → [link=http://localhost:{port}]http://localhost:{port}[/link]",
            title="🔆 Helios",
        ))
        time.sleep(0.5)

    # ── 4. Run the user's command ────────────────────────────────────
    console.print(f"[bold]▶[/] Running: {command}")
    t0 = time.monotonic()
    rc = recorder.trace_command(command)
    elapsed = time.monotonic() - t0

    # Signal recorder to stop
    recorder.running = False
    time.sleep(0.3)

    # ── 5. Summary table ─────────────────────────────────────────────
    events = recorder.bus.history()
    stats = _compute_stats(recorder, events)

    table = Table(title="Helios Run Summary")
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    table.add_row("Command", command)
    table.add_row("Exit code", str(rc))
    table.add_row("Elapsed", f"{elapsed:.2f}s")
    table.add_row("Events recorded", str(len(events)))
    table.add_row("Peak RSS", f"{stats['peak_rss_mb']:.1f} MB")
    table.add_row("Mean CPU", f"{stats['mean_cpu_pct']:.1f}%")
    console.print(table)

    # ── 6. Export self-contained HTML replay ──────────────────────────
    payload = json.dumps({
        "run_id": (run_id := time.strftime("run-%Y%m%d-%H%M%S")),
        "events": [e.serialise() for e in events],
        "stats": stats,
    })
    export_path = cwd / f"{run_id}.html"
    export_path.write_text(_build_html(run_id, payload), encoding="utf-8")
    console.print(f"[bold green]✔[/] Replay saved → {export_path}")

    # ── 7. Keep dashboard alive briefly ──────────────────────────────
    if not no_dashboard:
        console.print("\n[dim]Dashboard stays live for 30s… press Ctrl-C to exit.[/dim]")
        try:
            time.sleep(30)
        except KeyboardInterrupt:
            pass


# ── `helios dashboard` (standalone) ────────────────────────────────────────

@app.command()
def dashboard(
    port: int = typer.Option(6767, "--port", "-p", help="Dashboard port."),
):
    """Serve the replay dashboard (standalone, no active recording)."""
    import uvicorn

    web_dir = Path(__file__).resolve().parent.parent / "web"
    os.chdir(web_dir)
    console.print(Panel(f"[bold]Dashboard[/] → http://localhost:{port}"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="warning", reload=False)


# ── Helpers ────────────────────────────────────────────────────────────────

def _compute_stats(recorder: Recorder, events: list) -> dict[str, Any]:
    cpu = recorder._metrics["cpu"]
    rss = recorder._metrics["rss"]
    return {
        "peak_rss_mb": max(rss) if rss else 0.0,
        "mean_cpu_pct": round((sum(cpu) / len(cpu)), 1) if cpu else 0.0,
        "num_events": len(events),
    }


def _build_html(run_id: str, payload: str) -> str:
    """Self-contained HTML replay (no server needed)."""
    import html as _html

    safe_id = _html.escape(run_id)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>Helios Replay — {safe_id}</title>
<link href="https://cdn.jsdelivr.net/npm/tailwindcss@3/dist/tailwind.min.css" rel="stylesheet">
<style>body{{font-family:'JetBrains Mono',monospace;background:#0f172a;color:#e2e8f0;max-width:1060px;margin:0 auto;padding:24px}}
::-webkit-scrollbar{{width:6px}}::-webkit-scrollbar-thumb{{background:#334155;border-radius:3px}}</style>
</head><body>
<div id="app"></div>
<script src="https://cdn.jsdelivr.net/npm/preact@10/dist/preact.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/preact/hooks/dist/hooks.min.js"></script>
<script>
const DATA=JSON.parse({json.dumps(payload)});
const{{h,render}}=preact,{{useState,useEffect}}=preact.hooks;
function App(){{
  const[ev,setEv]=useState([]);
  useEffect(()=>setEv(DATA.events),[]);
  const icons={{"created":"+","modified":"~","deleted":"✕","start":"▶","done":"■"}};
  const colors={{"created":"text-green-400","modified":"text-yellow-400","deleted":"text-red-400"}};
  function badge(a){{
    const t=(a.action||"").toLowerCase();
    return h('span',{{className:(colors[t]||"text-slate-400")+"inline-block px-1.5 py-0.5 rounded text-xs font-semibold mr-2"}},(icons[t]||"·")+" "+t);
  }}
  return h('div',null,
    h('h1',{{className:"text-xl font-bold mb-4 text-cyan-400"}},"🔆 Helios Replay — "+DATA.run_id),
    h('div',{{className:"grid grid-cols-3 gap-4 mb-4"}},
      [["Events",DATA.stats.num_events],["Peak RSS",DATA.stats.peak_rss_mb.toFixed(1)+" MB"],["Mean CPU",DATA.stats.mean_cpu_pct.toFixed(1)+"%"]]
        .map(function(l,v){{
          return h('div',{{className:"bg-slate-900 rounded p-3 border border-slate-700"}},
            h('div',{{className:"text-xs text-slate-500 uppercase"}}),l)
            ,h('div',{{className:"text-lg font-bold"}}),v);
        }})),
    h('div',{{className:"bg-slate-900 rounded border border-slate-700 overflow-hidden"}},
      h('div',{{className:"p-2 text-sm text-slate-400 border-b border-slate-700"}},"Timeline"),
      h('div',{{className:"h-[60vh] overflow-y-auto p-2 space-y-1"}},
        ev.map(function(e,i){{
          var t=e.type;
          if(t==="file"){{
            return h('div',{{key:i,className:"flex gap-2 text-xs py-1.5 hover:bg-slate-800/50 rounded px-2 items-start"}}
              ,h('span',{{className:"text-slate-500 w-28 shrink-0"}},(new Date(e.ts*1000)).toISOString().slice(11,23))
              ,badge(e.body)
              ,h('span',{{className:"text-slate-300 text-sm font-mono"}},(e.body.path||"")));
          }}
          if(t==="cmd"){{
            var cmd=e.body.command, out=e.body.output, code=e.body.exit_code;
            return h('div',{{key:i,className:"flex gap-2 text-xs py-1.5 hover:bg-slate-800/50 rounded px-2 items-start"}}
              ,h('span',{{className:"text-slate-500 w-28 shrink-0"}},(new Date(e.ts*1000)).toISOString().slice(11,23))
              ,h('span',{{className:"text-cyan-400 w-20 shrink-0 font-semibold"}},"▶ cmd")
              ,h('div',{{className:"flex-1"}}
                ,cmd?h('pre',{{className:"bg-slate-950 rounded p-1.5 text-xs text-slate-200 overflow-x-auto"}},_raw(cmd))
                :null
                ,out?h('pre',{{className:"bg-slate-950/50 rounded p-1.5 text-xs text-slate-400 mt-0.5 overflow-x-auto"}},_raw(out))
                :null
                ,code!==undefined?h('span',{{className:"text-xs text-slate-500 mt-0.5"}},"exit "+code):null));
          }}
          if(t==="alert"){{
            return h('div',{{key:i,className:"flex gap-2 text-xs py-1.5 hover:bg-slate-800/50 rounded px-2"}}
              ,h('span',{{className:"text-amber-400"}},"⚠️")
              ,h('span',{{className:"text-amber-400"}},(e.body.msg||"")));
          }}
          return null;
        }})))),
    h('p',{{className:"text-xs text-slate-600 mt-4"}},"Standalone replay — no server needed.");
}}
function _raw(s){{var d=document.createElement('div');d.textContent=s;return d.innerHTML;}}
render(h(App),document.body);
</script></body></html>"""

import uvicorn  # deferred import for command import speed