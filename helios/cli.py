"""
Helios CLI — Typer-based command entry point.

Commands:
  run       Run a command under Helios monitoring
  dashboard Start the web dashboard (backend + frontend)
  prune     Remove old snapshots and replay files
  info      Show version and config summary
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import SITE, version
from .recorder import EventBus, Recorder
from .snapshot import SnapshotManager

app = typer.Typer(
    name="helios",
    help="Watchdog + replay for AI coding agents.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

# ── Helpers ──────────────────────────────────────────────────────────────────


def _get_config_path() -> Path:
    """Return the path to helios.toml (searched upward from cwd)."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / "helios.toml"
        if candidate.is_file():
            return candidate
    return cwd / "helios.toml"


def _load_config(config_path: Path | None = None) -> dict:
    """Load configuration from a TOML file (placeholder)."""
    if config_path and config_path.is_file():
        try:
            import tomllib

            with open(config_path, "rb") as f:
                return tomllib.load(f)
        except Exception:
            pass
    return {}


def _version() -> str:
    return f"Helios {version()}"


# ── Commands ─────────────────────────────────────────────────────────────────


@app.command()
def run(
    command: list[str] = typer.Argument(
        ..., help="Shell command to run and monitor (e.g. 'npm install')."
    ),
    config: Path = typer.Option(
        None, "--config", "-c", help="Path to helios.toml config file."
    ),
) -> None:
    """Run a command under Helios monitoring."""
    cfg = _load_config(config)
    console.print(
        Panel.fit(
            f"[bold]Running:[/bold] {' '.join(command)}",
            title=_version(),
        )
    )
    bus = EventBus()
    snap = SnapshotManager(Path.cwd())
    rec = Recorder(Path.cwd(), bus, cfg)
    try:
        result = rec.trace_command(command)
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)

    if result["exit_code"] == 0:
        console.print("[bold green]\u2713 Command completed successfully.[/]")
    else:
        console.print(
            f"[bold red]\u2717 Command failed[/] (exit {result['exit_code']})"
        )
        raise typer.Exit(result["exit_code"])


@app.command()
def dashboard(
    port: int = typer.Option(6767, "--port", "-p", help="Port for the web dashboard."),
    config: Path = typer.Option(
        None, "--config", "-c", help="Path to helios.toml config file."
    ),
) -> None:
    """Start the web dashboard (backend + frontend)."""
    from helios.backend import create_app

    import uvicorn

    cfg = _load_config(config)
    console.print(
        Panel.fit(
            f"[bold]Dashboard[/bold] starting on :{port}",
            title=_version(),
        )
    )
    app_obj = create_app(Path.cwd(), EventBus(), None, cfg)
    uvicorn.run(app_obj, host="0.0.0.0", port=port, log_level="info")


@app.command()
def info() -> None:
    """Show version and config summary."""
    table = Table(title=_version())
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Version", version())
    table.add_row("Config file", str(_get_config_path()))
    table.add_row("Python", sys.version.split()[0])
    table.add_row("Home", str(Path.home()))
    console.print(table)


@app.command()
def prune(
    keep: int = typer.Option(
        10, "--keep", "-k", help="Number of most recent snapshots to keep."
    ),
    dry: bool = typer.Option(
        False, "--dry-run", "-d", help="Show what would be pruned without deleting."
    ),
) -> None:
    """Remove old snapshots and replay files."""
    snap = SnapshotManager(Path.cwd())
    tags = snap.list_tags()
    if len(tags) <= keep:
        console.print(
            f"[green]Nothing to prune \u2014 {len(tags)} snapshots <= {keep}[/]"
        )
        return
    to_remove = tags[keep:]
    if dry:
        console.print(
            f"[yellow]Dry run \u2014 would prune {len(to_remove)} snapshots:[/]"
        )
        for tag, ts in to_remove:
            console.print(f"  [dim]{tag}[/] ({ts})")
        raise typer.Exit()
    snap.purge(keep)
    console.print(f"[bold green]\u2713 Pruned {len(to_remove)} snapshots[/]")


if __name__ == "__main__":
    app()