"""Customer Support world template.

Creates a support team world with email, chat, ticket tracking, and
payment processing services.  Configurable parameters include agent
count, customer count, initial ticket count, and governance policies.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.templates.base import BaseTemplate


class CustomerSupportTemplate(BaseTemplate):
    """Template for a customer support team environment.

    Generates a world definition featuring:
    - Email and chat communication services
    - A ticket tracking work-management service
    - A payment/refund processing service
    - Configurable agent and customer actors
    - Governance policies for refund thresholds and escalation
    """

    template_id: ClassVar[str] = "customer_support"
    template_name: ClassVar[str] = "Customer Support"
    description: ClassVar[str] = (
        "A support team world with email, chat, tickets, and payments. "
        "Configurable: agent_count, customer_count, ticket_count, policies."
    )

    async def generate(self, parameters: dict | None = None) -> dict:
        """Generate a customer support world definition.

        Args:
            parameters: Optional overrides (agent_count, customer_count,
                ticket_count, policies).

        Returns:
            World definition dictionary.
        """
        ...
