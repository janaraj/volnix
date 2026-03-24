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
    handle_cancel_payment_intent,
    handle_close_dispute,
    handle_confirm_payment_intent,
    handle_create_customer,
    handle_create_invoice,
    handle_create_payment_intent,
    handle_create_refund,
    handle_finalize_invoice,
    handle_get_charge,
    handle_get_customer,
    handle_get_dispute,
    handle_get_invoice,
    handle_get_payment_intent,
    handle_get_refund,
    handle_list_customers,
    handle_list_disputes,
    handle_list_invoices,
    handle_list_payment_intents,
    handle_list_refunds,
    handle_update_customer,
    handle_update_dispute,
)
from terrarium.packs.verified.payments.schemas import (
    CHARGE_ENTITY_SCHEMA,
    CUSTOMER_ENTITY_SCHEMA,
    DISPUTE_ENTITY_SCHEMA,
    INVOICE_ENTITY_SCHEMA,
    PAYMENT_INTENT_ENTITY_SCHEMA,
    PAYMENTS_TOOL_DEFINITIONS,
    REFUND_ENTITY_SCHEMA,
)
from terrarium.packs.verified.payments.state_machines import (
    DISPUTE_TRANSITIONS,
    INVOICE_TRANSITIONS,
    PAYMENT_INTENT_TRANSITIONS,
    REFUND_TRANSITIONS,
)


class PaymentsPack(ServicePack):
    """Verified pack for payment / money services.

    Tools (21): create_payment_intent, get_payment_intent,
    confirm_payment_intent, cancel_payment_intent, list_payment_intents,
    create_customer, get_customer, update_customer, list_customers,
    get_charge, create_refund, get_refund, list_refunds,
    create_invoice, get_invoice, finalize_invoice, list_invoices,
    get_dispute, close_dispute, list_disputes, update_dispute.
    """

    pack_name: ClassVar[str] = "payments"
    category: ClassVar[str] = "money"
    fidelity_tier: ClassVar[int] = 1

    _handlers: ClassVar[dict[str, ActionHandler]] = {
        "create_payment_intent": handle_create_payment_intent,
        "get_payment_intent": handle_get_payment_intent,
        "confirm_payment_intent": handle_confirm_payment_intent,
        "cancel_payment_intent": handle_cancel_payment_intent,
        "list_payment_intents": handle_list_payment_intents,
        "create_customer": handle_create_customer,
        "get_customer": handle_get_customer,
        "update_customer": handle_update_customer,
        "list_customers": handle_list_customers,
        "get_charge": handle_get_charge,
        "create_refund": handle_create_refund,
        "get_refund": handle_get_refund,
        "list_refunds": handle_list_refunds,
        "create_invoice": handle_create_invoice,
        "get_invoice": handle_get_invoice,
        "finalize_invoice": handle_finalize_invoice,
        "list_invoices": handle_list_invoices,
        "get_dispute": handle_get_dispute,
        "close_dispute": handle_close_dispute,
        "list_disputes": handle_list_disputes,
        "update_dispute": handle_update_dispute,
    }

    def get_tools(self) -> list[dict]:
        """Return the payments tool manifest."""
        return list(PAYMENTS_TOOL_DEFINITIONS)

    def get_entity_schemas(self) -> dict:
        """Return entity schemas for all 6 entity types."""
        return {
            "payment_intent": PAYMENT_INTENT_ENTITY_SCHEMA,
            "charge": CHARGE_ENTITY_SCHEMA,
            "customer": CUSTOMER_ENTITY_SCHEMA,
            "refund": REFUND_ENTITY_SCHEMA,
            "invoice": INVOICE_ENTITY_SCHEMA,
            "dispute": DISPUTE_ENTITY_SCHEMA,
        }

    def get_state_machines(self) -> dict:
        """Return state machines for payment entities."""
        return {
            "payment_intent": {"transitions": PAYMENT_INTENT_TRANSITIONS},
            "refund": {"transitions": REFUND_TRANSITIONS},
            "invoice": {"transitions": INVOICE_TRANSITIONS},
            "dispute": {"transitions": DISPUTE_TRANSITIONS},
        }

    async def handle_action(
        self,
        action: ToolName,
        input_data: dict,
        state: dict,
    ) -> ResponseProposal:
        """Dispatch to the appropriate payments action handler."""
        return await self.dispatch_action(action, input_data, state)
