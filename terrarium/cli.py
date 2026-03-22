"""Terrarium CLI — command interface for managing programmable worlds."""

from pathlib import Path
from typing import Annotated, Optional

import typer

app = typer.Typer(
    name="terrarium",
    help="Programmable worlds for artificial intelligence.",
    no_args_is_help=True,
)


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
        Optional[list[str]],
        typer.Option("--seed", help="Seed data files (repeatable)"),
    ] = None,
    override: Annotated[
        Optional[list[str]],
        typer.Option("--override", help="Reality condition overrides (repeatable, key=value)"),
    ] = None,
    overlay: Annotated[
        Optional[list[str]],
        typer.Option("--overlay", help="Additional overlay files (repeatable)"),
    ] = None,
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output path for the compiled world"),
    ] = Path("./world.yaml"),
) -> None:
    """Create a new world from a natural language description."""
    raise NotImplementedError


@app.command()
def run(
    world: Annotated[str, typer.Argument(help="Path or ID of the compiled world to run")],
    agent: Annotated[
        Optional[str],
        typer.Option("--agent", "-a", help="Agent adapter to connect"),
    ] = None,
    actor: Annotated[
        Optional[str],
        typer.Option("--actor", help="Actor ID to assign the agent to"),
    ] = None,
    mode: Annotated[
        Optional[str],
        typer.Option("--mode", "-m", help="Override world mode: governed, ungoverned"),
    ] = None,
    tag: Annotated[
        Optional[str],
        typer.Option("--tag", "-t", help="Tag for this run"),
    ] = None,
) -> None:
    """Run a simulation on a compiled world."""
    raise NotImplementedError


@app.command()
def plan(
    description: Annotated[str, typer.Argument(help="Natural language world description")],
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Path to write the generated world plan"),
    ] = None,
) -> None:
    """Generate a world plan from a natural language description without executing it."""
    raise NotImplementedError


@app.command()
def report(
    world: Annotated[str, typer.Argument(help="Name or ID of the world to report on")],
    run_id: Annotated[
        Optional[str],
        typer.Option("--run", "-r", help="Specific run ID (default: latest)"),
    ] = None,
    format: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: json, markdown"),
    ] = "markdown",
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Output file path (default: stdout)"),
    ] = None,
) -> None:
    """Generate a report for a world run."""
    raise NotImplementedError


@app.command()
def diff(
    runs: Annotated[
        list[str],
        typer.Argument(help="Run tags or IDs to compare"),
    ],
    format: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: cli, json, markdown"),
    ] = "cli",
) -> None:
    """Show differences between runs."""
    raise NotImplementedError


@app.command()
def dashboard(
    host: Annotated[
        str,
        typer.Option("--host", help="Dashboard bind host"),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", "-p", help="Dashboard bind port"),
    ] = 8200,
) -> None:
    """Launch the live observation dashboard."""
    raise NotImplementedError


@app.command()
def annotate(
    world: Annotated[str, typer.Argument(help="Name or ID of the world")],
    run_id: Annotated[
        Optional[str],
        typer.Option("--run", "-r", help="Specific run ID (default: latest)"),
    ] = None,
    message: Annotated[
        Optional[str],
        typer.Option("--message", "-m", help="Annotation text (interactive prompt if omitted)"),
    ] = None,
    tag: Annotated[
        Optional[str],
        typer.Option("--tag", "-t", help="Annotation tag for filtering"),
    ] = None,
) -> None:
    """Add a human annotation to a world run for feedback and evaluation."""
    raise NotImplementedError


@app.command()
def ledger(
    world: Annotated[str, typer.Argument(help="Name or ID of the world")],
    run_id: Annotated[
        Optional[str],
        typer.Option("--run", "-r", help="Specific run ID (default: latest)"),
    ] = None,
    tail: Annotated[
        int,
        typer.Option("--tail", "-n", help="Number of recent entries to show"),
    ] = 50,
    filter_type: Annotated[
        Optional[str],
        typer.Option("--type", help="Filter by entry type (pipeline, state, llm, gateway)"),
    ] = None,
) -> None:
    """Query and display ledger entries for a world run."""
    raise NotImplementedError


# -- Fidelity pack lifecycle commands -----------------------------------------


@app.command()
def compile_pack(
    service: Annotated[str, typer.Argument(help="Service name to compile a pack for")],
    from_source: Annotated[str, typer.Argument(help="Source profile or captured service to compile from")],
) -> None:
    """Generate a Tier 1 verified pack from a profile or captured service."""
    raise NotImplementedError


@app.command()
def verify_pack(
    service: Annotated[str, typer.Argument(help="Service name whose pack to validate")],
) -> None:
    """Validate a Tier 1 pack for correctness and completeness."""
    raise NotImplementedError


@app.command()
def capture(
    service: Annotated[str, typer.Argument(help="Service name to capture")],
    run: Annotated[
        str,
        typer.Option("--run", "-r", help="Run ID to capture from (default: last)"),
    ] = "last",
) -> None:
    """Capture a bootstrapped service surface from a completed run."""
    raise NotImplementedError


@app.command()
def promote(
    service: Annotated[str, typer.Argument(help="Service name to promote")],
    submit_pr: Annotated[
        bool,
        typer.Option("--submit-pr", help="Submit a PR to the community profiles repo"),
    ] = False,
) -> None:
    """Promote a captured service to Tier 2 community profile."""
    raise NotImplementedError


@app.command()
def setup(
    provider: Annotated[
        Optional[str],
        typer.Argument(help="Provider to set up: anthropic, openai, google, claude-acp, codex-acp, all"),
    ] = "all",
) -> None:
    """Interactive setup wizard — configure LLM providers and ACP servers.

    Detects installed CLIs, prompts for API keys, starts ACP servers,
    and validates connections. Run this after installing Terrarium.

    \b
    Examples:
        terrarium setup              # set up all available providers
        terrarium setup anthropic    # set up Anthropic API only
        terrarium setup claude-acp   # set up Claude Code via ACP
    """
    raise NotImplementedError


@app.command()
def check(
    test: Annotated[
        bool,
        typer.Option("--test", "-t", help="Run real API tests for configured providers"),
    ] = False,
) -> None:
    """Check system requirements and provider connectivity.

    Shows which CLIs are installed, which API keys are set,
    which ACP servers are running, and which Python SDKs are available.

    \b
    Examples:
        terrarium check          # show provider availability
        terrarium check --test   # also run real API tests
    """
    raise NotImplementedError
