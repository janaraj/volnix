"""WorldContextBundle -- frozen runtime context reused by all Agency/Animator LLM calls.

Created ONCE at compile time. Contains everything the LLM needs to understand
the world: description, reality, seeds, mission, and available services grouped
by read/write capability.

This is NOT re-generated per actor. Per-actor context is added by ActorPromptBuilder.
"""

from __future__ import annotations

from collections import defaultdict
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
    seeds: list[str] = Field(default_factory=list)

    def to_system_prompt(self) -> str:
        """Render the world context as an LLM system prompt string.

        Structure:
        1. World description
        2. Mission
        3. Reality summary
        4. Seeds (what scenarios/data exist in the world)
        5. Services grouped by service name, split into READ/WRITE tools
        """
        sections = [f"## World\n{self.world_description}"]

        if self.mission:
            sections.append(f"## Mission\n{self.mission}")

        if self.reality_summary:
            sections.append(f"## Reality\n{self.reality_summary}")

        if self.seeds:
            seed_lines = [
                "## World Scenarios",
                "These scenarios exist in this world's data. "
                "Query services to find the actual records.",
            ]
            for seed in self.seeds:
                seed_lines.append(f"- {seed}")
            sections.append("\n".join(seed_lines))

        if self.available_services:
            sections.append(self._render_services())

        return "\n\n".join(sections)

    def _render_services(self) -> str:
        """Group tools by service name, split into READ and WRITE.

        Each tool is shown with exact action_type and target_service
        so the LLM knows exactly what to put in the JSON response.
        """
        by_service: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for tool in self.available_services:
            service = tool.get("service", "unknown")
            by_service[service].append(tool)

        lines = [
            "## Available Tools",
            "Use the EXACT `action_type` and `target_service` values shown below.",
        ]
        for service_name in sorted(by_service):
            tools = by_service[service_name]
            read_tools = []
            write_tools = []
            for t in tools:
                method = t.get("http_method", "POST").upper()
                name = t.get("name", "?")
                desc = t.get("description", "")
                params = t.get("required_params", [])
                params_str = f" — params: {', '.join(params)}" if params else ""
                entry = f"  - action_type: \"{name}\", target_service: \"{service_name}\"{params_str}"
                if desc:
                    entry += f"  ({desc})"
                if method == "GET":
                    read_tools.append(entry)
                else:
                    write_tools.append(entry)

            lines.append(f"\n### {service_name}")
            if read_tools:
                lines.append("READ (query data):")
                lines.extend(read_tools)
            if write_tools:
                lines.append("WRITE (create/modify):")
                lines.extend(write_tools)

        return "\n".join(lines)
