"""Configuration for the simulation runner and event queue."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SimulationRunnerConfig(BaseModel):
    """Config for SimulationRunner safety rails and limits."""

    model_config = ConfigDict(frozen=True)

    # End conditions
    max_logical_time: float = 86400.0  # 24h of simulated time
    max_total_events: int = 10000  # hard cap on total events processed
    stop_on_empty_queue: bool = True  # stop when queue + scheduled are empty

    # Runaway loop protection
    max_envelopes_per_event: int = 20  # max envelopes from one committed event
    max_actions_per_actor_per_window: int = 5  # max actions from one actor in a 60s window
    max_environment_reactions_per_window: int = 10  # max animator reactions in a 60s window
    loop_breaker_threshold: int = 50  # consecutive events without external input

    # Tick interval (how often to check scheduled events)
    tick_interval_seconds: float = 60.0

    # Agent slot binding
    max_external_agents: int = 10
    slot_claim_timeout_seconds: float = 300.0

    # Internal-only world end conditions
    idle_stop_ticks: int = 5  # stop if all actors do_nothing for N consecutive ticks
    max_ticks: int = 200  # hard tick limit for internal-only worlds
