"""WorldContextBundle -- frozen runtime context reused by all Agency/Animator LLM calls.

Created ONCE at compile time. Contains everything the LLM needs to understand
the world: description, reality dimensions, behavior mode, governance rules,
available services + schemas.

This is NOT re-generated per actor. Per-actor context is added by ActorPromptBuilder.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorldContextBundle(BaseModel, frozen=True):
    """Canonical world prompt/context bundle.

    Created once during compilation. Reused by ActorPromptBuilder and
    Animator for all LLM calls. Contains the shared world system prompt.
    """

    world_description: str = ""
    reality_summary: str = ""
    reality_dimensions: dict[str, Any] = Field(default_factory=dict)
    behavior_mode: str = "dynamic"
    behavior_description: str = ""
    governance_rules_summary: str = ""
    available_services: list[dict[str, Any]] = Field(default_factory=list)
    mission: str = ""

    def to_system_prompt(self) -> str:
        """Render the world context as an LLM system prompt string."""
        sections = [
            f"## World\n{self.world_description}",
            f"## Reality\n{self.reality_summary}",
        ]
        if self.reality_dimensions:
            dim_lines = []
            for dim_name, dim_data in self.reality_dimensions.items():
                if isinstance(dim_data, dict):
                    attrs = ", ".join(
                        f"{k}={v}" for k, v in dim_data.get("attributes", {}).items()
                    )
                    dim_lines.append(
                        f"- {dim_name}: {dim_data.get('level', '')} ({attrs})"
                    )
                else:
                    dim_lines.append(f"- {dim_name}: {dim_data}")
            sections.append("## Reality Dimensions\n" + "\n".join(dim_lines))
        sections.append(
            f"## Behavior Mode\n{self.behavior_mode}: {self.behavior_description}"
        )
        if self.governance_rules_summary:
            sections.append(f"## Governance Rules\n{self.governance_rules_summary}")
        if self.mission:
            sections.append(f"## Mission\n{self.mission}")
        if self.available_services:
            svc_lines = []
            for svc in self.available_services:
                name = svc.get("name", "unknown")
                actions = svc.get("actions", [])
                svc_lines.append(f"- {name}: {', '.join(a.get('name', '?') for a in actions)}")
            sections.append("## Available Services\n" + "\n".join(svc_lines))
        return "\n\n".join(sections)
