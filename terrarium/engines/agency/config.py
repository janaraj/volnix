"""Configuration for the AgencyEngine."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AgencyConfig(BaseModel):
    """Config for the AgencyEngine."""

    model_config = ConfigDict(frozen=True)

    # Tier classification thresholds
    frustration_threshold_tier3: float = 0.7
    high_stakes_roles: list[str] = Field(default_factory=list)

    # Batch settings
    batch_size: int = 5

    # Patience / frustration
    frustration_increase_per_patience: float = 0.1
    frustration_decrease_per_positive: float = 0.1
    default_patience: float = 300.0  # 5 minutes logical time

    # Actor state update
    max_recent_interactions: int = 20
    max_pending_notifications: int = 50

    # Concurrency
    max_concurrent_actor_calls: int = 20
    max_activations_per_event: int = 100
    max_envelopes_per_event: int = 50

    # LLM routing (router builds key as "{engine_name}_{use_case}")
    # Engine name is "agency", so "individual" → routing key "agency_individual"
    llm_use_case_individual: str = "individual"
    llm_use_case_batch: str = "batch"

    # Collaborative communication
    collaboration_mode: str = "tagged"  # "tagged" | "open"
    collaboration_enabled: bool = True
    batch_threshold_default: int = 3  # batch notifications before activation
    synthesis_buffer_pct: float = 0.1  # % of max_ticks reserved for synthesis
    idle_stop_ticks: int = 5  # stop if all actors do_nothing for N ticks
    auto_include_chat: bool = True  # auto-add chat service for internal actors
