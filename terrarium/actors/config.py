"""Configuration models for the actor system.

:class:`ActorConfig` holds generator settings including style weights and
the friction behavior vocabulary used by :class:`SimpleActorGenerator`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SlotManagerConfig(BaseModel, frozen=True):
    """Configuration for external agent slot management."""

    # Max external agents that can be connected simultaneously.
    max_external_agents: int = 10
    # Allow tool calls without registration (backward compat).
    # When True, unknown actors are auto-registered with default permissions.
    allow_unregistered_access: bool = True
    # Auto-assign agents to available slots when no actor_id specified.
    auto_assign_enabled: bool = True
    # Default permissions for auto-registered agents (no profile provided).
    default_permissions: dict[str, Any] = Field(
        default_factory=lambda: {"read": "all", "write": "all"}
    )
    # Default budget for auto-registered agents. None = no limit.
    default_budget: dict[str, Any] | None = None
    # Token prefix for generated agent tokens.
    token_prefix: str = "terr_"


class ActorConfig(BaseModel, frozen=True):
    """Top-level actor configuration section."""

    default_agent_budget: dict[str, Any] = Field(default_factory=dict)
    default_human_response_time: str = "5m"
    generator_seed: int = 42

    style_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "balanced": 0.3,
            "cautious": 0.2,
            "aggressive": 0.15,
            "methodical": 0.2,
            "creative": 0.15,
        }
    )

    friction_behaviors: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "uncooperative": [
                "vague_requests",
                "changes_mind",
                "slow_to_respond",
                "ignores_instructions",
                "provides_incomplete_info",
            ],
            "deceptive": [
                "looks_legitimate",
                "provides_fake_evidence",
                "social_engineering",
                "identity_spoofing",
                "trust_building",
            ],
            "hostile": [
                "explicit_threats",
                "system_exploitation",
                "denial_of_service",
                "data_exfiltration",
                "privilege_escalation",
            ],
        }
    )
