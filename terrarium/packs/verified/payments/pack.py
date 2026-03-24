"""Payments service pack (Tier 1 -- verified).

Provides the canonical tool surface for money-category services:
payment intents, customers, charges, refunds, invoices, and disputes.
Aligned with Stripe's API and the official @stripe/mcp tool surface.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.base import ActionHandler, ServicePack
from terrarium.packs.verified.payments.handlers import (
    handle_create_customer,
    handle_create_invoice,
    handle_create_refund,
    handle_list_customers,
    handle_list_disputes,
    handle_list_invoices,
    handle_list_payment_intents,
    handle_update_dispute,
)
from terrarium.packs.verified.payments.schemas import (
    CHARGE_ENTITY_SCHEMA,
    CUSTOMER_ENTITY_SCHEMA,
    PAYMENT_INTENT_ENTITY_SCHEMA,
    PAYMENTS_TOOL_DEFINITIONS,
    REFUND_ENTITY_SCHEMA,
)
from terrarium.packs.verified.payments.state_machines import (
    PAYMENT_INTENT_TRANSITIONS,
    REFUND_TRANSITIONS,
)


class PaymentsPack(ServicePack):
    """Verified pack for payment / money services.

    Tools: list_payment_intents, create_customer, list_customers,
    create_refund, list_invoices, create_invoice, list_disputes,
    update_dispute.
    """

    pack_name: ClassVar[str] = "payments"
    category: ClassVar[str] = "money"
    fidelity_tier: ClassVar[int] = 1

    _handlers: ClassVar[dict[str, ActionHandler]] = {
        "list_payment_intents": handle_list_payment_intents,
        "create_customer": handle_create_customer,
        "list_customers": handle_list_customers,
        "create_refund": handle_create_refund,
        "list_invoices": handle_list_invoices,
        "create_invoice": handle_create_invoice,
        "list_disputes": handle_list_disputes,
        "update_dispute": handle_update_dispute,
    }

    def get_tools(self) -> list[dict]:
        """Return the payments tool manifest."""
        return list(PAYMENTS_TOOL_DEFINITIONS)

    def get_entity_schemas(self) -> dict:
        """Return entity schemas (payment_intent, charge, customer, refund)."""
        return {
            "payment_intent": PAYMENT_INTENT_ENTITY_SCHEMA,
            "charge": CHARGE_ENTITY_SCHEMA,
            "customer": CUSTOMER_ENTITY_SCHEMA,
            "refund": REFUND_ENTITY_SCHEMA,
        }

    def get_state_machines(self) -> dict:
        """Return state machines for payment entities."""
        return {
            "payment_intent": {"transitions": PAYMENT_INTENT_TRANSITIONS},
            "refund": {"transitions": REFUND_TRANSITIONS},
        }

    async def handle_action(
        self,
        action: ToolName,
        input_data: dict,
        state: dict,
    ) -> ResponseProposal:
        """Dispatch to the appropriate payments action handler."""
        return await self.dispatch_action(action, input_data, state)
