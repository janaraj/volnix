"""Payments service pack (Tier 1 -- verified).

Provides the canonical tool surface for money-transactions services:
charges list/get, refund create/list, and dispute list.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.base import ServicePack


class PaymentsPack(ServicePack):
    """Verified pack for payment / money-transaction services.

    Tools: charges_list, charges_get, refund_create, refund_list,
    dispute_list.
    """

    pack_name: ClassVar[str] = "payments"
    category: ClassVar[str] = "money_transactions"
    fidelity_tier: ClassVar[int] = 1

    def get_tools(self) -> list[dict]:
        """Return the payments tool manifest."""
        ...

    def get_entity_schemas(self) -> dict:
        """Return entity schemas (charge, refund, dispute, balance)."""
        ...

    def get_state_machines(self) -> dict:
        """Return state machines for payment entities."""
        ...

    async def handle_action(
        self,
        action: ToolName,
        input_data: dict,
        state: dict,
    ) -> ResponseProposal:
        """Dispatch to the appropriate payments action handler."""
        ...
