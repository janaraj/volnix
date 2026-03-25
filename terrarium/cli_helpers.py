"""Shared Rich formatting helpers for the Terrarium CLI.

Provides a singleton console, typed formatting functions for plans,
runs, entities, scorecards, comparisons, events, and ledger entries,
plus convenience printers and an async app-context manager.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

# ---------------------------------------------------------------------------
# Shared console instance
# ---------------------------------------------------------------------------

console = Console()


# ---------------------------------------------------------------------------
# Convenience printers
# ---------------------------------------------------------------------------


def print_error(message: str) -> None:
    """Print a red error message."""
    console.print(f"[bold red]Error:[/bold red] {message}")


def print_success(message: str) -> None:
    """Print a green success message."""
    console.print(f"[bold green]OK:[/bold green] {message}")


def print_warning(message: str) -> None:
    """Print a yellow warning message."""
    console.print(f"[bold yellow]Warning:[/bold yellow] {message}")


def print_info(message: str) -> None:
    """Print a blue informational message."""
    console.print(f"[bold blue]Info:[/bold blue] {message}")


# ---------------------------------------------------------------------------
# Structured output helpers
# ---------------------------------------------------------------------------


def print_json(data: dict | list) -> None:
    """Pretty-print a JSON-serialisable object with syntax highlighting."""
    console.print(Syntax(json.dumps(data, indent=2, default=str), "json"))


def print_plan(plan_text: str) -> None:
    """Display plan text inside a Rich panel."""
    console.print(Panel(plan_text, title="World Plan", border_style="blue"))


def print_report(report: dict, fmt: str = "markdown") -> None:
    """Render a report dict.  JSON mode uses syntax highlighting."""
    if fmt == "json":
        print_json(report)
        return

    # Markdown / default: iterate top-level sections
    for section, content in report.items():
        if isinstance(content, dict):
            console.print(
                Panel(
                    json.dumps(content, indent=2, default=str),
                    title=section,
                    border_style="cyan",
                )
            )
        elif isinstance(content, list):
            table = Table(title=section)
            if content and isinstance(content[0], dict):
                for col in content[0]:
                    table.add_column(str(col))
                for row in content:
                    table.add_row(*(str(row.get(c, "")) for c in content[0]))
            else:
                table.add_column("Value")
                for item in content:
                    table.add_row(str(item))
            console.print(table)
        else:
            console.print(f"[bold]{section}:[/bold] {content}")


# ---------------------------------------------------------------------------
# Table formatters
# ---------------------------------------------------------------------------


def format_run_table(runs: list[dict]) -> Table:
    """Format a list of run dicts as a Rich table."""
    table = Table(title="Runs")
    table.add_column("Run ID", style="cyan")
    table.add_column("Tag")
    table.add_column("Mode")
    table.add_column("Status")
    table.add_column("Created")
    for r in runs:
        table.add_row(
            str(r.get("run_id", "")),
            str(r.get("tag", "") or ""),
            str(r.get("mode", "")),
            str(r.get("status", "")),
            str(r.get("created_at", "")),
        )
    return table


def format_entity_table(entities: list[dict], entity_type: str) -> Table:
    """Format entities of a given type as a Rich table."""
    table = Table(title=f"Entities: {entity_type}")
    if entities and isinstance(entities[0], dict):
        for col in entities[0]:
            table.add_column(str(col))
        for entity in entities:
            table.add_row(*(str(entity.get(c, "")) for c in entities[0]))
    else:
        table.add_column("Value")
        for entity in entities:
            table.add_row(str(entity))
    return table


def format_ledger_table(entries: list[Any]) -> Table:
    """Format ledger entries as a Rich table."""
    table = Table(title="Ledger Entries")
    table.add_column("ID", style="dim")
    table.add_column("Type")
    table.add_column("Timestamp")
    table.add_column("Actor")
    table.add_column("Details", max_width=60)
    for entry in entries:
        if hasattr(entry, "model_dump"):
            d = entry.model_dump(mode="json")
        elif isinstance(entry, dict):
            d = entry
        else:
            d = {"id": str(entry)}
        table.add_row(
            str(d.get("entry_id", d.get("id", "")))[:12],
            str(d.get("entry_type", "")),
            str(d.get("timestamp", ""))[:19],
            str(d.get("actor_id", "")),
            str(d.get("details", d.get("data", "")))[:60],
        )
    return table


def format_scorecard(scorecard: dict) -> Panel:
    """Render a scorecard dict as a Rich panel with nested tables."""
    lines: list[str] = []
    for section, data in scorecard.items():
        lines.append(f"[bold]{section}[/bold]")
        if isinstance(data, dict):
            for key, val in data.items():
                if isinstance(val, float):
                    lines.append(f"  {key}: {val:.2f}")
                else:
                    lines.append(f"  {key}: {val}")
        elif isinstance(data, list):
            for item in data:
                lines.append(f"  - {item}")
        else:
            lines.append(f"  {data}")
        lines.append("")
    return Panel("\n".join(lines), title="Scorecard", border_style="green")


def format_health_table(results: dict[str, dict]) -> Table:
    """Format engine health results as a Rich table."""
    table = Table(title="Engine Health")
    table.add_column("Engine")
    table.add_column("Started")
    table.add_column("Healthy")
    table.add_column("Error")
    for engine_name, info in results.items():
        started = info.get("started", False)
        healthy = info.get("healthy", False)
        error = info.get("error", "")
        started_str = "[green]Yes[/green]" if started else "[red]No[/red]"
        healthy_str = "[green]Yes[/green]" if healthy else "[red]No[/red]"
        error_str = f"[red]{error}[/red]" if error else ""
        table.add_row(engine_name, started_str, healthy_str, error_str)
    return table


def format_diff(comparison: dict) -> str:
    """Format a comparison dict as a human-readable string.

    Delegates to RunComparator.format_comparison when available,
    otherwise returns a JSON dump.
    """
    try:
        from terrarium.runs.comparison import RunComparator

        # RunComparator.format_comparison is an instance method but
        # only uses *comparison*, not self._artifact_store, so we can
        # call it from a throwaway instance with a None store.
        comparator = RunComparator(artifact_store=None)  # type: ignore[arg-type]
        return comparator.format_comparison(comparison)
    except Exception:
        return json.dumps(comparison, indent=2, default=str)


def format_event_line(event: dict) -> str:
    """Format a single event dict as a one-line summary."""
    ts = str(event.get("timestamp", ""))[:19]
    etype = event.get("event_type", "?")
    actor = event.get("actor_id", "")
    action = event.get("action", "")
    return f"[dim]{ts}[/dim]  {etype}  actor={actor}  action={action}"


# ---------------------------------------------------------------------------
# File output helper
# ---------------------------------------------------------------------------


def write_output(content: str, output_path: Path | None) -> None:
    """Write *content* to *output_path* (or print it if None)."""
    if output_path:
        output_path.write_text(content)
        print_success(f"Written to {output_path}")
    else:
        console.print(content)


# ---------------------------------------------------------------------------
# Async app context manager
# ---------------------------------------------------------------------------


@asynccontextmanager
async def app_context(env: str = "development") -> AsyncIterator[Any]:
    """Yield a fully-started TerrariumApp, stopping it on exit.

    Args:
        env: Configuration environment name. Maps to
            ``terrarium.{env}.toml`` overlay file.

    Usage::

        async with app_context() as terrarium:
            compiler = terrarium.registry.get("world_compiler")
            ...
    """
    from terrarium.app import TerrariumApp
    from terrarium.config.loader import ConfigLoader

    config = ConfigLoader(env=env).load()
    terrarium_app = TerrariumApp(config)
    try:
        await terrarium_app.start()
        yield terrarium_app
    finally:
        await terrarium_app.stop()
