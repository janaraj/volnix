Now I have a thorough understanding of the entire codebase. Let me produce the comprehensive implementation plan.

---

## Comprehensive Implementation Plan: Terrarium CLI (15 Commands)

### Overview

The plan covers three files:
1. **`terrarium/cli.py`** -- Complete rewrite with 15 implemented commands + 5 deferred stubs
2. **`terrarium/cli_helpers.py`** -- New shared formatting module for Rich output
3. **`tests/cli/test_cli.py`** -- Full test suite using Typer's CliRunner

---

### Architecture Decisions

**Async Pattern**: Every command follows the same async wrapper pattern. The synchronous Typer command function calls `asyncio.run(_impl(...))`. The async `_impl` function instantiates `TerrariumApp`, calls `start()`, does work in a `try` block, and calls `stop()` in `finally`. Several commands (like `create`, `plan`) that only need the world compiler do NOT need the full app bootstrap -- they need the compiler engine specifically, but the app.start() is the only supported bootstrap path that wires everything correctly.

**Config Loading**: Every command loads config via `ConfigLoader().load()` at the top. This respects TOML layering and env vars.

**Error Boundary**: Every `_impl` function wraps its core logic in `try/except TerrariumError`, printing user-friendly messages via Rich and raising `typer.Exit(1)`.

**Output**: All output goes through a shared `Console()` instance from `terrarium/cli_helpers.py`. Tables, panels, and colored text from Rich.

**`--format` options**: Commands that support `--format json` emit `json.dumps(result, indent=2)` directly. Markdown and CLI formats use Rich rendering.

---

### File 1: `terrarium/cli_helpers.py`

This new module provides shared formatting utilities so commands don't duplicate output logic.

**Contents**:

```
Module: terrarium/cli_helpers.py

Imports:
  - json
  - rich.console.Console
  - rich.table.Table
  - rich.panel.Panel
  - rich.syntax.Syntax
  - rich.text.Text
  - rich.markdown.Markdown

Global:
  console = Console()

Functions:

1. print_error(message: str) -> None
   console.print(f"[bold red]Error:[/bold red] {message}")

2. print_success(message: str) -> None
   console.print(f"[bold green]OK:[/bold green] {message}")

3. print_warning(message: str) -> None
   console.print(f"[bold yellow]Warning:[/bold yellow] {message}")

4. print_json(data: dict | list) -> None
   console.print(Syntax(json.dumps(data, indent=2, default=str), "json"))

5. print_plan(plan_text: str) -> None
   console.print(Panel(plan_text, title="World Plan", border_style="blue"))

6. print_report(report: dict, fmt: str = "markdown") -> None
   If fmt == "json": print_json(report)
   If fmt == "markdown": render report sections as Rich Panels + Tables

7. format_run_table(runs: list[dict]) -> Table
   Create Rich Table with columns: Run ID, Tag, Mode, Status, Created
   Add rows from run dicts
   Return Table

8. format_entity_table(entities: list[dict], entity_type: str) -> Table
   Create Rich Table with column names from entity keys
   Return Table

9. format_ledger_table(entries: list) -> Table
   Create Rich Table with columns: ID, Type, Timestamp, Actor, Details
   Return Table

10. format_scorecard(scorecard: dict) -> Panel
    Render scorecard as Rich Panel with nested tables

11. format_health_table(results: dict[str, dict]) -> Table
    Columns: Engine, Started, Healthy, Error
    Color rows: green for healthy, red for unhealthy

12. format_diff(comparison: dict) -> str
    Delegate to RunComparator.format_comparison() for CLI format
    For markdown: wrap in markdown blocks

13. write_output(content: str, output_path: Path | None) -> None
    If output_path: write to file, print confirmation
    Else: console.print(content)

14. app_context() -> async context manager
    Yields a started TerrariumApp instance.
    Usage:
      async with app_context() as terrarium:
          ...
    Internally: loads config, creates TerrariumApp, starts it, yields it,
    stops it in finally block.
    Implementation:
      from contextlib import asynccontextmanager
      @asynccontextmanager
      async def app_context():
          config = ConfigLoader().load()
          terrarium = TerrariumApp(config)
          try:
              await terrarium.start()
              yield terrarium
          finally:
              await terrarium.stop()
```

---

### File 2: `terrarium/cli.py` -- Full Implementation

**Module-level structure**:

```python
"""Terrarium CLI -- command interface for managing programmable worlds."""

import asyncio
import json
import shutil
from pathlib import Path
from typing import Annotated, Optional

import typer

from terrarium.cli_helpers import (
    app_context,
    console,
    format_diff,
    format_entity_table,
    format_health_table,
    format_ledger_table,
    format_run_table,
    format_scorecard,
    print_error,
    print_json,
    print_plan,
    print_report,
    print_success,
    print_warning,
    write_output,
)
from terrarium.core.errors import TerrariumError

app = typer.Typer(
    name="terrarium",
    help="Programmable worlds for artificial intelligence.",
    no_args_is_help=True,
)
```

---

#### Command 1: `create`

**Purpose**: Natural language description becomes a YAML world definition file.

```
Typer Signature:
@app.command()
def create(
    description: Annotated[str, typer.Argument(help="Natural language description of the world")],
    reality: Annotated[str, typer.Option("--reality", "-r", help="Reality preset: ideal, messy, hostile")] = "messy",
    fidelity: Annotated[str, typer.Option("--fidelity", help="Fidelity mode: auto, strict, exploratory")] = "auto",
    mode: Annotated[str, typer.Option("--mode", "-m", help="World mode: governed, ungoverned")] = "governed",
    seed: Annotated[Optional[list[str]], typer.Option("--seed", help="Seed data files (repeatable)")] = None,
    override: Annotated[Optional[list[str]], typer.Option("--override", help="Reality condition overrides (repeatable, key=value)")] = None,
    overlay: Annotated[Optional[list[str]], typer.Option("--overlay", help="Additional overlay files (repeatable)")] = None,
    output: Annotated[Path, typer.Option("--output", "-o", help="Output path for the YAML world definition")] = Path("./world.yaml"),
) -> None:
    """Create a new world from a natural language description."""
    asyncio.run(_create_impl(description, reality, fidelity, mode, seed, override, overlay, output))
```

**Async Implementation `_create_impl`**:

```
async def _create_impl(description, reality, fidelity, mode, seed, override, overlay, output):
    try:
        async with app_context() as terrarium:
            compiler = terrarium.registry.get("world_compiler")
            
            # Compile from NL
            console.print(f"[bold]Creating world from description...[/bold]")
            plan = await compiler.compile_from_nl(
                description=description,
                reality=reality,
                behavior="dynamic",   # default; user doesn't set this at create time
                fidelity=fidelity,
            )
            
            # Serialize plan to YAML
            from terrarium.engines.world_compiler.plan_reviewer import PlanReviewer
            reviewer = PlanReviewer()
            yaml_str = reviewer.to_yaml(plan)
            
            # Write to output file
            output.write_text(yaml_str)
            print_success(f"World definition written to {output}")
            
            # Show plan summary
            print_plan(reviewer.format_plan(plan))
            
            if plan.warnings:
                for w in plan.warnings:
                    print_warning(w)
    except TerrariumError as e:
        print_error(str(e))
        raise typer.Exit(1)
```

**Backend Calls**:
- `compiler.compile_from_nl(description, reality, behavior, fidelity)` -> `WorldPlan`
- `PlanReviewer().to_yaml(plan)` -> YAML string
- `PlanReviewer().format_plan(plan)` -> formatted string

**Output**: Writes YAML to `output` path. Prints plan summary panel.

**Error Handling**: `CompilerError` or `NLParseError` from the compiler (both subclass `TerrariumError`).

---

#### Command 2: `init` (NEW -- not in current stubs)

**Purpose**: Compile a YAML world definition into a WorldPlan without running.

```
Typer Signature:
@app.command()
def init(
    world: Annotated[str, typer.Argument(help="Path to world definition YAML file")],
    settings: Annotated[Optional[str], typer.Option("--settings", "-s", help="Path to compiler settings YAML")] = None,
    output: Annotated[Optional[Path], typer.Option("--output", "-o", help="Path to write compiled plan")] = None,
) -> None:
    """Compile a YAML world definition into a world plan."""
    asyncio.run(_init_impl(world, settings, output))
```

**Async Implementation `_init_impl`**:

```
async def _init_impl(world, settings, output):
    try:
        async with app_context() as terrarium:
            compiler = terrarium.registry.get("world_compiler")
            
            console.print(f"[bold]Compiling world from {world}...[/bold]")
            plan = await compiler.compile_from_yaml(world, settings)
            
            from terrarium.engines.world_compiler.plan_reviewer import PlanReviewer
            reviewer = PlanReviewer()
            
            # Validate
            errors = reviewer.validate_plan(plan)
            if errors:
                for err in errors:
                    print_warning(err)
            
            # Show plan
            print_plan(reviewer.format_plan(plan))
            
            # Optionally write plan to file
            if output:
                yaml_str = reviewer.to_yaml(plan)
                output.write_text(yaml_str)
                print_success(f"Compiled plan written to {output}")
            else:
                print_success("Compilation complete")
    except TerrariumError as e:
        print_error(str(e))
        raise typer.Exit(1)
```

**Backend Calls**:
- `compiler.compile_from_yaml(world_def_path, settings_path)` -> `WorldPlan`
- `PlanReviewer().format_plan(plan)` -> str
- `PlanReviewer().to_yaml(plan)` -> YAML str

---

#### Command 3: `plan`

**Purpose**: Show or export a plan from a description (NL or YAML path).

```
Typer Signature:
@app.command()
def plan(
    description: Annotated[str, typer.Argument(help="Natural language world description or path to YAML file")],
    output: Annotated[Optional[Path], typer.Option("--output", "-o", help="Path to write the generated world plan")] = None,
    format: Annotated[str, typer.Option("--format", "-f", help="Output format: text, yaml, json")] = "text",
) -> None:
    """Generate and display a world plan without executing it."""
    asyncio.run(_plan_impl(description, output, format))
```

**Async Implementation `_plan_impl`**:

```
async def _plan_impl(description, output, fmt):
    try:
        async with app_context() as terrarium:
            compiler = terrarium.registry.get("world_compiler")
            
            # Detect if description is a file path
            desc_path = Path(description)
            if desc_path.exists() and desc_path.suffix in (".yaml", ".yml"):
                plan = await compiler.compile_from_yaml(str(desc_path))
            else:
                plan = await compiler.compile_from_nl(description)
            
            from terrarium.engines.world_compiler.plan_reviewer import PlanReviewer
            reviewer = PlanReviewer()
            
            if fmt == "json":
                content = json.dumps(plan.model_dump(mode="json"), indent=2, default=str)
            elif fmt == "yaml":
                content = reviewer.to_yaml(plan)
            else:
                content = reviewer.format_plan(plan)
            
            write_output(content, output)
            
            if not output:
                if fmt == "text":
                    print_plan(content)
                else:
                    console.print(content)
    except TerrariumError as e:
        print_error(str(e))
        raise typer.Exit(1)
```

**Backend Calls**:
- `compiler.compile_from_yaml(path)` or `compiler.compile_from_nl(description)`
- `PlanReviewer().format_plan(plan)` / `.to_yaml(plan)` / `plan.model_dump()`

---

#### Command 4: `run`

**Purpose**: Full simulation lifecycle -- compile + generate + configure + run simulation + report.

```
Typer Signature:
@app.command()
def run(
    world: Annotated[str, typer.Argument(help="Path to YAML world definition or NL description")],
    settings: Annotated[Optional[str], typer.Option("--settings", "-s", help="Path to compiler settings YAML")] = None,
    agent: Annotated[Optional[str], typer.Option("--agent", "-a", help="Agent adapter to connect")] = None,
    actor: Annotated[Optional[str], typer.Option("--actor", help="Actor ID to assign the agent to")] = None,
    mode: Annotated[Optional[str], typer.Option("--mode", "-m", help="Override world mode: governed, ungoverned")] = None,
    tag: Annotated[Optional[str], typer.Option("--tag", "-t", help="Tag for this run")] = None,
    behavior: Annotated[str, typer.Option("--behavior", "-b", help="Behavior mode: static, reactive, dynamic")] = "dynamic",
    serve: Annotated[bool, typer.Option("--serve", help="Start MCP/HTTP servers for agent connection")] = False,
) -> None:
    """Run a full simulation on a world definition."""
    asyncio.run(_run_impl(world, settings, agent, actor, mode, tag, behavior, serve))
```

**Async Implementation `_run_impl`**:

```
async def _run_impl(world, settings, agent, actor, mode, tag, behavior, serve):
    try:
        async with app_context() as terrarium:
            compiler = terrarium.registry.get("world_compiler")
            
            # Step 1: Compile
            console.print("[bold]Step 1/4: Compiling world...[/bold]")
            world_path = Path(world)
            if world_path.exists() and world_path.suffix in (".yaml", ".yml"):
                plan = await compiler.compile_from_yaml(str(world_path), settings)
            else:
                plan = await compiler.compile_from_nl(world)
            
            # Override mode if specified
            if mode:
                plan = plan.model_copy(update={"mode": mode})
            if behavior:
                plan = plan.model_copy(update={"behavior": behavior})
            
            # Step 2: Create run and compile world
            console.print("[bold]Step 2/4: Generating world and creating run...[/bold]")
            run_id = await terrarium.create_run(plan, mode=plan.mode, tag=tag)
            console.print(f"  Run ID: [cyan]{run_id}[/cyan]")
            
            # Step 3: Optionally start servers
            if serve:
                console.print("[bold]Step 3/4: Starting protocol servers...[/bold]")
                await terrarium.gateway.start_adapters()
                gateway_config = terrarium._config.gateway
                console.print(f"  HTTP: http://{gateway_config.host}:{gateway_config.port}")
                console.print(f"  MCP:  stdio (connect via mcp client)")
                console.print("[dim]Press Ctrl+C to stop[/dim]")
                
                # Run simulation loop
                from terrarium.simulation.runner import SimulationRunner
                from terrarium.simulation.event_queue import EventQueue
                
                event_queue = EventQueue()
                
                async def pipeline_executor(envelope):
                    result = await terrarium.handle_action(
                        actor_id=str(envelope.actor_id),
                        service_id=str(envelope.service_id),
                        action=envelope.action,
                        input_data=envelope.input_data,
                    )
                    return result if "error" not in result else None
                
                runner = SimulationRunner(
                    event_queue=event_queue,
                    pipeline_executor=pipeline_executor,
                    agency_engine=terrarium.registry.get("agency"),
                    animator=terrarium.registry.get("animator"),
                    config=terrarium._config.simulation_runner,
                    ledger=terrarium.ledger,
                )
                
                if plan.mission:
                    runner.set_mission(plan.mission)
                
                console.print("[bold]Step 4/4: Running simulation...[/bold]")
                stop_reason = await runner.run()
                console.print(f"  Simulation stopped: [yellow]{stop_reason}[/yellow]")
            else:
                console.print("[bold]Step 3/4: Skipping server start (use --serve to enable)[/bold]")
                console.print("[bold]Step 4/4: Simulation ready for programmatic interaction[/bold]")
            
            # Step 5: End run and generate report
            console.print("[bold]Generating report...[/bold]")
            result = await terrarium.end_run(run_id)
            
            report = result.get("report", {})
            scorecard = result.get("scorecard", {})
            
            print_report(report)
            console.print()
            console.print(format_scorecard(scorecard))
            
            print_success(f"Run {run_id} completed")
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
    except TerrariumError as e:
        print_error(str(e))
        raise typer.Exit(1)
```

**Backend Calls**:
- `compiler.compile_from_yaml()` or `compiler.compile_from_nl()`
- `terrarium.create_run(plan, mode, tag)` -> `RunId`
- `terrarium.gateway.start_adapters()`
- `SimulationRunner(...).run()` -> `StopReason`
- `terrarium.end_run(run_id)` -> dict with report + scorecard

---

#### Command 5: `serve` (NEW)

**Purpose**: Start MCP/HTTP servers for an already-compiled world.

```
Typer Signature:
@app.command()
def serve(
    world: Annotated[str, typer.Argument(help="Path to YAML world definition")],
    settings: Annotated[Optional[str], typer.Option("--settings", "-s", help="Path to compiler settings YAML")] = None,
    host: Annotated[str, typer.Option("--host", help="HTTP server bind host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", "-p", help="HTTP server bind port")] = 8080,
) -> None:
    """Compile world and start MCP/HTTP servers for agent connections."""
    asyncio.run(_serve_impl(world, settings, host, port))
```

**Async Implementation `_serve_impl`**:

```
async def _serve_impl(world, settings, host, port):
    try:
        async with app_context() as terrarium:
            compiler = terrarium.registry.get("world_compiler")
            
            console.print(f"[bold]Compiling world from {world}...[/bold]")
            plan = await compiler.compile_from_yaml(world, settings)
            
            console.print("[bold]Generating world...[/bold]")
            await terrarium.compile_and_run(plan)
            
            console.print("[bold]Starting protocol servers...[/bold]")
            await terrarium.gateway.start_adapters()
            
            console.print(f"[green]HTTP server: http://{host}:{port}[/green]")
            console.print("[green]MCP server:  stdio[/green]")
            console.print("[dim]Press Ctrl+C to stop[/dim]")
            
            # List available tools
            tools = await terrarium.gateway.get_tool_manifest()
            if tools:
                console.print(f"\nAvailable tools ({len(tools)}):")
                for tool in tools:
                    name = tool.get("name", "?")
                    desc = tool.get("description", "")[:60]
                    console.print(f"  [cyan]{name}[/cyan] -- {desc}")
            
            # Block until interrupted
            try:
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                pass
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down servers...[/yellow]")
    except TerrariumError as e:
        print_error(str(e))
        raise typer.Exit(1)
```

**Backend Calls**:
- `compiler.compile_from_yaml()`
- `terrarium.compile_and_run(plan)`
- `terrarium.gateway.start_adapters()`
- `terrarium.gateway.get_tool_manifest()` -> list of tool dicts

---

#### Command 6: `report`

```
Typer Signature:
@app.command()
def report(
    run_id: Annotated[str, typer.Argument(help="Run ID or tag (use 'last' for latest)")] = "last",
    format: Annotated[str, typer.Option("--format", "-f", help="Output format: json, markdown")] = "markdown",
    output: Annotated[Optional[Path], typer.Option("--output", "-o", help="Output file path (default: stdout)")] = None,
) -> None:
    """Generate a governance report for a run."""
    asyncio.run(_report_impl(run_id, format, output))
```

**Async Implementation `_report_impl`**:

```
async def _report_impl(run_id_str, fmt, output):
    try:
        async with app_context() as terrarium:
            from terrarium.core.types import RunId
            
            # Try to load from artifact store first
            run = await terrarium.run_manager.get_run(RunId(run_id_str))
            if run is None:
                print_error(f"Run not found: {run_id_str}")
                raise typer.Exit(1)
            
            actual_run_id = RunId(run["run_id"])
            report = await terrarium.artifact_store.load_artifact(actual_run_id, "report")
            scorecard = await terrarium.artifact_store.load_artifact(actual_run_id, "scorecard")
            
            if report is None:
                # No saved report -- generate fresh from current state
                reporter = terrarium.registry.get("reporter")
                report = await reporter.generate_full_report()
                scorecard = await reporter.generate_scorecard()
            
            if fmt == "json":
                content = json.dumps({"report": report, "scorecard": scorecard}, indent=2, default=str)
                write_output(content, output)
            else:
                print_report(report, fmt="markdown")
                if scorecard:
                    console.print(format_scorecard(scorecard))
    except TerrariumError as e:
        print_error(str(e))
        raise typer.Exit(1)
```

**Backend Calls**:
- `terrarium.run_manager.get_run(RunId(run_id))` -> dict | None
- `terrarium.artifact_store.load_artifact(run_id, "report")` -> dict | None
- `terrarium.artifact_store.load_artifact(run_id, "scorecard")` -> dict | None
- Fallback: `reporter.generate_full_report()`, `reporter.generate_scorecard()`

---

#### Command 7: `diff`

```
Typer Signature:
@app.command()
def diff(
    runs: Annotated[list[str], typer.Argument(help="Run tags or IDs to compare (2 or more)")],
    format: Annotated[str, typer.Option("--format", "-f", help="Output format: cli, json, markdown")] = "cli",
    governed_vs_ungoverned: Annotated[bool, typer.Option("--gov-vs-ungov", help="Compare governed vs ungoverned mode")] = False,
) -> None:
    """Show differences between runs."""
    asyncio.run(_diff_impl(runs, format, governed_vs_ungoverned))
```

**Async Implementation `_diff_impl`**:

```
async def _diff_impl(runs, fmt, gov_vs_ungov):
    try:
        if len(runs) < 2:
            print_error("Need at least 2 run IDs to compare")
            raise typer.Exit(1)
        
        async with app_context() as terrarium:
            if gov_vs_ungov and len(runs) == 2:
                result = await terrarium.diff_governed_ungoverned(runs[0], runs[1])
            else:
                result = await terrarium.diff_runs(runs)
            
            if fmt == "json":
                print_json(result)
            else:
                from terrarium.runs.comparison import RunComparator
                comparator = RunComparator(terrarium.artifact_store)
                formatted = comparator.format_comparison(result)
                console.print(formatted)
    except TerrariumError as e:
        print_error(str(e))
        raise typer.Exit(1)
```

**Backend Calls**:
- `terrarium.diff_runs(run_ids)` -> dict
- `terrarium.diff_governed_ungoverned(gov_tag, ungov_tag)` -> dict
- `RunComparator.format_comparison(result)` -> str

---

#### Command 8: `inspect` (NEW)

```
Typer Signature:
@app.command()
def inspect(
    resource: Annotated[str, typer.Argument(help="What to inspect: entities, actors, policies, services, tools")],
    entity_type: Annotated[Optional[str], typer.Option("--type", "-t", help="Entity type filter")] = None,
    actor_id: Annotated[Optional[str], typer.Option("--actor", "-a", help="Actor ID to inspect")] = None,
    format: Annotated[str, typer.Option("--format", "-f", help="Output format: cli, json")] = "cli",
) -> None:
    """Inspect world state: entities, actors, policies, services, or tools."""
    asyncio.run(_inspect_impl(resource, entity_type, actor_id, format))
```

**Async Implementation `_inspect_impl`**:

```
async def _inspect_impl(resource, entity_type, actor_id, fmt):
    try:
        async with app_context() as terrarium:
            if resource == "entities":
                state = terrarium.registry.get("state")
                if entity_type:
                    entities = await state.query_entities(entity_type)
                    if fmt == "json":
                        print_json(entities)
                    else:
                        console.print(format_entity_table(entities, entity_type))
                else:
                    # List entity types by querying all known types
                    console.print("[yellow]Specify --type to query entities[/yellow]")
                    
            elif resource == "actors":
                compiler = terrarium.registry.get("world_compiler")
                actor_registry = compiler._config.get("_actor_registry")
                if actor_registry:
                    if actor_id:
                        from terrarium.core.types import ActorId as AId
                        actor = actor_registry.get(AId(actor_id))
                        data = {"id": str(actor.id), "type": str(actor.type),
                                "role": actor.role, "team": actor.team,
                                "permissions": actor.permissions}
                        if fmt == "json":
                            print_json(data)
                        else:
                            console.print(Panel(json.dumps(data, indent=2, default=str), title=f"Actor: {actor_id}"))
                    else:
                        actors = actor_registry.list_actors()
                        if fmt == "json":
                            print_json([{"id": str(a.id), "type": str(a.type), "role": a.role} for a in actors])
                        else:
                            table = Table(title="Actors")
                            table.add_column("ID")
                            table.add_column("Type")
                            table.add_column("Role")
                            table.add_column("Team")
                            for a in actors:
                                table.add_row(str(a.id), str(a.type), a.role, a.team or "")
                            console.print(table)
                            
            elif resource == "policies":
                policy_engine = terrarium.registry.get("policy")
                policies = getattr(policy_engine, "_policies", [])
                if fmt == "json":
                    print_json(policies)
                else:
                    for i, p in enumerate(policies):
                        console.print(Panel(json.dumps(p, indent=2, default=str), title=f"Policy {i+1}"))
                    if not policies:
                        console.print("[dim]No policies configured[/dim]")
                        
            elif resource == "services" or resource == "tools":
                responder = terrarium.registry.get("responder")
                if hasattr(responder, "_pack_registry"):
                    if resource == "services":
                        packs = responder._pack_registry.list_packs()
                        if fmt == "json":
                            print_json(packs)
                        else:
                            table = Table(title="Services")
                            table.add_column("Pack Name")
                            table.add_column("Tools")
                            for p in packs:
                                table.add_row(p.get("pack_name", "?"), str(p.get("tool_count", 0)))
                            console.print(table)
                    else:  # tools
                        tools = responder._pack_registry.list_tools()
                        if fmt == "json":
                            print_json(tools)
                        else:
                            table = Table(title="Tools")
                            table.add_column("Name")
                            table.add_column("Service")
                            table.add_column("Description")
                            for t in tools:
                                table.add_row(t.get("name", "?"), t.get("pack_name", "?"), t.get("description", "")[:60])
                            console.print(table)
                else:
                    console.print("[dim]No service packs registered[/dim]")
            else:
                print_error(f"Unknown resource: {resource}. Use: entities, actors, policies, services, tools")
                raise typer.Exit(1)
    except TerrariumError as e:
        print_error(str(e))
        raise typer.Exit(1)
```

**Backend Calls**:
- `state.query_entities(entity_type)` -> list[dict]
- `actor_registry.list_actors()` / `actor_registry.get(ActorId(...))`
- `policy_engine._policies` attribute
- `responder._pack_registry.list_packs()` / `.list_tools()`

---

#### Command 9: `list` (NEW)

```
Typer Signature:
@app.command(name="list")
def list_resources(
    resource: Annotated[str, typer.Argument(help="What to list: runs, tools, services, engines, artifacts")],
    run_id: Annotated[Optional[str], typer.Option("--run", "-r", help="Run ID (for artifacts)")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Maximum items to show")] = 20,
    format: Annotated[str, typer.Option("--format", "-f", help="Output format: cli, json")] = "cli",
) -> None:
    """List runs, tools, services, engines, or artifacts."""
    asyncio.run(_list_impl(resource, run_id, limit, format))
```

**Async Implementation `_list_impl`**:

```
async def _list_impl(resource, run_id, limit, fmt):
    try:
        async with app_context() as terrarium:
            if resource == "runs":
                runs = await terrarium.run_manager.list_runs(limit=limit)
                if fmt == "json":
                    print_json(runs)
                else:
                    console.print(format_run_table(runs))
                    
            elif resource == "tools":
                responder = terrarium.registry.get("responder")
                if hasattr(responder, "_pack_registry"):
                    tools = responder._pack_registry.list_tools()
                    if fmt == "json":
                        print_json(tools)
                    else:
                        table = Table(title=f"Tools ({len(tools)})")
                        table.add_column("Name")
                        table.add_column("Service")
                        table.add_column("Description")
                        for t in tools[:limit]:
                            table.add_row(t.get("name", "?"), t.get("pack_name", "?"), t.get("description", "")[:60])
                        console.print(table)
                else:
                    console.print("[dim]No tools registered[/dim]")
                    
            elif resource == "services":
                responder = terrarium.registry.get("responder")
                if hasattr(responder, "_pack_registry"):
                    packs = responder._pack_registry.list_packs()
                    if fmt == "json":
                        print_json(packs)
                    else:
                        table = Table(title=f"Services ({len(packs)})")
                        table.add_column("Name")
                        table.add_column("Tools")
                        table.add_column("Tier")
                        for p in packs[:limit]:
                            table.add_row(p.get("pack_name", "?"), str(p.get("tool_count", 0)), str(p.get("tier", "?")))
                        console.print(table)
                else:
                    console.print("[dim]No services registered[/dim]")
                    
            elif resource == "engines":
                engines = terrarium.registry.list_engines()
                if fmt == "json":
                    print_json([{"name": e} for e in engines])
                else:
                    table = Table(title=f"Engines ({len(engines)})")
                    table.add_column("Name")
                    for e in engines:
                        table.add_row(e)
                    console.print(table)
                    
            elif resource == "artifacts":
                if not run_id:
                    print_error("--run is required for listing artifacts")
                    raise typer.Exit(1)
                from terrarium.core.types import RunId
                artifacts = await terrarium.artifact_store.list_artifacts(RunId(run_id))
                if fmt == "json":
                    print_json(artifacts)
                else:
                    table = Table(title=f"Artifacts for {run_id}")
                    table.add_column("Type")
                    table.add_column("Path")
                    table.add_column("Size (bytes)")
                    for a in artifacts:
                        table.add_row(a.get("type", "?"), a.get("path", "?"), str(a.get("size_bytes", 0)))
                    console.print(table)
            else:
                print_error(f"Unknown resource: {resource}. Use: runs, tools, services, engines, artifacts")
                raise typer.Exit(1)
    except TerrariumError as e:
        print_error(str(e))
        raise typer.Exit(1)
```

---

#### Command 10: `show` (NEW)

```
Typer Signature:
@app.command()
def show(
    resource: Annotated[str, typer.Argument(help="What to show: run, tool, service")],
    name: Annotated[str, typer.Argument(help="Resource name or ID")],
    format: Annotated[str, typer.Option("--format", "-f", help="Output format: cli, json")] = "cli",
) -> None:
    """Show detailed information about a run, tool, or service."""
    asyncio.run(_show_impl(resource, name, format))
```

**Async Implementation `_show_impl`**:

```
async def _show_impl(resource, name, fmt):
    try:
        async with app_context() as terrarium:
            if resource == "run":
                from terrarium.core.types import RunId
                run = await terrarium.run_manager.get_run(RunId(name))
                if run is None:
                    print_error(f"Run not found: {name}")
                    raise typer.Exit(1)
                if fmt == "json":
                    print_json(run)
                else:
                    console.print(Panel(json.dumps(run, indent=2, default=str), title=f"Run: {name}"))
                    
            elif resource == "tool":
                responder = terrarium.registry.get("responder")
                if hasattr(responder, "_pack_registry"):
                    tools = responder._pack_registry.list_tools()
                    tool = next((t for t in tools if t.get("name") == name), None)
                    if tool is None:
                        print_error(f"Tool not found: {name}")
                        raise typer.Exit(1)
                    if fmt == "json":
                        print_json(tool)
                    else:
                        console.print(Panel(json.dumps(tool, indent=2, default=str), title=f"Tool: {name}"))
                else:
                    print_error("No service packs registered")
                    raise typer.Exit(1)
                    
            elif resource == "service":
                responder = terrarium.registry.get("responder")
                if hasattr(responder, "_pack_registry"):
                    try:
                        pack = responder._pack_registry.get_pack(name)
                    except Exception:
                        print_error(f"Service not found: {name}")
                        raise typer.Exit(1)
                    from terrarium.kernel.surface import ServiceSurface
                    surface = ServiceSurface.from_pack(pack)
                    data = surface.model_dump(mode="json")
                    if fmt == "json":
                        print_json(data)
                    else:
                        console.print(Panel(json.dumps(data, indent=2, default=str), title=f"Service: {name}"))
                else:
                    print_error("No service packs registered")
                    raise typer.Exit(1)
            else:
                print_error(f"Unknown resource: {resource}. Use: run, tool, service")
                raise typer.Exit(1)
    except TerrariumError as e:
        print_error(str(e))
        raise typer.Exit(1)
```

---

#### Command 11: `snapshot` (NEW)

```
Typer Signature:
@app.command()
def snapshot(
    label: Annotated[str, typer.Argument(help="Label for the snapshot")] = "manual",
) -> None:
    """Create a point-in-time snapshot of the current world state."""
    asyncio.run(_snapshot_impl(label))
```

**Async Implementation `_snapshot_impl`**:

```
async def _snapshot_impl(label):
    try:
        async with app_context() as terrarium:
            state = terrarium.registry.get("state")
            snapshot_id = await state.snapshot(label)
            print_success(f"Snapshot created: {snapshot_id} (label: {label})")
    except TerrariumError as e:
        print_error(str(e))
        raise typer.Exit(1)
```

**Backend Calls**: `state.snapshot(label)` -> `SnapshotId`

---

#### Command 12: `replay` (NEW)

```
Typer Signature:
@app.command()
def replay(
    run_id: Annotated[str, typer.Argument(help="Run ID or tag to replay from")],
    tag: Annotated[Optional[str], typer.Option("--tag", "-t", help="Tag for the replay run")] = None,
) -> None:
    """Replay a previous run from its saved artifacts."""
    asyncio.run(_replay_impl(run_id, tag))
```

**Async Implementation `_replay_impl`**:

```
async def _replay_impl(run_id_str, tag):
    try:
        async with app_context() as terrarium:
            from terrarium.core.types import RunId
            
            # Load original run's config
            source_run = await terrarium.run_manager.get_run(RunId(run_id_str))
            if source_run is None:
                print_error(f"Run not found: {run_id_str}")
                raise typer.Exit(1)
            
            # Load the original world definition from the config artifact
            config_artifact = await terrarium.artifact_store.load_artifact(RunId(source_run["run_id"]), "config")
            if config_artifact is None:
                print_error(f"No config artifact found for run {run_id_str}")
                raise typer.Exit(1)
            
            console.print(f"[bold]Replaying run {run_id_str}...[/bold]")
            
            # Reconstruct the world from the stored world_def
            world_def = source_run.get("world_def", {})
            if not world_def:
                print_error("Run has no stored world definition -- cannot replay")
                raise typer.Exit(1)
            
            # Use the stored config to re-compile
            compiler = terrarium.registry.get("world_compiler")
            plan_partial, service_specs = await compiler._yaml_parser.parse_from_dicts(
                world_def, source_run.get("config_snapshot", {})
            )
            plan = await compiler._resolve_and_assemble(plan_partial, service_specs)
            
            # Create a new run from the reconstructed plan
            replay_tag = tag or f"replay-{run_id_str}"
            new_run_id = await terrarium.create_run(plan, mode=plan.mode, tag=replay_tag)
            
            # Load and replay event log
            event_log = await terrarium.artifact_store.load_artifact(RunId(source_run["run_id"]), "event_log")
            if event_log and isinstance(event_log, list):
                console.print(f"  Replaying {len(event_log)} events...")
                for event_data in event_log:
                    if isinstance(event_data, dict) and event_data.get("action"):
                        await terrarium.handle_action(
                            actor_id=event_data.get("actor_id", "replay-agent"),
                            service_id=event_data.get("service_id", "unknown"),
                            action=event_data["action"],
                            input_data=event_data.get("input_data", {}),
                        )
            
            result = await terrarium.end_run(new_run_id)
            print_success(f"Replay complete. New run: {new_run_id}")
            
            # Show comparison
            comparison = await terrarium.diff_runs([source_run["run_id"], str(new_run_id)])
            from terrarium.runs.comparison import RunComparator
            comparator = RunComparator(terrarium.artifact_store)
            console.print(comparator.format_comparison(comparison))
    except TerrariumError as e:
        print_error(str(e))
        raise typer.Exit(1)
```

---

#### Command 13: `setup`

```
Typer Signature:
@app.command()
def setup(
    provider: Annotated[Optional[str], typer.Argument(help="Provider to set up: anthropic, openai, google, claude-acp, codex-acp, all")] = "all",
) -> None:
    """Interactive setup wizard -- configure LLM providers and ACP servers."""
    asyncio.run(_setup_impl(provider))
```

**Async Implementation `_setup_impl`**:

```
async def _setup_impl(provider):
    import os
    
    console.print("[bold]Terrarium Setup Wizard[/bold]\n")
    
    providers_to_check = {
        "google": {"env": "GOOGLE_API_KEY", "cli": None, "sdk": "google.genai"},
        "anthropic": {"env": "ANTHROPIC_API_KEY", "cli": "claude", "sdk": "anthropic"},
        "openai": {"env": "OPENAI_API_KEY", "cli": None, "sdk": "openai"},
        "claude-acp": {"env": None, "cli": "claude", "sdk": "acp_sdk"},
        "codex-acp": {"env": None, "cli": "codex", "sdk": "acp_sdk"},
    }
    
    if provider != "all":
        if provider not in providers_to_check:
            print_error(f"Unknown provider: {provider}. Options: {', '.join(providers_to_check.keys())}, all")
            raise typer.Exit(1)
        providers_to_check = {provider: providers_to_check[provider]}
    
    for name, info in providers_to_check.items():
        console.print(f"\n[bold]--- {name.upper()} ---[/bold]")
        
        # Check CLI
        if info["cli"]:
            cli_path = shutil.which(info["cli"])
            if cli_path:
                console.print(f"  CLI [{info['cli']}]: [green]found[/green] at {cli_path}")
            else:
                console.print(f"  CLI [{info['cli']}]: [red]not found[/red]")
        
        # Check env var
        if info["env"]:
            env_val = os.environ.get(info["env"])
            if env_val:
                masked = env_val[:4] + "..." + env_val[-4:] if len(env_val) > 8 else "***"
                console.print(f"  API key [{info['env']}]: [green]set[/green] ({masked})")
            else:
                console.print(f"  API key [{info['env']}]: [red]not set[/red]")
                # Prompt for key
                key = typer.prompt(f"  Enter {info['env']} (or press Enter to skip)", default="", show_default=False)
                if key:
                    console.print(f"  [yellow]Note: Set {info['env']}={key[:4]}... in your shell profile for persistence[/yellow]")
        
        # Check SDK
        if info["sdk"]:
            try:
                __import__(info["sdk"])
                console.print(f"  SDK [{info['sdk']}]: [green]available[/green]")
            except ImportError:
                console.print(f"  SDK [{info['sdk']}]: [red]not installed[/red]")
    
    console.print("\n[bold]Setup complete.[/bold] Run 'terrarium check' to verify connectivity.")
```

---

#### Command 14: `check`

```
Typer Signature:
@app.command()
def check(
    test: Annotated[bool, typer.Option("--test", "-t", help="Run real API tests for configured providers")] = False,
) -> None:
    """Check system requirements and provider connectivity."""
    asyncio.run(_check_impl(test))
```

**Async Implementation `_check_impl`**:

```
async def _check_impl(run_tests):
    import os
    
    console.print("[bold]Terrarium System Check[/bold]\n")
    
    # 1. Check Python version
    import sys
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok = sys.version_info >= (3, 12)
    status = "[green]OK[/green]" if ok else "[red]FAIL[/red]"
    console.print(f"Python: {py_ver} {status}")
    
    # 2. Check required packages
    packages = ["pydantic", "aiosqlite", "typer", "fastapi", "httpx", "mcp", "yaml", "rich"]
    for pkg in packages:
        try:
            __import__(pkg)
            console.print(f"  {pkg}: [green]installed[/green]")
        except ImportError:
            console.print(f"  {pkg}: [red]missing[/red]")
    
    # 3. Check LLM providers
    console.print("\n[bold]LLM Providers:[/bold]")
    provider_checks = [
        ("Google (Gemini)", "GOOGLE_API_KEY", "google.genai", None),
        ("Anthropic", "ANTHROPIC_API_KEY", "anthropic", "claude"),
        ("OpenAI", "OPENAI_API_KEY", "openai", None),
    ]
    for label, env_var, sdk, cli_name in provider_checks:
        has_key = bool(os.environ.get(env_var))
        try:
            __import__(sdk)
            has_sdk = True
        except ImportError:
            has_sdk = False
        has_cli = bool(shutil.which(cli_name)) if cli_name else None
        
        parts = [label + ":"]
        parts.append(f"key={'[green]YES[/green]' if has_key else '[red]NO[/red]'}")
        parts.append(f"sdk={'[green]YES[/green]' if has_sdk else '[red]NO[/red]'}")
        if has_cli is not None:
            parts.append(f"cli={'[green]YES[/green]' if has_cli else '[yellow]NO[/yellow]'}")
        console.print("  " + " ".join(parts))
    
    # 4. Check engine health (requires app start)
    if run_tests:
        console.print("\n[bold]Engine Health (starting app)...[/bold]")
        try:
            async with app_context() as terrarium:
                health = terrarium._health
                results = await health.check_all()
                console.print(format_health_table(results))
                
                if health.is_healthy():
                    print_success("All engines healthy")
                else:
                    print_warning("Some engines unhealthy")
        except Exception as e:
            print_error(f"App startup failed: {e}")
    else:
        console.print("\n[dim]Use --test to start the app and check engine health[/dim]")
    
    # 5. Config check
    console.print("\n[bold]Configuration:[/bold]")
    from pathlib import Path
    config_files = ["terrarium.toml", "terrarium.development.toml", "terrarium.local.toml"]
    for cf in config_files:
        exists = Path(cf).exists()
        status = "[green]found[/green]" if exists else "[dim]not found[/dim]"
        console.print(f"  {cf}: {status}")
```

---

#### Command 15: `ledger`

```
Typer Signature:
@app.command()
def ledger(
    tail: Annotated[int, typer.Option("--tail", "-n", help="Number of recent entries to show")] = 50,
    filter_type: Annotated[Optional[str], typer.Option("--type", help="Filter by entry type (pipeline_step, state_mutation, llm_call, gateway_request, validation, engine_lifecycle, snapshot, actor_activation, action_generation)")] = None,
    actor: Annotated[Optional[str], typer.Option("--actor", "-a", help="Filter by actor ID")] = None,
    engine: Annotated[Optional[str], typer.Option("--engine", "-e", help="Filter by engine name")] = None,
    format: Annotated[str, typer.Option("--format", "-f", help="Output format: cli, json")] = "cli",
) -> None:
    """Query and display audit ledger entries."""
    asyncio.run(_ledger_impl(tail, filter_type, actor, engine, format))
```

**Async Implementation `_ledger_impl`**:

```
async def _ledger_impl(tail, filter_type, actor, engine, fmt):
    try:
        async with app_context() as terrarium:
            from terrarium.ledger.query import LedgerQueryBuilder
            from terrarium.core.types import ActorId
            
            builder = LedgerQueryBuilder().limit(tail)
            if filter_type:
                builder = builder.filter_type(filter_type)
            if actor:
                builder = builder.filter_actor(ActorId(actor))
            if engine:
                builder = builder.filter_engine(engine)
            
            query = builder.build()
            entries = await terrarium.ledger.query(query)
            
            if fmt == "json":
                print_json([e.model_dump(mode="json") for e in entries])
            else:
                console.print(format_ledger_table(entries))
                console.print(f"\n[dim]Showing {len(entries)} entries (limit: {tail})[/dim]")
    except TerrariumError as e:
        print_error(str(e))
        raise typer.Exit(1)
```

**Backend Calls**:
- `LedgerQueryBuilder().limit(tail).filter_type(filter_type).filter_actor(actor).filter_engine(engine).build()` -> `LedgerQuery`
- `terrarium.ledger.query(query)` -> list[LedgerEntry]

---

#### Deferred Commands (5)

These replace the existing stubs for `capture`, `compile_pack`, `verify_pack`, `promote`, `annotate`:

```python
_DEFERRED_MSG = "[yellow]This command is not yet implemented. It will be available in a future release.[/yellow]"

@app.command()
def capture(
    service: Annotated[str, typer.Argument(help="Service name to capture")],
    run: Annotated[str, typer.Option("--run", "-r", help="Run ID to capture from")] = "last",
) -> None:
    """Capture a bootstrapped service surface from a completed run."""
    console.print(_DEFERRED_MSG)
    raise typer.Exit(0)

@app.command()
def compile_pack(
    service: Annotated[str, typer.Argument(help="Service name to compile a pack for")],
    from_source: Annotated[str, typer.Argument(help="Source profile to compile from")],
) -> None:
    """Generate a Tier 1 verified pack from a profile or captured service."""
    console.print(_DEFERRED_MSG)
    raise typer.Exit(0)

@app.command()
def verify_pack(
    service: Annotated[str, typer.Argument(help="Service name whose pack to validate")],
) -> None:
    """Validate a Tier 1 pack for correctness and completeness."""
    console.print(_DEFERRED_MSG)
    raise typer.Exit(0)

@app.command()
def promote(
    service: Annotated[str, typer.Argument(help="Service name to promote")],
    submit_pr: Annotated[bool, typer.Option("--submit-pr", help="Submit a PR to the community profiles repo")] = False,
) -> None:
    """Promote a captured service to Tier 2 community profile."""
    console.print(_DEFERRED_MSG)
    raise typer.Exit(0)

@app.command()
def annotate(
    world: Annotated[str, typer.Argument(help="Name or ID of the world")],
    run_id: Annotated[Optional[str], typer.Option("--run", "-r", help="Specific run ID")] = None,
    message: Annotated[Optional[str], typer.Option("--message", "-m", help="Annotation text")] = None,
    tag: Annotated[Optional[str], typer.Option("--tag", "-t", help="Annotation tag")] = None,
) -> None:
    """Add a human annotation to a world run for feedback and evaluation."""
    console.print(_DEFERRED_MSG)
    raise typer.Exit(0)
```

**Remove**: The old `dashboard` command stub (replaced by nothing -- it was in the old stubs but not in the 15-command spec).

---

### File 3: `tests/cli/test_cli.py`

**Directory**: Create `tests/cli/__init__.py` (empty) and `tests/cli/test_cli.py`.

**Strategy**: Use `typer.testing.CliRunner` to invoke commands. Mock `TerrariumApp` to avoid real database/LLM usage. Some tests use the `app_context` context manager -- we mock that too.

**Test Structure**:

```
tests/cli/__init__.py  (empty)
tests/cli/test_cli.py

Imports:
  - json
  - from unittest.mock import AsyncMock, MagicMock, patch
  - import pytest
  - from typer.testing import CliRunner
  - from terrarium.cli import app

runner = CliRunner()
```

**Test Categories**:

1. **Deferred commands exit cleanly (5 tests)**:
```
def test_capture_not_implemented():
    result = runner.invoke(app, ["capture", "email"])
    assert result.exit_code == 0
    assert "not yet implemented" in result.output

def test_compile_pack_not_implemented():
    result = runner.invoke(app, ["compile-pack", "email", "source"])
    assert result.exit_code == 0

def test_verify_pack_not_implemented():
    result = runner.invoke(app, ["verify-pack", "email"])
    assert result.exit_code == 0

def test_promote_not_implemented():
    result = runner.invoke(app, ["promote", "email"])
    assert result.exit_code == 0

def test_annotate_not_implemented():
    result = runner.invoke(app, ["annotate", "world-1"])
    assert result.exit_code == 0
```

2. **Help text tests (15 tests)**:
```
@pytest.mark.parametrize("cmd", [
    "create", "init", "plan", "run", "serve", "report", "diff",
    "inspect", "list", "show", "snapshot", "replay", "setup", "check", "ledger",
])
def test_command_help(cmd):
    result = runner.invoke(app, [cmd, "--help"])
    assert result.exit_code == 0
    assert cmd in result.output.lower() or "--help" in result.output
```

3. **No-args-is-help test**:
```
def test_no_args_shows_help():
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Programmable worlds" in result.output
```

4. **Mock-based command tests** (mock `app_context`):

For each command, create a fixture that patches `terrarium.cli_helpers.app_context` to yield a mock `TerrariumApp`:

```python
@pytest.fixture
def mock_app():
    """Create a mock TerrariumApp for CLI testing."""
    mock = AsyncMock()
    
    # Registry with mock engines
    mock.registry = MagicMock()
    mock_compiler = AsyncMock()
    mock_compiler.compile_from_yaml = AsyncMock(return_value=MagicMock(
        name="test-world",
        description="Test",
        source="yaml",
        services={},
        warnings=[],
        behavior="dynamic",
        mode="governed",
        model_dump=MagicMock(return_value={"name": "test-world"}),
        model_copy=MagicMock(return_value=MagicMock()),
    ))
    mock_compiler.compile_from_nl = AsyncMock(return_value=mock_compiler.compile_from_yaml.return_value)
    mock.registry.get = MagicMock(return_value=mock_compiler)
    
    # Run manager
    mock.run_manager = AsyncMock()
    mock.run_manager.list_runs = AsyncMock(return_value=[
        {"run_id": "run_abc123", "tag": "test", "mode": "governed", "status": "completed", "created_at": "2026-01-01T00:00:00Z"},
    ])
    mock.run_manager.get_run = AsyncMock(return_value={
        "run_id": "run_abc123", "status": "completed", "tag": "test",
        "world_def": {}, "config_snapshot": {},
    })
    
    # Artifact store
    mock.artifact_store = AsyncMock()
    mock.artifact_store.list_artifacts = AsyncMock(return_value=[])
    mock.artifact_store.load_artifact = AsyncMock(return_value=None)
    
    # Ledger
    mock.ledger = AsyncMock()
    mock.ledger.query = AsyncMock(return_value=[])
    
    # Gateway
    mock.gateway = AsyncMock()
    mock.gateway.get_tool_manifest = AsyncMock(return_value=[])
    
    # Health
    mock._health = AsyncMock()
    mock._health.check_all = AsyncMock(return_value={})
    mock._health.is_healthy = MagicMock(return_value=True)
    
    # Config
    from terrarium.config.schema import TerrariumConfig
    mock._config = TerrariumConfig()
    
    return mock


@pytest.fixture
def patched_app_context(mock_app):
    """Patch app_context to yield mock_app."""
    from contextlib import asynccontextmanager
    
    @asynccontextmanager
    async def _mock_ctx():
        yield mock_app
    
    with patch("terrarium.cli.app_context", _mock_ctx):
        yield mock_app
```

5. **Individual command tests using patched_app_context**:

```python
def test_list_runs(patched_app_context):
    result = runner.invoke(app, ["list", "runs"])
    assert result.exit_code == 0

def test_list_runs_json(patched_app_context):
    result = runner.invoke(app, ["list", "runs", "--format", "json"])
    assert result.exit_code == 0
    # Should contain valid JSON
    assert "run_abc123" in result.output

def test_list_unknown_resource(patched_app_context):
    result = runner.invoke(app, ["list", "unknown"])
    assert result.exit_code == 1

def test_show_run(patched_app_context):
    result = runner.invoke(app, ["show", "run", "run_abc123"])
    assert result.exit_code == 0

def test_show_run_not_found(patched_app_context, mock_app):
    mock_app.run_manager.get_run = AsyncMock(return_value=None)
    result = runner.invoke(app, ["show", "run", "nonexistent"])
    assert result.exit_code == 1

def test_report_json(patched_app_context, mock_app):
    mock_app.artifact_store.load_artifact = AsyncMock(return_value={"scorecard": {}})
    result = runner.invoke(app, ["report", "run_abc123", "--format", "json"])
    assert result.exit_code == 0

def test_diff_requires_two_runs(patched_app_context):
    result = runner.invoke(app, ["diff", "run1"])
    assert result.exit_code == 1

def test_diff_two_runs(patched_app_context, mock_app):
    mock_app.diff_runs = AsyncMock(return_value={
        "run_ids": ["run1", "run2"], "labels": {}, "scores": {}, "events": {}, "entity_states": {},
    })
    result = runner.invoke(app, ["diff", "run1", "run2"])
    assert result.exit_code == 0

def test_ledger_empty(patched_app_context):
    result = runner.invoke(app, ["ledger"])
    assert result.exit_code == 0

def test_ledger_with_type_filter(patched_app_context):
    result = runner.invoke(app, ["ledger", "--type", "pipeline_step"])
    assert result.exit_code == 0

def test_snapshot(patched_app_context, mock_app):
    mock_state = AsyncMock()
    mock_state.snapshot = AsyncMock(return_value="snap_123")
    mock_app.registry.get = MagicMock(return_value=mock_state)
    result = runner.invoke(app, ["snapshot", "my-snapshot"])
    assert result.exit_code == 0
    assert "snap_123" in result.output

def test_inspect_unknown_resource(patched_app_context):
    result = runner.invoke(app, ["inspect", "unknown"])
    assert result.exit_code == 1

def test_check_basic():
    """Check without --test doesn't need app_context."""
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 0
    assert "Python" in result.output

def test_setup_unknown_provider():
    result = runner.invoke(app, ["setup", "nonexistent"], input="\n")
    assert result.exit_code == 1

def test_init_file_not_found(patched_app_context, mock_app):
    from terrarium.core.errors import YAMLParseError
    mock_compiler = AsyncMock()
    mock_compiler.compile_from_yaml = AsyncMock(side_effect=YAMLParseError("File not found"))
    mock_app.registry.get = MagicMock(return_value=mock_compiler)
    result = runner.invoke(app, ["init", "nonexistent.yaml"])
    assert result.exit_code == 1
    assert "Error" in result.output

def test_create_prints_yaml(patched_app_context, mock_app, tmp_path):
    mock_plan = MagicMock()
    mock_plan.warnings = []
    mock_compiler = AsyncMock()
    mock_compiler.compile_from_nl = AsyncMock(return_value=mock_plan)
    mock_app.registry.get = MagicMock(return_value=mock_compiler)
    
    output_file = tmp_path / "world.yaml"
    result = runner.invoke(app, ["create", "A support desk world", "-o", str(output_file)])
    assert result.exit_code == 0
```

**Total test count**: approximately 30 tests covering:
- 5 deferred command tests
- 1 parametrized help test (15 sub-tests)
- 1 no-args test
- ~20 functional command tests with mocked backend

---

### Implementation Sequencing

1. **Phase 1**: Create `terrarium/cli_helpers.py` with all shared utilities and the `app_context` context manager.

2. **Phase 2**: Rewrite `terrarium/cli.py`:
   - Module-level imports and Typer app definition
   - 5 deferred commands first (simplest, validates Typer wiring)
   - `check` and `setup` (no app_context dependency for basic mode)
   - `list`, `show`, `inspect` (read-only commands)
   - `ledger`, `snapshot` (read-only + one write op)
   - `init`, `plan`, `create` (compilation commands)
   - `report`, `diff` (run analysis commands)
   - `run`, `serve`, `replay` (full lifecycle commands)

3. **Phase 3**: Create `tests/cli/__init__.py` and `tests/cli/test_cli.py`.

4. **Phase 4**: Run `uv run pytest tests/cli/ -v` and `uv run ruff check terrarium/cli.py terrarium/cli_helpers.py`.

---

### Key Warnings for Implementer

1. **Typer command names with underscores**: Typer auto-converts underscores to hyphens. The command `compile_pack` becomes `compile-pack` on the CLI. The `name="list"` override is needed because `list` is a Python builtin.

2. **`--format` option**: `format` is a Python builtin too, but it works fine as a Typer option name. The variable inside the function should be renamed to `fmt` to avoid shadowing.

3. **Frozen Pydantic models**: `WorldPlan` is frozen. Use `plan.model_copy(update={...})` to modify fields.

4. **Pack Registry access**: The pack registry is on `responder._pack_registry` (underscore-prefixed private attribute). This is the established pattern used by the gateway and other components. Methods: `.list_packs()` -> list[dict], `.list_tools()` -> list[dict], `.get_pack(name)` -> BasePack.

5. **`asyncio.run()` in Typer**: Each command calls `asyncio.run(_impl(...))`. This creates a fresh event loop per command, which is correct for CLI usage.

6. **Config is frozen**: `TerrariumConfig` is a frozen Pydantic model. The `ConfigLoader().load()` call returns one. Never try to mutate it.

7. **`setup` and `check` without app start**: The basic modes of these commands do NOT need `app_context()`. Only `check --test` needs it. Do not wrap the entire function in `app_context`.

8. **Remove `dashboard` command**: The old stub for `dashboard` is not in the 15-command spec. Remove it.

9. **Rich import**: `rich` is not in `pyproject.toml` dependencies. It comes transitively through `typer[all]` but should be added explicitly: `"rich>=13.0"`.

### Critical Files for Implementation

- `/Users/jana/workspace/terrarium/terrarium/cli.py` - The main file to rewrite with all 15 commands + 5 deferred stubs
- `/Users/jana/workspace/terrarium/terrarium/app.py` - Core backend: TerrariumApp with all methods the CLI calls (start, stop, create_run, end_run, compile_and_run, diff_runs, handle_action)
- `/Users/jana/workspace/terrarium/terrarium/engines/world_compiler/engine.py` - World compiler engine with compile_from_yaml, compile_from_nl, generate_world methods
- `/Users/jana/workspace/terrarium/terrarium/runs/comparison.py` - RunComparator.compare() and format_comparison() for the diff command
- `/Users/jana/workspace/terrarium/tests/integration/conftest.py` - Pattern to follow for mocking TerrariumApp in tests (inject_mock_llm, app fixture with tmp_path)