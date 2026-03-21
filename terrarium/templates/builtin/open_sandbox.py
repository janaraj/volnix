"""Open Sandbox world template.

Creates a minimal, ungoverned world with all available service packs
enabled and no policies.  Useful for free-form exploration and
development.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.templates.base import BaseTemplate


class OpenSandboxTemplate(BaseTemplate):
    """Template for an open sandbox environment.

    Generates a world definition featuring:
    - All available service packs enabled
    - No governance policies (ungoverned mode)
    - A single agent actor with full permissions
    - Minimal seed data
    """

    template_id: ClassVar[str] = "open_sandbox"
    template_name: ClassVar[str] = "Open Sandbox"
    description: ClassVar[str] = (
        "A minimal ungoverned sandbox with all service packs and no policies."
    )

    async def generate(self, parameters: dict | None = None) -> dict:
        """Generate an open sandbox world definition.

        Args:
            parameters: Optional overrides (services, actor_count).

        Returns:
            World definition dictionary.
        """
        ...
