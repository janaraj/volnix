"""Configuration model for the world animator engine.

Supports all YAML settings from the compiler animator section:
  creativity, event_frequency, contextual_targeting, escalation_on_inaction,
  creativity_budget_per_tick, tick_interval_seconds, scheduled_events.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AnimatorConfig(BaseModel):
    """Configuration for the world animator engine.

    Parsed from the YAML ``compiler.animator`` section and from
    WorldPlan.animator_settings at runtime.
    """

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    creativity: Literal["low", "medium", "high"] = "medium"
    event_frequency: Literal["rare", "moderate", "frequent"] = "moderate"
    contextual_targeting: bool = True
    escalation_on_inaction: bool = True
    creativity_budget_per_tick: int = 3
    tick_interval_seconds: float = 60.0
    scheduled_events: list[dict[str, Any]] = Field(default_factory=list)
