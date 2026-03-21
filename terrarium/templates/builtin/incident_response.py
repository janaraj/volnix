"""Incident Response world template.

Creates an on-call / incident-response world with monitoring, alerting,
communication, and code-deployment services for evaluating how agents
handle production incidents.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.templates.base import BaseTemplate


class IncidentResponseTemplate(BaseTemplate):
    """Template for an incident response environment.

    Generates a world definition featuring:
    - Monitoring and alerting services
    - Chat communication for war-room coordination
    - Code/DevOps services for hotfix deployment
    - Configurable severity levels and escalation chains
    """

    template_id: ClassVar[str] = "incident_response"
    template_name: ClassVar[str] = "Incident Response"
    description: ClassVar[str] = (
        "An on-call incident response world with monitoring, chat, "
        "and code deployment services."
    )

    async def generate(self, parameters: dict | None = None) -> dict:
        """Generate an incident response world definition.

        Args:
            parameters: Optional overrides (team_size, severity,
                alert_count, services).

        Returns:
            World definition dictionary.
        """
        ...
