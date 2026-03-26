"""Terrarium CLI -- command interface for managing programmable worlds."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

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

# ---------------------------------------------------------------------------
# Deferred-command sentinel
# ---------------------------------------------------------------------------

_DEFERRED_MSG = (
    "[yellow]This command is not yet implemented. "
    "It will be available in a future release.[/yellow]"
)

# ===================================================================
# Command 1: create
# ===================================================================


@app.command()
def create(
    description: Annotated[str, typer.Argument(help="Natural language description of the world")],
    reality: Annotated[
        str,
        typer.Option("--reality", "-r", help="Reality preset: ideal, messy, hostile"),
    ] = "messy",
    fidelity: Annotated[
        str,
        typer.Option("--fidelity", help="Fidelity mode: auto, strict, exploratory"),
    ] = "auto",
    mode: Annotated[
        str,
        typer.Option("--mode", "-m", help="World mode: governed, ungoverned"),
    ] = "governed",
    seed: Annotated[
        list[str] | None,
        typer.Option("--seed", help="Seed data files (repeatable)"),
    ] = None,
    override: Annotated[
        list[str] | None,
        typer.Option("--override", help="Reality condition overrides (repeatable, key=value)"),
    ] = None,
    overlay: Annotated[
        list[str] | None,
        typer.Option("--overlay", help="Additional overlay files (repeatable)"),
    ] = None,
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output path for the YAML world definition"),
    ] = Path("./world.yaml"),
) -> None:
    """Create a new world from a natural language description."""
    asyncio.run(_create_impl(description, reality, fidelity, mode, seed, override, overlay, output))


async def _create_impl(
    description: str,
    reality: str,
    fidelity: str,
    mode: str,
    seed: list[str] | None,
    override: list[str] | None,
    overlay: list[str] | None,
    output: Path,
) -> None:
    try:
        async with app_context() as terrarium:
            compiler = terrarium.registry.get("world_compiler")

            console.print("[bold]Creating world from description...[/bold]")
            plan = await compiler.compile_from_nl(
                description=description,
                reality=reality,
                behavior="dynamic",
                fidelity=fidelity,
            )

            from terrarium.engines.world_compiler.plan_reviewer import PlanReviewer

            reviewer = PlanReviewer()
            yaml_str = reviewer.to_yaml(plan)

            # Wire seed, override, overlay into the generated YAML
            import yaml as _yaml

            yaml_data = _yaml.safe_load(yaml_str) or {}
            world_section = yaml_data.setdefault("world", {})
            compiler_section = yaml_data.setdefault("compiler", {})

            if seed:
                world_section["seeds"] = seed
            if override:
                for ov in override:
                    key, _, val = ov.partition("=")
                    compiler_section.setdefault("reality", {})[key.strip()] = val.strip()
            if overlay:
                world_section["overlays"] = overlay

            yaml_str = _yaml.dump(yaml_data, default_flow_style=False, sort_keys=False)

            output.write_text(yaml_str)
            print_success(f"World definition written to {output}")

            print_plan(reviewer.format_plan(plan))

            warnings = getattr(plan, "warnings", None)
            if warnings:
                for w in warnings:
                    print_warning(str(w))
    except TerrariumError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from None


# ===================================================================
# Command 2: init (NEW)
# ===================================================================


@app.command()
def init(
    world: Annotated[str, typer.Argument(help="Path to world definition YAML file")],
    settings: Annotated[
        str | None,
        typer.Option("--settings", "-s", help="Path to compiler settings YAML"),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Path to write compiled plan"),
    ] = None,
) -> None:
    """Compile a YAML world definition into a world plan."""
    asyncio.run(_init_impl(world, settings, output))


async def _init_impl(world: str, settings: str | None, output: Path | None) -> None:
    try:
        async with app_context() as terrarium:
            compiler = terrarium.registry.get("world_compiler")

            console.print(f"[bold]Compiling world from {world}...[/bold]")
            plan = await compiler.compile_from_yaml(world, settings)

            from terrarium.engines.world_compiler.plan_reviewer import PlanReviewer

            reviewer = PlanReviewer()

            errors = reviewer.validate_plan(plan)
            if errors:
                for err in errors:
                    print_warning(str(err))

            print_plan(reviewer.format_plan(plan))

            if output:
                yaml_str = reviewer.to_yaml(plan)
                output.write_text(yaml_str)
                print_success(f"Compiled plan written to {output}")
            else:
                print_success("Compilation complete")
    except TerrariumError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from None


# ===================================================================
# Command 3: plan
# ===================================================================


@app.command()
def plan(
    description: Annotated[
        str,
        typer.Argument(help="Natural language world description or path to YAML file"),
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Path to write the generated world plan"),
    ] = None,
    fmt: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: text, yaml, json"),
    ] = "text",
) -> None:
    """Generate and display a world plan without executing it."""
    asyncio.run(_plan_impl(description, output, fmt))


async def _plan_impl(description: str, output: Path | None, fmt: str) -> None:
    try:
        async with app_context() as terrarium:
            compiler = terrarium.registry.get("world_compiler")

            from terrarium.paths import resolve_blueprint

            resolved = resolve_blueprint(description)
            if resolved:
                compiled = await compiler.compile_from_yaml(str(resolved))
            else:
                compiled = await compiler.compile_from_nl(description)

            from terrarium.engines.world_compiler.plan_reviewer import PlanReviewer

            reviewer = PlanReviewer()

            if fmt == "json":
                content = json.dumps(compiled.model_dump(mode="json"), indent=2, default=str)
            elif fmt == "yaml":
                content = reviewer.to_yaml(compiled)
            else:
                content = reviewer.format_plan(compiled)

            if output:
                write_output(content, output)
            else:
                if fmt == "text":
                    print_plan(content)
                else:
                    console.print(content)
    except TerrariumError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from None


# ===================================================================
# Command 4: run
# ===================================================================


@app.command()
def run(
    world: Annotated[str, typer.Argument(help="Path to YAML world definition or NL description")],
    settings: Annotated[
        str | None,
        typer.Option("--settings", "-s", help="Path to compiler settings YAML"),
    ] = None,
    agent: Annotated[
        str | None,
        typer.Option("--agent", "-a", help="Agent adapter to connect"),
    ] = None,
    actor: Annotated[
        str | None,
        typer.Option("--actor", help="Actor ID to assign the agent to"),
    ] = None,
    mode: Annotated[
        str | None,
        typer.Option("--mode", "-m", help="Override world mode: governed, ungoverned"),
    ] = None,
    tag: Annotated[
        str | None,
        typer.Option("--tag", "-t", help="Tag for this run"),
    ] = None,
    behavior: Annotated[
        str,
        typer.Option("--behavior", "-b", help="Behavior mode: static, reactive, dynamic"),
    ] = "dynamic",
    serve: Annotated[
        bool,
        typer.Option("--serve", help="Start MCP/HTTP servers for agent connection"),
    ] = False,
) -> None:
    """Run a full simulation on a world definition."""
    asyncio.run(_run_impl(world, settings, agent, actor, mode, tag, behavior, serve))


async def _run_impl(
    world: str,
    settings: str | None,
    agent: str | None,
    actor: str | None,
    mode: str | None,
    tag: str | None,
    behavior: str,
    serve: bool,
) -> None:
    try:
        async with app_context() as terrarium:
            compiler = terrarium.registry.get("world_compiler")

            # Step 1: Compile
            console.print("[bold]Step 1/4: Compiling world...[/bold]")
            from terrarium.paths import resolve_blueprint, sanitize_filename, user_blueprints_dir

            resolved = resolve_blueprint(world)
            if resolved:
                console.print(f"  Using: [cyan]{resolved}[/cyan]")
                compiled_plan = await compiler.compile_from_yaml(str(resolved), settings)
            else:
                compiled_plan = await compiler.compile_from_nl(world)
                # Auto-save to ~/.terrarium/blueprints/
                from terrarium.engines.world_compiler.plan_reviewer import PlanReviewer

                reviewer = PlanReviewer()
                name = sanitize_filename(compiled_plan.name)
                saved = user_blueprints_dir() / f"{name}_{compiled_plan.seed}.yaml"
                saved.write_text(reviewer.to_yaml(compiled_plan))
                console.print(f"  Saved: [cyan]{saved}[/cyan]")

            if mode:
                compiled_plan = compiled_plan.model_copy(update={"mode": mode})
            if behavior:
                compiled_plan = compiled_plan.model_copy(update={"behavior": behavior})

            # Step 2: Create run + generate world
            console.print("[bold]Step 2/4: Generating world and creating run...[/bold]")
            run_id = await terrarium.create_run(compiled_plan, mode=compiled_plan.mode, tag=tag)
            console.print(f"  Run ID: [cyan]{run_id}[/cyan]")

            # Step 3: Optionally start servers
            if serve:
                console.print("[bold]Step 3/4: Starting protocol servers...[/bold]")
                await terrarium.gateway.start_adapters()
                gw_cfg = terrarium.config.gateway
                console.print(f"  HTTP: http://{gw_cfg.host}:{gw_cfg.port}")
                console.print("  MCP:  stdio (connect via mcp client)")
                console.print("[dim]Press Ctrl+C to stop[/dim]")

                from terrarium.simulation.event_queue import EventQueue
                from terrarium.simulation.runner import SimulationRunner

                event_queue = EventQueue()

                async def pipeline_executor(envelope: object) -> dict | None:
                    result = await terrarium.handle_action(
                        actor_id=str(envelope.actor_id),  # type: ignore[attr-defined]
                        service_id=str(envelope.service_id),  # type: ignore[attr-defined]
                        action=envelope.action,  # type: ignore[attr-defined]
                        input_data=envelope.input_data,  # type: ignore[attr-defined]
                    )
                    return result if "error" not in result else None

                runner = SimulationRunner(
                    event_queue=event_queue,
                    pipeline_executor=pipeline_executor,
                    agency_engine=terrarium.registry.get("agency"),
                    animator=terrarium.registry.get("animator"),
                    config=terrarium.config.simulation_runner,
                    ledger=terrarium.ledger,
                )

                mission = getattr(compiled_plan, "mission", None)
                if mission:
                    runner.set_mission(mission)

                console.print("[bold]Step 4/4: Running simulation...[/bold]")
                stop_reason = await runner.run()
                console.print(f"  Simulation stopped: [yellow]{stop_reason}[/yellow]")
            else:
                console.print(
                    "[bold]Step 3/4: Skipping server start (use --serve to enable)[/bold]"
                )
                console.print(
                    "[bold]Step 4/4: Simulation ready for programmatic interaction[/bold]"
                )

            # End run + report
            console.print("[bold]Generating report...[/bold]")
            result = await terrarium.end_run(run_id)

            report_data = result.get("report", {})
            scorecard_data = result.get("scorecard", {})

            print_report(report_data)
            console.print()
            console.print(format_scorecard(scorecard_data))
            print_success(f"Run {run_id} completed")
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
    except TerrariumError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from None


# ===================================================================
# Command 5: serve (NEW)
# ===================================================================


@app.command()
def serve(
    world: Annotated[str, typer.Argument(help="Path to YAML world definition")],
    settings: Annotated[
        str | None,
        typer.Option("--settings", "-s", help="Path to compiler settings YAML"),
    ] = None,
    host: Annotated[str, typer.Option("--host", help="HTTP server bind host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", "-p", help="HTTP server bind port")] = 8080,
) -> None:
    """Compile world and start MCP/HTTP servers for agent connections."""
    asyncio.run(_serve_impl(world, settings, host, port))


async def _serve_impl(world: str, settings: str | None, host: str, port: int) -> None:
    try:
        async with app_context() as terrarium:
            compiler = terrarium.registry.get("world_compiler")

            from terrarium.paths import resolve_blueprint, sanitize_filename, user_blueprints_dir

            console.print(f"[bold]Compiling world from {world}...[/bold]")
            resolved = resolve_blueprint(world)
            if resolved:
                console.print(f"  Using: [cyan]{resolved}[/cyan]")
                compiled_plan = await compiler.compile_from_yaml(str(resolved), settings)
            else:
                compiled_plan = await compiler.compile_from_nl(world)
                from terrarium.engines.world_compiler.plan_reviewer import PlanReviewer

                reviewer = PlanReviewer()
                name = sanitize_filename(compiled_plan.name)
                saved = user_blueprints_dir() / f"{name}_{compiled_plan.seed}.yaml"
                saved.write_text(reviewer.to_yaml(compiled_plan))
                console.print(f"  Saved: [cyan]{saved}[/cyan]")

            console.print("[bold]Generating world and creating run...[/bold]")
            run_id = await terrarium.create_run(compiled_plan, mode=compiled_plan.mode)
            console.print(f"  Run ID: [cyan]{run_id}[/cyan]")

            # Wire user-specified host/port into gateway config
            gw_config = terrarium.gateway.config
            gw_config.host = host
            gw_config.port = port

            console.print("[bold]Starting protocol servers...[/bold]")
            await terrarium.gateway.start_adapters()

            console.print(f"[green]HTTP server: http://{host}:{port}[/green]")
            console.print("[green]MCP server:  stdio[/green]")
            console.print("[dim]Press Ctrl+C to stop[/dim]")

            tools = await terrarium.gateway.get_tool_manifest()
            if tools:
                console.print(f"\nAvailable tools ({len(tools)}):")
                for tool in tools:
                    tname = tool.get("name", "?")
                    desc = str(tool.get("description", ""))[:60]
                    console.print(f"  [cyan]{tname}[/cyan] -- {desc}")

            # Start HTTP server (uvicorn) — blocks until Ctrl+C
            http_adapter = terrarium.gateway._adapters.get("http")
            if http_adapter:
                await http_adapter.run_server(host=host, port=port)
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down servers...[/yellow]")
    except TerrariumError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from None


# ===================================================================
# Command 6: mcp (NEW — stdio MCP server for agent subprocess connections)
# ===================================================================


@app.command()
def mcp(
    world: Annotated[str, typer.Argument(help="Path to YAML world definition or NL description")],
    settings: Annotated[
        str | None,
        typer.Option("--settings", "-s", help="Path to compiler settings YAML"),
    ] = None,
) -> None:
    """Run Terrarium as MCP stdio server for agent subprocess connections.

    Agents spawn this command as a subprocess and communicate via MCP protocol
    over stdin/stdout. Accepts a YAML world file or a natural language description.

    Examples:
      terrarium mcp world.yaml
      terrarium mcp "Support team with email and tickets"
    """
    asyncio.run(_mcp_impl(world, settings))


async def _mcp_impl(world: str, settings: str | None) -> None:
    try:
        async with app_context() as terrarium:
            compiler = terrarium.registry.get("world_compiler")

            import sys as _sys

            from terrarium.paths import resolve_blueprint, sanitize_filename, user_blueprints_dir

            resolved = resolve_blueprint(world)
            if resolved:
                print(f"Using: {resolved}", file=_sys.stderr)
                plan = await compiler.compile_from_yaml(str(resolved), settings)
            else:
                plan = await compiler.compile_from_nl(world)
                # Auto-save — stderr so MCP stdio protocol isn't corrupted
                from terrarium.engines.world_compiler.plan_reviewer import PlanReviewer

                reviewer = PlanReviewer()
                name = sanitize_filename(plan.name)
                saved = user_blueprints_dir() / f"{name}_{plan.seed}.yaml"
                saved.write_text(reviewer.to_yaml(plan))
                print(f"Saved: {saved}", file=_sys.stderr)

            await terrarium.compile_and_run(plan)

            mcp_adapter = terrarium.gateway._adapters.get("mcp")
            if mcp_adapter is None:
                print_error("MCP adapter not available")
                raise typer.Exit(1)

            await mcp_adapter.start_server()
            await mcp_adapter.run_stdio()
    except TerrariumError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from None


# ===================================================================
# Command 7: blueprints (list available world blueprints + presets)
# ===================================================================


@app.command()
def blueprints(
    tier: Annotated[
        str | None,
        typer.Option("--tier", "-t", help="Filter by tier: official, community, user"),
    ] = None,
    presets: Annotated[
        bool,
        typer.Option("--presets", help="List reality presets instead of blueprints"),
    ] = False,
) -> None:
    """List available world blueprints and reality presets."""
    from terrarium.paths import list_blueprints, list_presets

    if presets:
        items = list_presets()
        if not items:
            console.print("[dim]No presets found.[/dim]")
            return
        console.print("[bold]Reality Presets:[/bold]")
        for item in items:
            tier_label = item["tier"].upper()
            console.print(f"  [cyan]{tier_label:10s}[/cyan] {item['name']}")
        return

    items = list_blueprints()
    if tier:
        items = [i for i in items if i["tier"] == tier]

    if not items:
        console.print("[dim]No blueprints found.[/dim]")
        return

    console.print("[bold]World Blueprints:[/bold]")
    for item in items:
        tier_label = item["tier"].upper()
        desc = item["description"][:60] if item["description"] else ""
        console.print(f"  [cyan]{tier_label:10s}[/cyan] {item['name']:30s} {desc}")


# ===================================================================
# Command 8: report
# ===================================================================


@app.command()
def report(
    run_id: Annotated[str, typer.Argument(help="Run ID or tag (use 'last' for latest)")] = "last",
    fmt: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: json, markdown"),
    ] = "markdown",
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output file path (default: stdout)"),
    ] = None,
) -> None:
    """Generate a governance report for a run."""
    asyncio.run(_report_impl(run_id, fmt, output))


async def _report_impl(run_id_str: str, fmt: str, output: Path | None) -> None:
    try:
        async with app_context() as terrarium:
            from terrarium.core.types import RunId

            run_record = await terrarium.run_manager.get_run(RunId(run_id_str))
            if run_record is None:
                print_error(f"Run not found: {run_id_str}")
                raise typer.Exit(1)

            actual_run_id = RunId(run_record["run_id"])
            report_data = await terrarium.artifact_store.load_artifact(actual_run_id, "report")
            scorecard_data = await terrarium.artifact_store.load_artifact(
                actual_run_id, "scorecard"
            )

            if report_data is None:
                reporter = terrarium.registry.get("reporter")
                report_data = await reporter.generate_full_report()
                scorecard_data = await reporter.generate_scorecard()

            if fmt == "json":
                content = json.dumps(
                    {"report": report_data, "scorecard": scorecard_data},
                    indent=2,
                    default=str,
                )
                write_output(content, output)
            else:
                print_report(report_data or {}, fmt="markdown")
                if scorecard_data:
                    console.print(format_scorecard(scorecard_data))
    except TerrariumError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from None


# ===================================================================
# Command 7: diff
# ===================================================================


@app.command()
def diff(
    runs: Annotated[list[str], typer.Argument(help="Run tags or IDs to compare (2 or more)")],
    fmt: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: cli, json, markdown"),
    ] = "cli",
    governed_vs_ungoverned: Annotated[
        bool,
        typer.Option("--gov-vs-ungov", help="Compare governed vs ungoverned mode"),
    ] = False,
) -> None:
    """Show differences between runs."""
    asyncio.run(_diff_impl(runs, fmt, governed_vs_ungoverned))


async def _diff_impl(runs: list[str], fmt: str, gov_vs_ungov: bool) -> None:
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
                console.print(format_diff(result))
    except TerrariumError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from None


# ===================================================================
# Command 8: inspect (NEW)
# ===================================================================


@app.command()
def inspect(
    resource: Annotated[
        str,
        typer.Argument(help="What to inspect: entities, actors, policies, services, tools"),
    ],
    entity_type: Annotated[
        str | None,
        typer.Option("--type", "-t", help="Entity type filter"),
    ] = None,
    actor_id: Annotated[
        str | None,
        typer.Option("--actor", "-a", help="Actor ID to inspect"),
    ] = None,
    fmt: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: cli, json"),
    ] = "cli",
) -> None:
    """Inspect world state: entities, actors, policies, services, or tools."""
    asyncio.run(_inspect_impl(resource, entity_type, actor_id, fmt))


async def _inspect_impl(
    resource: str,
    entity_type: str | None,
    actor_id: str | None,
    fmt: str,
) -> None:
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
                    console.print("[yellow]Specify --type to query entities[/yellow]")

            elif resource == "actors":
                actor_registry = terrarium.actor_registry
                if actor_registry:
                    if actor_id:
                        from terrarium.core.types import ActorId as AId

                        actor_def = actor_registry.get(AId(actor_id))
                        if actor_def is None:
                            print_error(f"Actor not found: {actor_id}")
                            raise typer.Exit(1)
                        data = {
                            "id": str(actor_def.id),
                            "type": str(actor_def.type),
                            "role": actor_def.role,
                            "team": getattr(actor_def, "team", None),
                            "permissions": actor_def.permissions,
                        }
                        if fmt == "json":
                            print_json(data)
                        else:
                            console.print(
                                Panel(
                                    json.dumps(data, indent=2, default=str),
                                    title=f"Actor: {actor_id}",
                                )
                            )
                    else:
                        actors = actor_registry.list_actors()
                        if fmt == "json":
                            print_json(
                                [
                                    {
                                        "id": str(a.id),
                                        "type": str(a.type),
                                        "role": a.role,
                                    }
                                    for a in actors
                                ]
                            )
                        else:
                            table = Table(title="Actors")
                            table.add_column("ID")
                            table.add_column("Type")
                            table.add_column("Role")
                            table.add_column("Team")
                            for a in actors:
                                table.add_row(
                                    str(a.id),
                                    str(a.type),
                                    a.role,
                                    getattr(a, "team", None) or "",
                                )
                            console.print(table)
                else:
                    console.print("[dim]No actor registry available[/dim]")

            elif resource == "policies":
                policy_engine = terrarium.registry.get("policy")
                policy_ids = await policy_engine.get_active_policies()
                if fmt == "json":
                    print_json([str(pid) for pid in policy_ids])
                else:
                    for i, pid in enumerate(policy_ids):
                        console.print(f"  {i + 1}. {pid}")
                    if not policy_ids:
                        console.print("[dim]No policies configured[/dim]")

            elif resource in ("services", "tools"):
                responder = terrarium.registry.get("responder")
                if hasattr(responder, "pack_registry"):
                    if resource == "services":
                        packs = responder.pack_registry.list_packs()
                        if fmt == "json":
                            print_json(packs)
                        else:
                            table = Table(title="Services")
                            table.add_column("Pack Name")
                            table.add_column("Tools")
                            table.add_column("Tier")
                            for p in packs:
                                table.add_row(
                                    p.get("pack_name", "?"),
                                    str(p.get("tool_count", 0)),
                                    str(p.get("fidelity_tier", p.get("tier", "?"))),
                                )
                            console.print(table)
                    else:
                        tools = responder.pack_registry.list_tools()
                        if fmt == "json":
                            print_json(tools)
                        else:
                            table = Table(title="Tools")
                            table.add_column("Name")
                            table.add_column("Service")
                            table.add_column("Description")
                            for t in tools:
                                table.add_row(
                                    t.get("name", "?"),
                                    t.get("pack_name", "?"),
                                    str(t.get("description", ""))[:60],
                                )
                            console.print(table)
                else:
                    console.print("[dim]No service packs registered[/dim]")

            else:
                print_error(
                    f"Unknown resource: {resource}. "
                    "Use: entities, actors, policies, services, tools"
                )
                raise typer.Exit(1)
    except TerrariumError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from None


# ===================================================================
# Command 9: list (NEW)
# ===================================================================


@app.command(name="list")
def list_resources(
    resource: Annotated[
        str,
        typer.Argument(help="What to list: runs, tools, services, engines, artifacts"),
    ],
    run_id: Annotated[
        str | None,
        typer.Option("--run", "-r", help="Run ID (for artifacts)"),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Maximum items to show")] = 20,
    fmt: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: cli, json"),
    ] = "cli",
) -> None:
    """List runs, tools, services, engines, or artifacts."""
    asyncio.run(_list_impl(resource, run_id, limit, fmt))


async def _list_impl(resource: str, run_id: str | None, limit: int, fmt: str) -> None:
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
                if hasattr(responder, "pack_registry"):
                    tools = responder.pack_registry.list_tools()
                    if fmt == "json":
                        print_json(tools)
                    else:
                        table = Table(title=f"Tools ({len(tools)})")
                        table.add_column("Name")
                        table.add_column("Service")
                        table.add_column("Description")
                        for t in tools[:limit]:
                            table.add_row(
                                t.get("name", "?"),
                                t.get("pack_name", "?"),
                                str(t.get("description", ""))[:60],
                            )
                        console.print(table)
                else:
                    console.print("[dim]No tools registered[/dim]")

            elif resource == "services":
                responder = terrarium.registry.get("responder")
                if hasattr(responder, "pack_registry"):
                    packs = responder.pack_registry.list_packs()
                    if fmt == "json":
                        print_json(packs)
                    else:
                        table = Table(title=f"Services ({len(packs)})")
                        table.add_column("Name")
                        table.add_column("Tools")
                        table.add_column("Tier")
                        for p in packs[:limit]:
                            table.add_row(
                                p.get("pack_name", "?"),
                                str(p.get("tool_count", 0)),
                                str(p.get("tier", "?")),
                            )
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
                        table.add_row(
                            a.get("type", "?"),
                            a.get("path", "?"),
                            str(a.get("size_bytes", 0)),
                        )
                    console.print(table)

            else:
                print_error(
                    f"Unknown resource: {resource}. Use: runs, tools, services, engines, artifacts"
                )
                raise typer.Exit(1)
    except TerrariumError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from None


# ===================================================================
# Command 10: show (NEW)
# ===================================================================


@app.command()
def show(
    resource: Annotated[str, typer.Argument(help="What to show: run, tool, service")],
    name: Annotated[str, typer.Argument(help="Resource name or ID")],
    fmt: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: cli, json"),
    ] = "cli",
) -> None:
    """Show detailed information about a run, tool, or service."""
    asyncio.run(_show_impl(resource, name, fmt))


async def _show_impl(resource: str, name: str, fmt: str) -> None:
    try:
        async with app_context() as terrarium:
            if resource == "run":
                from terrarium.core.types import RunId

                run_record = await terrarium.run_manager.get_run(RunId(name))
                if run_record is None:
                    print_error(f"Run not found: {name}")
                    raise typer.Exit(1)
                if fmt == "json":
                    print_json(run_record)
                else:
                    console.print(
                        Panel(
                            json.dumps(run_record, indent=2, default=str),
                            title=f"Run: {name}",
                        )
                    )

            elif resource == "tool":
                responder = terrarium.registry.get("responder")
                if hasattr(responder, "pack_registry"):
                    tools = responder.pack_registry.list_tools()
                    tool = next((t for t in tools if t.get("name") == name), None)
                    if tool is None:
                        print_error(f"Tool not found: {name}")
                        raise typer.Exit(1)
                    if fmt == "json":
                        print_json(tool)
                    else:
                        console.print(
                            Panel(
                                json.dumps(tool, indent=2, default=str),
                                title=f"Tool: {name}",
                            )
                        )
                else:
                    print_error("No service packs registered")
                    raise typer.Exit(1)

            elif resource == "service":
                responder = terrarium.registry.get("responder")
                if hasattr(responder, "pack_registry"):
                    try:
                        pack = responder.pack_registry.get_pack(name)
                    except (KeyError, AttributeError):
                        print_error(f"Service not found: {name}")
                        raise typer.Exit(1) from None
                    from terrarium.kernel.surface import ServiceSurface

                    surface = ServiceSurface.from_pack(pack)
                    data = {
                        "pack_name": pack.pack_name,
                        "category": getattr(pack, "category", ""),
                        "fidelity_tier": getattr(pack, "fidelity_tier", ""),
                        "operations": len(surface.operations),
                        "entity_schemas": list(surface.entity_schemas.keys()),
                        "state_machines": list(surface.state_machines.keys()),
                        "tools": [
                            {
                                "name": op.name,
                                "method": op.http_method,
                                "path": op.http_path,
                            }
                            for op in surface.operations
                        ],
                    }
                    if fmt == "json":
                        print_json(data)
                    else:
                        console.print(
                            Panel(
                                json.dumps(data, indent=2, default=str),
                                title=f"Service: {name}",
                            )
                        )
                else:
                    print_error("No service packs registered")
                    raise typer.Exit(1)

            else:
                print_error(f"Unknown resource: {resource}. Use: run, tool, service")
                raise typer.Exit(1)
    except TerrariumError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from None


# ===================================================================
# Command 11: snapshot (NEW)
# ===================================================================


@app.command()
def snapshot(
    label: Annotated[str, typer.Argument(help="Label for the snapshot")] = "manual",
) -> None:
    """Create a point-in-time snapshot of the current world state."""
    asyncio.run(_snapshot_impl(label))


async def _snapshot_impl(label: str) -> None:
    try:
        async with app_context() as terrarium:
            state = terrarium.registry.get("state")
            snapshot_id = await state.snapshot(label)
            print_success(f"Snapshot created: {snapshot_id} (label: {label})")
    except TerrariumError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from None


# ===================================================================
# Command 12: replay (NEW)
# ===================================================================


@app.command()
def replay(
    run_id: Annotated[str, typer.Argument(help="Run ID or tag to replay from")],
    tag: Annotated[
        str | None,
        typer.Option("--tag", "-t", help="Tag for the replay run"),
    ] = None,
) -> None:
    """Replay a previous run from its saved artifacts."""
    asyncio.run(_replay_impl(run_id, tag))


async def _replay_impl(run_id_str: str, tag: str | None) -> None:
    try:
        async with app_context() as terrarium:
            from terrarium.core.types import RunId

            source_run = await terrarium.run_manager.get_run(RunId(run_id_str))
            if source_run is None:
                print_error(f"Run not found: {run_id_str}")
                raise typer.Exit(1)

            config_artifact = await terrarium.artifact_store.load_artifact(
                RunId(source_run["run_id"]), "config"
            )
            if config_artifact is None:
                print_error(f"No config artifact found for run {run_id_str}")
                raise typer.Exit(1)

            console.print(f"[bold]Replaying run {run_id_str}...[/bold]")

            world_def = source_run.get("world_def", {})
            if not world_def:
                print_error("Run has no stored world definition -- cannot replay")
                raise typer.Exit(1)

            compiler = terrarium.registry.get("world_compiler")
            reconstructed_plan = await compiler.compile_from_dicts(
                world_def, source_run.get("config_snapshot", {}),
            )

            replay_tag = tag or f"replay-{run_id_str}"
            new_run_id = await terrarium.create_run(
                reconstructed_plan, mode=reconstructed_plan.mode, tag=replay_tag
            )

            event_log = await terrarium.artifact_store.load_artifact(
                RunId(source_run["run_id"]), "event_log"
            )
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

            await terrarium.end_run(new_run_id)
            print_success(f"Replay complete. New run: {new_run_id}")

            comparison = await terrarium.diff_runs([source_run["run_id"], str(new_run_id)])
            console.print(format_diff(comparison))
    except TerrariumError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from None


# ===================================================================
# Command 13: setup
# ===================================================================


@app.command()
def setup(
    provider: Annotated[
        str | None,
        typer.Argument(
            help="Provider to set up: anthropic, openai, google, claude-acp, codex-acp, all"
        ),
    ] = "all",
) -> None:
    """Interactive setup wizard -- configure LLM providers and ACP servers."""
    asyncio.run(_setup_impl(provider or "all"))


async def _setup_impl(provider: str) -> None:
    import os

    console.print("[bold]Terrarium Setup Wizard[/bold]\n")

    providers_to_check: dict[str, dict[str, str | None]] = {
        "google": {"env": "GOOGLE_API_KEY", "cli": None, "sdk": "google.genai"},
        "anthropic": {"env": "ANTHROPIC_API_KEY", "cli": "claude", "sdk": "anthropic"},
        "openai": {"env": "OPENAI_API_KEY", "cli": None, "sdk": "openai"},
        "claude-acp": {"env": None, "cli": "claude", "sdk": "acp_sdk"},
        "codex-acp": {"env": None, "cli": "codex", "sdk": "acp_sdk"},
    }

    if provider != "all":
        if provider not in providers_to_check:
            print_error(
                f"Unknown provider: {provider}. "
                f"Options: {', '.join(providers_to_check.keys())}, all"
            )
            raise typer.Exit(1)
        providers_to_check = {provider: providers_to_check[provider]}

    for name, info in providers_to_check.items():
        console.print(f"\n[bold]--- {name.upper()} ---[/bold]")

        cli_name = info["cli"]
        if cli_name:
            cli_path = shutil.which(cli_name)
            if cli_path:
                console.print(f"  CLI [{cli_name}]: [green]found[/green] at {cli_path}")
            else:
                console.print(f"  CLI [{cli_name}]: [red]not found[/red]")

        env_var = info["env"]
        if env_var:
            env_val = os.environ.get(env_var)
            if env_val:
                masked = env_val[:4] + "..." + env_val[-4:] if len(env_val) > 8 else "***"
                console.print(f"  API key [{env_var}]: [green]set[/green] ({masked})")
            else:
                console.print(f"  API key [{env_var}]: [red]not set[/red]")

        sdk_name = info["sdk"]
        if sdk_name:
            try:
                __import__(sdk_name)
                console.print(f"  SDK [{sdk_name}]: [green]available[/green]")
            except ImportError:
                console.print(f"  SDK [{sdk_name}]: [red]not installed[/red]")

    console.print("\n[bold]Setup complete.[/bold] Run 'terrarium check' to verify connectivity.")


# ===================================================================
# Command 14: check
# ===================================================================


@app.command()
def check(
    test: Annotated[
        bool,
        typer.Option("--test", "-t", help="Run real API tests for configured providers"),
    ] = False,
) -> None:
    """Check system requirements and provider connectivity."""
    asyncio.run(_check_impl(test))


async def _check_impl(run_tests: bool) -> None:
    import os
    import sys

    console.print("[bold]Terrarium System Check[/bold]\n")

    # Python version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok = sys.version_info >= (3, 12)
    status = "[green]OK[/green]" if ok else "[red]FAIL[/red]"
    console.print(f"Python: {py_ver} {status}")

    # Required packages
    packages = [
        "pydantic",
        "aiosqlite",
        "typer",
        "fastapi",
        "httpx",
        "mcp",
        "yaml",
        "rich",
    ]
    for pkg in packages:
        try:
            __import__(pkg)
            console.print(f"  {pkg}: [green]installed[/green]")
        except ImportError:
            console.print(f"  {pkg}: [red]missing[/red]")

    # LLM providers
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

    # Engine health (requires full app bootstrap)
    if run_tests:
        console.print("\n[bold]Engine Health (starting app)...[/bold]")
        try:
            async with app_context() as terrarium:
                health = terrarium.health
                if health is None:
                    print_error("Health aggregator not initialized")
                    raise typer.Exit(1)
                results = await health.check_all()
                console.print(format_health_table(results))

                if health.is_healthy():
                    print_success("All engines healthy")
                else:
                    print_warning("Some engines unhealthy")
        except Exception as exc:
            print_error(f"App startup failed: {type(exc).__name__}: {exc}")
    else:
        console.print("\n[dim]Use --test to start the app and check engine health[/dim]")

    # Config files
    console.print("\n[bold]Configuration:[/bold]")
    config_files = [
        "terrarium.toml",
        "terrarium.development.toml",
        "terrarium.local.toml",
    ]
    for cf in config_files:
        exists = Path(cf).exists()
        file_status = "[green]found[/green]" if exists else "[dim]not found[/dim]"
        console.print(f"  {cf}: {file_status}")


# ===================================================================
# Command 15: ledger
# ===================================================================


@app.command()
def ledger(
    tail: Annotated[
        int,
        typer.Option("--tail", "-n", help="Number of recent entries to show"),
    ] = 50,
    filter_type: Annotated[
        str | None,
        typer.Option(
            "--type",
            help=(
                "Filter by entry type (pipeline_step, state_mutation, "
                "llm_call, gateway_request, validation, engine_lifecycle, "
                "snapshot, actor_activation, action_generation)"
            ),
        ),
    ] = None,
    actor_filter: Annotated[
        str | None,
        typer.Option("--actor", "-a", help="Filter by actor ID"),
    ] = None,
    engine: Annotated[
        str | None,
        typer.Option("--engine", "-e", help="Filter by engine name"),
    ] = None,
    fmt: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: cli, json"),
    ] = "cli",
) -> None:
    """Query and display audit ledger entries."""
    asyncio.run(_ledger_impl(tail, filter_type, actor_filter, engine, fmt))


async def _ledger_impl(
    tail: int,
    filter_type: str | None,
    actor_filter: str | None,
    engine: str | None,
    fmt: str,
) -> None:
    try:
        async with app_context() as terrarium:
            from terrarium.core.types import ActorId
            from terrarium.ledger.query import LedgerQueryBuilder

            builder = LedgerQueryBuilder().limit(tail)
            if filter_type:
                builder = builder.filter_type(filter_type)
            if actor_filter:
                builder = builder.filter_actor(ActorId(actor_filter))
            if engine:
                builder = builder.filter_engine(engine)

            query = builder.build()
            entries = await terrarium.ledger.query(query)

            if fmt == "json":
                print_json(
                    [e.model_dump(mode="json") if hasattr(e, "model_dump") else e for e in entries]
                )
            else:
                console.print(format_ledger_table(entries))
                console.print(f"\n[dim]Showing {len(entries)} entries (limit: {tail})[/dim]")
    except TerrariumError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from None


# ===================================================================
# Feedback commands (5) — G4a
# ===================================================================


@app.command()
def annotate(
    service: Annotated[str, typer.Argument(help="Service name to annotate")],
    message: Annotated[
        str | None,
        typer.Option("--message", "-m", help="Annotation text"),
    ] = None,
    tag: Annotated[
        str | None,
        typer.Option("--tag", "-t", help="Annotation tag"),
    ] = None,
    run_id: Annotated[
        str | None,
        typer.Option("--run", "-r", help="Associated run ID"),
    ] = None,
) -> None:
    """Add a behavioral annotation to a service."""
    asyncio.run(_annotate_impl(service, message, tag, run_id))


async def _annotate_impl(
    service: str, message: str | None, tag: str | None, run_id: str | None
) -> None:
    if not message:
        print_error("Annotation text is required: --message / -m")
        raise typer.Exit(1)
    try:
        async with app_context() as terrarium:
            feedback = terrarium.registry.get("feedback")
            seq = await feedback.add_annotation(
                service_id=service,
                text=message,
                author="user",
                tag=tag,
                run_id=run_id,
            )
            console.print(f"[green]Annotation #{seq} added to '{service}'[/green]")
            console.print(f"  Text: {message}")
            if tag:
                console.print(f"  Tag: {tag}")
    except (TerrariumError, RuntimeError) as exc:
        print_error(str(exc))
        raise typer.Exit(1)


@app.command()
def capture(
    service: Annotated[str, typer.Argument(help="Service name to capture")],
    run_from: Annotated[
        str,
        typer.Option("--run", "-r", help="Run ID to capture from"),
    ] = "last",
) -> None:
    """Capture a bootstrapped service surface from a completed run."""
    asyncio.run(_capture_impl(service, run_from))


async def _capture_impl(service: str, run_from: str) -> None:
    try:
        async with app_context() as terrarium:
            # Resolve "last" to the most recent run
            actual_run_id = run_from
            if run_from == "last":
                from terrarium.core.types import RunId
                runs = await terrarium.run_manager.list_runs()
                if not runs:
                    print_error("No runs found")
                    raise typer.Exit(1)
                actual_run_id = runs[0]["run_id"]

            feedback = terrarium.registry.get("feedback")
            captured = await feedback.capture_service(actual_run_id, service)

            console.print(f"[bold]Captured surface for '{service}' from run {actual_run_id}[/bold]")
            console.print(f"  Operations: {len(captured.operations_observed)}")
            for op in captured.operations_observed:
                console.print(f"    - {op.name} (called {op.call_count}x)")
            console.print(f"  Entity mutations: {len(captured.entity_mutations)}")
            for mut in captured.entity_mutations:
                console.print(f"    - {mut.entity_type}.{mut.operation} ({mut.count}x)")
            console.print(f"  Errors: {len(captured.error_patterns)}")
            console.print(f"  Annotations: {len(captured.annotations)}")
            console.print(f"  Behavioral rules: {len(captured.behavioral_rules)}")
    except (TerrariumError, RuntimeError) as exc:
        print_error(str(exc))
        raise typer.Exit(1)


@app.command()
def promote(
    service: Annotated[str, typer.Argument(help="Service name to promote")],
    submit_pr: Annotated[
        bool,
        typer.Option("--submit-pr", help="Print instructions for submitting a community PR"),
    ] = False,
) -> None:
    """Promote a bootstrapped service to Tier 2 curated profile."""
    asyncio.run(_promote_impl(service, submit_pr))


async def _promote_impl(service: str, submit_pr: bool) -> None:
    try:
        async with app_context() as terrarium:
            feedback = terrarium.registry.get("feedback")
            responder = terrarium.registry.get("responder")
            profile_registry = getattr(responder, "_profile_registry", None)

            if not profile_registry:
                print_error("Profile registry not available")
                raise typer.Exit(1)

            profile = profile_registry.get_profile(service)
            if profile is None:
                print_error(f"No profile found for '{service}'")
                raise typer.Exit(1)

            # Build captured surface from profile data for evaluation
            from terrarium.engines.feedback.models import (
                CapturedSurface,
                ObservedMutation,
                ObservedOperation,
            )
            from datetime import UTC, datetime

            captured = CapturedSurface(
                service_name=service,
                run_id="manual-promote",
                captured_at=datetime.now(UTC).isoformat(),
                operations_observed=[
                    ObservedOperation(
                        name=op.name,
                        call_count=1,
                        parameter_keys=(
                            list(op.parameters.keys())
                            if op.parameters else []
                        ),
                        response_keys=(
                            list(
                                op.response_schema.get(
                                    "properties", {}
                                ).keys()
                            )
                            if op.response_schema else []
                        ),
                    )
                    for op in profile.operations
                ],
                # H10 fix: include entity mutations from profile
                entity_mutations=[
                    ObservedMutation(
                        entity_type=e.name,
                        operation="create",
                        count=1,
                    )
                    for e in profile.entities
                ],
                fidelity_source=profile.fidelity_source,
            )

            evaluation = await feedback.evaluate_promotion(service, captured)

            console.print(f"[bold]Promotion evaluation for '{service}'[/bold]")
            console.print(f"  Current: {evaluation.current_fidelity}")
            console.print(f"  Eligible: {'[green]Yes[/green]' if evaluation.eligible else '[red]No[/red]'}")
            for met in evaluation.criteria_met:
                console.print(f"  [green]✓[/green] {met}")
            for missing in evaluation.criteria_missing:
                console.print(f"  [red]✗[/red] {missing}")
            console.print(f"  Recommendation: {evaluation.recommendation}")

            if evaluation.eligible:
                result = await feedback.promote_service(service, profile)
                console.print(f"\n[green]Promoted '{service}' to {result.new_fidelity} (v{result.version})[/green]")
                if result.profile_path:
                    console.print(f"  Saved: {result.profile_path}")

            if submit_pr:
                console.print("\n[yellow]To submit to community profiles:[/yellow]")
                console.print("  1. Fork https://github.com/terrarium-project/profiles")
                console.print(f"  2. Copy the profile YAML to profiles/{service}.profile.yaml")
                console.print("  3. Submit a pull request")

    except (TerrariumError, RuntimeError) as exc:
        print_error(str(exc))
        raise typer.Exit(1)


@app.command()
def compile_pack(
    service: Annotated[str, typer.Argument(help="Service name to compile a pack for")],
    from_source: Annotated[str, typer.Argument(help="Source profile path or service name")],
) -> None:
    """Generate a Tier 1 verified pack scaffold from a profile."""
    asyncio.run(_compile_pack_impl(service, from_source))


async def _compile_pack_impl(service: str, from_source: str) -> None:
    from pathlib import Path

    try:
        from terrarium.engines.feedback.pack_compiler import PackCompiler
        from terrarium.packs.profile_loader import ProfileLoader

        # Load profile from file path or service name
        source_path = Path(from_source)
        if source_path.exists():
            loader = ProfileLoader(source_path.parent)
            profile = loader.load(source_path.stem.replace(".profile", ""))
        else:
            async with app_context() as terrarium:
                responder = terrarium.registry.get("responder")
                registry = getattr(responder, "_profile_registry", None)
                profile = registry.get_profile(from_source) if registry else None

        if profile is None:
            print_error(f"Could not load profile from '{from_source}'")
            raise typer.Exit(1)

        compiler = PackCompiler()
        result = await compiler.compile(profile)

        console.print(f"[bold]Generated Tier 1 pack scaffold for '{service}'[/bold]")
        console.print(f"  Output: {result.output_dir}")
        console.print(f"  Files: {len(result.files_generated)}")
        for f in result.files_generated:
            console.print(f"    - {Path(f).name}")
        console.print(f"  Handler stubs: {result.handler_stubs}")
        console.print(
            "\n[yellow]Next: implement deterministic handlers in handlers.py[/yellow]"
        )

    except (TerrariumError, RuntimeError, OSError) as exc:
        print_error(str(exc))
        raise typer.Exit(1)


@app.command()
def verify_pack(
    service: Annotated[str, typer.Argument(help="Service name whose pack to validate")],
) -> None:
    """Validate a Tier 1 pack for correctness and completeness."""
    asyncio.run(_verify_pack_impl(service))


async def _verify_pack_impl(service: str) -> None:
    from pathlib import Path

    from terrarium.engines.feedback.pack_verifier import PackVerifier

    pack_dir = Path(__file__).resolve().parent / "packs" / "verified" / service
    if not pack_dir.exists():
        print_error(f"Pack directory not found: {pack_dir}")
        raise typer.Exit(1)

    verifier = PackVerifier()
    try:
        result = await verifier.verify(pack_dir)
    except (OSError, PermissionError) as exc:
        print_error(f"Cannot read pack files: {exc}")
        raise typer.Exit(1)

    console.print(f"[bold]Pack verification: {service}[/bold]")
    for check in result.checks:
        icon = "[green]✓[/green]" if check.passed else "[red]✗[/red]"
        console.print(f"  {icon} {check.name}: {check.message}")

    if result.warnings:
        console.print("\n[yellow]Warnings:[/yellow]")
        for w in result.warnings:
            console.print(f"  ⚠ {w}")

    if result.passed:
        console.print(f"\n[green]Pack '{service}' passed all checks[/green]")
    else:
        console.print(f"\n[red]Pack '{service}' failed verification[/red]")
        for e in result.errors:
            console.print(f"  {e}")
        raise typer.Exit(1)


# ===================================================================
# G4b: Sync + Signals commands
# ===================================================================


@app.command()
def sync(
    service: Annotated[
        str | None, typer.Argument(help="Service name to check (omit for all)")
    ] = None,
    check_all: Annotated[
        bool, typer.Option("--all", help="Check all profiled services")
    ] = False,
    apply: Annotated[
        bool, typer.Option("--apply", help="Apply proposed updates")
    ] = False,
) -> None:
    """Check external API drift for profiled services."""
    asyncio.run(_sync_impl(service, check_all, apply))


async def _sync_impl(
    service: str | None, check_all: bool, apply: bool
) -> None:
    try:
        async with app_context() as terrarium:
            feedback = terrarium.registry.get("feedback")

            if check_all or service is None:
                reports = await feedback.check_sync_all()
                if not reports:
                    console.print("[green]No drift detected across all services[/green]")
                    return
                console.print(f"[bold]Drift detected in {len(reports)} source(s):[/bold]")
                for report in reports:
                    _print_drift_report(report)
            else:
                reports = await feedback.check_sync(service)
                if not reports:
                    console.print(f"[green]No drift for '{service}'[/green]")
                    return
                for report in reports:
                    _print_drift_report(report)

                if apply and reports:
                    proposal = await feedback.propose_sync_update(service)
                    if proposal:
                        console.print(
                            f"\n[bold]Proposed {len(proposal.proposed_changes)} changes:[/bold]"
                        )
                        for change in proposal.proposed_changes:
                            console.print(f"  - {change.change_type}: {change.description}")
                        updated = await feedback.apply_sync_update(service, proposal)
                        console.print(
                            f"\n[green]Applied. Profile updated to v{updated.version}[/green]"
                        )
    except (TerrariumError, RuntimeError) as exc:
        print_error(str(exc))
        raise typer.Exit(1)


def _print_drift_report(report: Any) -> None:
    """Pretty-print a DriftReport."""
    console.print(f"\n  [bold]{report.service_name}[/bold] ({report.source})")
    if report.operations_added:
        shown = report.operations_added[:5]
        extra = len(report.operations_added) - 5
        suffix = f" (+{extra} more)" if extra > 0 else ""
        console.print(f"    Added: {', '.join(shown)}{suffix}")
    if report.operations_removed:
        shown = report.operations_removed[:5]
        extra = len(report.operations_removed) - 5
        suffix = f" (+{extra} more)" if extra > 0 else ""
        console.print(f"    Removed: {', '.join(shown)}{suffix}")
    if report.summary:
        console.print(f"    Summary: {report.summary}")


@app.command()
def signals(
    fmt: Annotated[
        str, typer.Option("--format", "-f", help="Output format")
    ] = "table",
) -> None:
    """Display local signals from your run history."""
    asyncio.run(_signals_impl(fmt))


async def _signals_impl(fmt: str) -> None:
    try:
        async with app_context() as terrarium:
            feedback = terrarium.registry.get("feedback")
            result = await feedback.get_local_signals()

            if fmt == "json":
                import json
                console.print(json.dumps(result.model_dump(mode="json"), indent=2))
                return

            console.print(f"[bold]Local Signals[/bold] ({result.total_runs} runs)")
            console.print()

            for name, signal in result.signals.items():
                console.print(f"  [bold]{name}[/bold]: {signal.summary}")
                for entry in signal.entries[:5]:
                    parts = [f"{k}={v}" for k, v in entry.items()]
                    console.print(f"    {', '.join(parts)}")
                if len(signal.entries) > 5:
                    console.print(
                        f"    ... and {len(signal.entries) - 5} more"
                    )
                console.print()

    except (TerrariumError, RuntimeError) as exc:
        print_error(str(exc))
        raise typer.Exit(1)


# ===================================================================
# Agent Integration: config export + attach/detach
# ===================================================================


@app.command(name="config")
def config_cmd(
    export: Annotated[
        str,
        typer.Option("--export", help="Export target (e.g., claude-desktop, openai-tools)"),
    ] = "",
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8080,
) -> None:
    """Export configuration for agent integration."""
    if not export:
        from terrarium.cli_exports.templates import EXPORT_REGISTRY

        console.print("[bold]Available export targets:[/bold]")
        for name in sorted(EXPORT_REGISTRY.keys()):
            console.print(f"  terrarium config --export {name}")
        return

    from terrarium.cli_exports.templates import EXPORT_REGISTRY

    template_fn = EXPORT_REGISTRY.get(export)
    if template_fn is None:
        print_error(
            f"Unknown export target: '{export}'. "
            f"Available: {', '.join(sorted(EXPORT_REGISTRY.keys()))}"
        )
        raise typer.Exit(1)

    url = f"http://{host}:{port}"

    # For tool-manifest exports, fetch tools from a running server
    if export in ("openai-tools", "anthropic-tools"):
        try:
            from terrarium.sdk import get_tool_manifest

            fmt = "openai" if export == "openai-tools" else "anthropic"
            tools = get_tool_manifest(url=url, format=fmt)
        except Exception:
            tools = []
            console.print(
                f"[yellow]Could not fetch tools from {url} — "
                f"using empty list[/yellow]"
            )
    else:
        tools = []

    output = template_fn(url, tools)
    console.print(output)


@app.command()
def attach(
    agent: Annotated[str, typer.Argument(help="Agent type: claude-desktop, cursor, windsurf")],
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8080,
) -> None:
    """Patch agent config to connect to Terrarium."""
    import json

    from terrarium.cli_exports.attach import _get_config_path, patch_config
    from terrarium.cli_exports.templates import EXPORT_REGISTRY

    config_path = _get_config_path(agent)
    if config_path is None:
        print_error(f"Unknown agent type: '{agent}'")
        raise typer.Exit(1)

    template_fn = EXPORT_REGISTRY.get(agent)
    if template_fn is None:
        print_error(f"No export template for '{agent}'")
        raise typer.Exit(1)

    url = f"http://{host}:{port}"
    snippet = template_fn(url, [])
    patch = json.loads(snippet)

    patch_config(config_path, patch)
    console.print(f"[green]Attached to {agent} at {config_path}[/green]")
    console.print(f"  Terrarium URL: {url}")
    console.print(f"  Backup: {config_path}.terrarium-backup")


@app.command()
def detach(
    agent: Annotated[str, typer.Argument(help="Agent type to restore")],
) -> None:
    """Restore agent config from backup."""
    from terrarium.cli_exports.attach import _get_config_path, restore_config

    config_path = _get_config_path(agent)
    if config_path is None:
        print_error(f"Unknown agent type: '{agent}'")
        raise typer.Exit(1)

    if restore_config(config_path):
        console.print(f"[green]Detached from {agent} — config restored[/green]")
    else:
        print_error(f"No backup found for {agent} at {config_path}")
        raise typer.Exit(1)


# ===================================================================
# Command: dashboard
# ===================================================================


@app.command()
def dashboard(
    host: Annotated[
        str, typer.Option("--host", help="API server bind host"),
    ] = "127.0.0.1",
    port: Annotated[
        int, typer.Option("--port", "-p", help="API server bind port"),
    ] = 8200,
    env: Annotated[
        str, typer.Option("--env", "-e", help="Config environment (maps to terrarium.{env}.toml)"),
    ] = "development",
) -> None:
    """Start the dashboard API server for browsing historical runs.

    No world compilation needed -- serves run data from disk.
    """
    asyncio.run(_dashboard_impl(host, port, env))


async def _dashboard_impl(host: str, port: int, env: str) -> None:
    try:
        async with app_context(env=env) as terrarium:
            console.print("[bold]Starting dashboard API server...[/bold]")

            # Create FastAPI app with all routes
            await terrarium.gateway.start_adapters()

            # Get the HTTP adapter and start uvicorn
            http_adapter = terrarium.gateway._adapters.get("http")
            if http_adapter is None:
                print_error("No HTTP adapter registered in gateway")
                raise typer.Exit(1)

            run_count = len(await terrarium.run_manager.list_runs())
            console.print(f"[green]Dashboard API: http://{host}:{port}[/green]")
            console.print(f"[green]Historical runs available: {run_count}[/green]")
            console.print("[dim]Press Ctrl+C to stop[/dim]")

            # This blocks until the server is shut down
            await http_adapter.run_server(host=host, port=port)
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down dashboard...[/yellow]")
    except Exception as exc:
        print_error(str(exc))
        raise typer.Exit(1) from None
