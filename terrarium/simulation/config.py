"""Configuration for the simulation runner and event queue."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SimulationRunnerConfig(BaseModel):
    """Config for SimulationRunner safety rails and limits."""

    model_config = ConfigDict(frozen=True)

    # ── End conditions ──────────────────────────────────────────
    # Maximum logical time before forced stop (seconds of simulated time).
    # For internal-only sims, time advances by tick_interval_seconds per event.
    max_logical_time: float = 86400.0

    # Hard cap on total committed events processed before forced stop.
    # Primary safety rail — keeps token spend bounded.
    max_total_events: int = 50

    # Stop when the event queue is empty AND no engine has scheduled future work.
    # If an actor has a scheduled_action, this condition is suppressed.
    stop_on_empty_queue: bool = True

    # ── Runaway loop protection ─────────────────────────────────
    # Max response envelopes accepted from agency/animator per single committed event.
    # Prevents one event from triggering an unbounded cascade.
    max_envelopes_per_event: int = 20

    # Max actions from one actor within a rolling tick_interval_seconds window.
    # Set high (100) to avoid restricting natural collaboration flow.
    max_actions_per_actor_per_window: int = 100

    # Max animator (environment) reactions within a rolling tick_interval_seconds window.
    max_environment_reactions_per_window: int = 10

    # For external/mixed sims: stop if this many consecutive events have no
    # external agent input. Skipped for internal-only sims.
    loop_breaker_threshold: int = 50

    # ── Timing ──────────────────────────────────────────────────
    # Logical time increment per tick. Used for:
    # - Runaway window duration (rolling window = tick_interval_seconds)
    # - Deliverable scheduling (deadline_tick * tick_interval_seconds)
    # - Internal-only sims: each committed event advances time by this amount
    tick_interval_seconds: float = 60.0

    # ── External agent slot binding (not yet enforced) ──────────
    max_external_agents: int = 10
    slot_claim_timeout_seconds: float = 300.0

    # ── Internal-only world end conditions ──────────────────────
    # Stop after N consecutive do_nothing/idle actions from actors.
    idle_stop_ticks: int = 5

    # Hard tick limit for internal-only worlds. Each committed event = 1 tick.
    max_ticks: int = 200
