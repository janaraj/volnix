# Plan C: Automatic Deliverable Triggering

## Context

Deliverable presets exist (6 YAML schemas), the lead actor concept exists, synthesis deadline is mentioned in the plan — but nothing actually triggers the lead actor to produce a deliverable. The simulation runs, actors collaborate, but no structured output is produced.

## Design

Three-tier end condition with automatic synthesis triggering:

```
Tick 1-90:    Normal collaboration
Tick 90:      Synthesis deadline fires (lead's ScheduledAction)
              Lead's prompt says "Produce deliverable NOW"
              Lead returns deliverable in state_updates
              SimulationRunner extracts + saves as artifact
              → Simulation ends

OR at any tick: Lead naturally produces deliverable
               → Same extraction + end

OR Tick 100:   Hard limit. No deliverable. Best-effort summary.
```

## Files to Modify

| # | File | Change |
|---|---|---|
| 1 | `terrarium/app.py` | `configure_agency()` — generate synthesis deadline ScheduledAction on lead actor |
| 2 | `terrarium/engines/agency/engine.py` | `_apply_state_updates()` — detect `deliverable` flag, extract content. `_tier1_activation_check()` — add synthesis_deadline trigger. |
| 3 | `terrarium/simulation/runner.py` | Detect `deliverable_produced` flag. Save deliverable artifact. End simulation. |
| 4 | `terrarium/engines/agency/prompt_builder.py` | When activation_reason is `synthesis_deadline`, inject preset schema + instructions into prompt |
| 5 | `terrarium/runs/artifacts.py` | Add "deliverable" to `_ALLOWED_ARTIFACT_TYPES` |

## Key Implementation Details

### 1. Synthesis Deadline Generation (`app.py` → `configure_agency()`)

After creating ActorStates, find the lead actor and add a ScheduledAction:

```python
# Find lead actor
lead_actor = None
for actor_def in actors:
    spec = next((s for s in plan.actor_specs if s.get("role") == actor_def.role), {})
    if spec.get("lead"):
        lead_actor = actor_def
        break

# If no explicit lead, first actor is lead (compiler default)
if lead_actor is None and actors:
    lead_actor = actors[0]

# Set synthesis deadline on lead
if lead_actor:
    max_ticks = self._config.simulation_runner.max_ticks
    buffer = int(max_ticks * self._config.agency.synthesis_buffer_pct)
    deadline_tick = max_ticks - buffer

    lead_state = agency._actor_states.get(lead_actor.id)
    if lead_state:
        lead_state.scheduled_action = ScheduledAction(
            logical_time=float(deadline_tick),
            action_type="produce_deliverable",
            description="Synthesis deadline — produce final deliverable",
        )
        lead_state.goal_context = (
            f"synthesis_deadline at tick {deadline_tick}. "
            f"You are the lead. When the deadline fires, produce the deliverable."
        )
```

### 2. Tier1 Activation Check (`agency/engine.py`)

Add after existing scheduled action check:

```python
# Trigger 5: Synthesis deadline
if (
    actor.scheduled_action
    and actor.scheduled_action.action_type == "produce_deliverable"
    and actor.scheduled_action.logical_time <= event_time
):
    activated.append((actor_id, "synthesis_deadline"))
    actor.scheduled_action = None  # consume the action
    continue
```

### 3. Prompt Builder — Synthesis Mode

When `activation_reason == "synthesis_deadline"`, inject deliverable instructions:

```python
if activation_reason == "synthesis_deadline":
    # Load preset schema from plan
    preset = plan.deliverable.get("preset", "synthesis") if plan.deliverable else "synthesis"
    from terrarium.deliverable_presets import load_preset
    preset_data = load_preset(preset)

    sections.append(f"""### SYNTHESIS DEADLINE REACHED
You MUST produce your final deliverable NOW.

{preset_data.get('prompt_instructions', '')}

Output your deliverable as JSON in the `deliverable_content` field of state_updates.
Schema: {json.dumps(preset_data.get('schema', {}), indent=2)}
""")
```

### 4. State Updates — Deliverable Detection (`agency/engine.py`)

In `_apply_state_updates()`:

```python
if "deliverable" in updates and updates["deliverable"]:
    self._deliverable_content = updates.get("deliverable_content", {})
    self._deliverable_produced = True
```

### 5. SimulationRunner — End on Deliverable

In the main loop end-condition check:

```python
agency = self._agency
if hasattr(agency, "_deliverable_produced") and agency._deliverable_produced:
    # Save deliverable artifact
    content = getattr(agency, "_deliverable_content", {})
    await self._artifact_store.save(run_id, "deliverable", content)
    return StopReason.DELIVERABLE_PRODUCED
```

### 6. Artifact Type

Add to `_ALLOWED_ARTIFACT_TYPES` in `runs/artifacts.py`:
```python
_ALLOWED_ARTIFACT_TYPES = frozenset({"report", "scorecard", "event_log", "config", "metadata", "deliverable"})
```

## What Does NOT Change
- Deliverable preset YAML files — already exist
- Lead actor selection logic — follows existing pattern
- ScheduledAction model — already exists on ActorState
- Normal collaboration flow — unchanged until deadline fires
- Mode 1 (agent testing) — no deliverable, no deadline, unaffected

## Verification
1. `uv run pytest tests/engines/agency/ -v` — tier1 check tests pass
2. Live test: run climate_research.yaml, verify deliverable produced at deadline
3. Dashboard: `GET /api/v1/runs/{id}/deliverable` returns structured output
4. Verify early convergence: if lead produces deliverable before deadline, simulation stops
