# Plan B: CLI `--preset` and `--actors` Flags

## Context

The spec shows `terrarium run --preset prediction --actors macro-economist,technical-analyst,risk-analyst`. Neither flag exists. Users can't launch collaborative intelligence from CLI as documented. This is the "front door" to Mode 2.

## What Already Exists (verified)
- `load_preset(name)` at `deliverable_presets/__init__.py:33` — loads YAML, validates keys, returns dict
- `WorldPlan` accepts `deliverable` dict and `actor_specs` list
- `configure_agency()` at `app.py:694` already reads `actor_specs` from plan
- `_run_impl()` at `cli.py:411` already handles compilation from NL and YAML
- `--agents` flag at `cli.py:290` exists but is for external agent adapter config, NOT for defining actor roles

## File to Modify

**`terrarium/cli.py`** — 2 insertion points

### Insertion 1: Add flags to `run()` command (line 278)

Current params end at line 292 with `agents`. Insert BEFORE the closing paren:

```python
    # Existing params above...
    agents: Annotated[str | None, typer.Option("--agents", ...)] = None,
    # NEW:
    preset: Annotated[
        str | None,
        typer.Option(
            "--preset",
            help="Deliverable preset: synthesis, decision, prediction, brainstorm, recommendation, assessment",
        ),
    ] = None,
    actor_roles: Annotated[
        str | None,
        typer.Option(
            "--actors",
            help="Comma-separated internal actor roles (e.g. 'economist,analyst,strategist'). First role is lead.",
        ),
    ] = None,
```

Update the `run()` body to pass these to `_run_impl()`:

```python
asyncio.run(_run_impl(
    world, settings, agent, actor, mode, tag, behavior, serve,
    world_id, host, port, agents,
    preset=preset, actor_roles=actor_roles,  # NEW
))
```

### Insertion 2: Add params to `_run_impl()` (line 411)

Add to signature:

```python
async def _run_impl(
    ...existing params...,
    preset: str | None = None,        # NEW
    actor_roles: str | None = None,   # NEW
) -> None:
```

Insert AFTER the plan is compiled (after line 458 — after `compiled_plan` is set from either YAML, NL, or loaded world) but BEFORE `create_run()`:

```python
            # Apply --preset flag: inject deliverable preset into plan
            if preset:
                from terrarium.deliverable_presets import load_preset as _load_preset
                try:
                    preset_data = _load_preset(preset)
                    compiled_plan = compiled_plan.model_copy(update={
                        "deliverable": {"preset": preset, **preset_data},
                    })
                    console.print(f"  Deliverable preset: [cyan]{preset}[/cyan]")
                except (FileNotFoundError, ValueError) as exc:
                    print_error(f"Invalid preset '{preset}': {exc}")
                    raise typer.Exit(1) from None

            # Apply --actors flag: override actor_specs with inline roles
            if actor_roles:
                roles = [r.strip() for r in actor_roles.split(",") if r.strip()]
                if not roles:
                    print_error("--actors requires at least one role")
                    raise typer.Exit(1) from None
                actor_specs = []
                for i, role in enumerate(roles):
                    spec: dict[str, Any] = {
                        "role": role,
                        "type": "internal",
                        "count": 1,
                    }
                    if i == 0:
                        spec["lead"] = True  # first role is lead
                    actor_specs.append(spec)
                compiled_plan = compiled_plan.model_copy(
                    update={"actor_specs": actor_specs}
                )
                console.print(
                    f"  Actors: [cyan]{', '.join(roles)}[/cyan] "
                    f"(lead: {roles[0]})"
                )
```

## What Does NOT Change
- `load_preset()` — already exists, no modifications
- `configure_agency()` — already reads actor_specs from plan
- `WorldPlan` model — already accepts deliverable and actor_specs
- `--agents` flag — stays as-is (different purpose: external agent adapter)
- Existing `terrarium run world.yaml` — unchanged when new flags not provided

## Test Harness

**`tests/cli/test_preset_actors_flags.py`**

```python
"""Test harness for --preset and --actors CLI flags.

These tests verify structural contracts, not specific LLM behavior.
If a new preset is added, the harness catches if it's not loadable.
If actor_specs format changes, the harness catches if CLI wiring breaks.
"""

class TestPresetFlag:
    def test_all_presets_loadable(self):
        """Every preset name accepted by --preset must be loadable."""
        from terrarium.deliverable_presets import load_preset, list_presets
        for name in list_presets():
            data = load_preset(name)
            assert "schema" in data, f"Preset '{name}' missing 'schema'"
            assert "prompt_instructions" in data, f"Preset '{name}' missing 'prompt_instructions'"

    def test_invalid_preset_raises(self):
        """Unknown preset name raises ValueError."""
        from terrarium.deliverable_presets import load_preset
        with pytest.raises((FileNotFoundError, ValueError)):
            load_preset("nonexistent_preset")

    def test_preset_injects_into_plan(self):
        """--preset modifies compiled_plan.deliverable correctly."""
        from terrarium.deliverable_presets import load_preset
        preset_data = load_preset("synthesis")
        plan = WorldPlan(name="test", seed=42, ...)
        updated = plan.model_copy(update={"deliverable": {"preset": "synthesis", **preset_data}})
        assert updated.deliverable["preset"] == "synthesis"
        assert "schema" in updated.deliverable

class TestActorsFlag:
    def test_single_actor_is_lead(self):
        """Single role → lead=True."""
        roles = ["economist"]
        specs = [{"role": r, "type": "internal", "count": 1, **({"lead": True} if i == 0 else {})} for i, r in enumerate(roles)]
        assert specs[0]["lead"] is True

    def test_multiple_actors_first_is_lead(self):
        """First of multiple roles is lead."""
        roles = ["economist", "analyst", "strategist"]
        specs = [{"role": r, "type": "internal", "count": 1, **({"lead": True} if i == 0 else {})} for i, r in enumerate(roles)]
        assert specs[0].get("lead") is True
        assert "lead" not in specs[1]
        assert "lead" not in specs[2]

    def test_empty_actors_string(self):
        """Empty --actors string produces empty list."""
        roles = [r.strip() for r in "".split(",") if r.strip()]
        assert roles == []

    def test_actors_override_plan_specs(self):
        """--actors replaces existing actor_specs entirely."""
        plan = WorldPlan(name="test", seed=42, actor_specs=[{"role": "old", "type": "internal"}])
        new_specs = [{"role": "new", "type": "internal", "count": 1, "lead": True}]
        updated = plan.model_copy(update={"actor_specs": new_specs})
        assert len(updated.actor_specs) == 1
        assert updated.actor_specs[0]["role"] == "new"
```

## Verification
1. `uv run terrarium run --help` — shows `--preset` and `--actors` in help text
2. `uv run pytest tests/cli/test_preset_actors_flags.py -v` — all pass
3. `uv run terrarium run "Market analysis" --preset prediction --actors economist,analyst,strategist --tag cli-test` — runs end-to-end
4. Existing tests: `uv run pytest tests/ -q --ignore=tests/live` — no regressions
