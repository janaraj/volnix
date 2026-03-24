"""Action handlers for the payments service pack.

Each function handles one tool action, producing a ResponseProposal with
any state mutations expressed as StateDelta objects.

Handlers import ONLY from terrarium.core (types, context). They NEVER
import from persistence/, engines/, or bus/.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from terrarium.core.context import ResponseProposal
from terrarium.core.types import EntityId, StateDelta


def _new_id(prefix: str) -> str:
    """Generate a unique entity ID with the given prefix (e.g. 'cus', 'in')."""
    return f"{prefix}_{uuid.uuid4().hex}"


def _now_unix() -> int:
    """Return the current UTC time as a Unix timestamp (seconds)."""
    return int(time.time())


def _stripe_list(data: list[dict[str, Any]], has_more: bool = False) -> dict[str, Any]:
    """Build a Stripe-style list response envelope."""
    return {
        "object": "list",
        "data": data,
        "has_more": has_more,
    }


# ---------------------------------------------------------------------------
# list_payment_intents
# ---------------------------------------------------------------------------


async def handle_list_payment_intents(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``list_payment_intents`` action.

    Filters state["payment_intents"] by optional customer and status.
    Paginates via limit.  No state mutations.
    """
    intents: list[dict[str, Any]] = state.get("payment_intents", [])

    customer = input_data.get("customer")
    if customer:
        intents = [pi for pi in intents if pi.get("customer") == customer]

    status = input_data.get("status")
    if status:
        intents = [pi for pi in intents if pi.get("status") == status]

    limit = input_data.get("limit", 10)
    has_more = len(intents) > limit
    intents = intents[:limit]

    return ResponseProposal(
        response_body=_stripe_list(intents, has_more=has_more),
    )


# ---------------------------------------------------------------------------
# create_customer
# ---------------------------------------------------------------------------


async def handle_create_customer(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``create_customer`` action.

    Creates a new customer entity with a generated id and timestamp.
    """
    customer_id = _new_id("cus")
    now = _now_unix()

    customer_fields: dict[str, Any] = {
        "id": customer_id,
        "object": "customer",
        "name": input_data.get("name"),
        "email": input_data.get("email"),
        "phone": input_data.get("phone"),
        "description": input_data.get("description"),
        "metadata": input_data.get("metadata", {}),
        "balance": 0,
        "created": now,
    }

    delta = StateDelta(
        entity_type="customer",
        entity_id=EntityId(customer_id),
        operation="create",
        fields=customer_fields,
    )

    return ResponseProposal(
        response_body=customer_fields,
        proposed_state_deltas=[delta],
    )


# ---------------------------------------------------------------------------
# list_customers
# ---------------------------------------------------------------------------


async def handle_list_customers(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``list_customers`` action.

    Filters state["customers"] by optional email.  Paginates via limit.
    No state mutations.
    """
    customers: list[dict[str, Any]] = state.get("customers", [])

    email = input_data.get("email")
    if email:
        customers = [c for c in customers if c.get("email") == email]

    limit = input_data.get("limit", 10)
    has_more = len(customers) > limit
    customers = customers[:limit]

    return ResponseProposal(
        response_body=_stripe_list(customers, has_more=has_more),
    )


# ---------------------------------------------------------------------------
# create_refund
# ---------------------------------------------------------------------------


async def handle_create_refund(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``create_refund`` action.

    CRITICAL logic:
    1. Find the charge by id in state["charges"].
    2. If charge not found, return error.
    3. If charge is not paid, return error.
    4. Determine refund amount: input amount or charge.amount (full refund).
    5. If refund amount exceeds charge amount, return error.
    6. Create refund with status="pending".
    7. If full refund (amount == charge.amount), mark charge.refunded=true.
    8. Return TWO StateDelta objects (refund create + charge update).
    """
    charge_id = input_data["charge"]
    charges: list[dict[str, Any]] = state.get("charges", [])

    # Find the charge
    charge: dict[str, Any] | None = None
    for c in charges:
        if c.get("id") == charge_id:
            charge = c
            break

    if charge is None:
        return ResponseProposal(
            response_body={
                "error": {
                    "type": "invalid_request_error",
                    "message": f"No such charge: '{charge_id}'",
                    "param": "charge",
                },
            },
        )

    # Charge must be paid
    if not charge.get("paid", False):
        return ResponseProposal(
            response_body={
                "error": {
                    "type": "invalid_request_error",
                    "message": f"Charge '{charge_id}' has not been paid and cannot be refunded.",
                    "param": "charge",
                },
            },
        )

    charge_amount: int = charge.get("amount", 0)
    refund_amount: int = input_data.get("amount", charge_amount)

    # Refund amount must not exceed charge amount
    if refund_amount > charge_amount:
        return ResponseProposal(
            response_body={
                "error": {
                    "type": "invalid_request_error",
                    "message": (
                        f"Refund amount ({refund_amount}) is greater than "
                        f"charge amount ({charge_amount})."
                    ),
                    "param": "amount",
                },
            },
        )

    # Refund amount must be positive
    if refund_amount <= 0:
        return ResponseProposal(
            response_body={
                "error": {
                    "type": "invalid_request_error",
                    "message": "Refund amount must be a positive integer.",
                    "param": "amount",
                },
            },
        )

    refund_id = _new_id("re")
    now = _now_unix()
    is_full_refund = refund_amount == charge_amount

    refund_fields: dict[str, Any] = {
        "id": refund_id,
        "object": "refund",
        "amount": refund_amount,
        "charge": charge_id,
        "currency": charge.get("currency", "usd"),
        "status": "pending",
        "reason": input_data.get("reason"),
        "payment_intent": charge.get("payment_intent"),
        "created": now,
        "metadata": input_data.get("metadata", {}),
    }

    deltas: list[StateDelta] = []

    # Delta 1: create the refund
    deltas.append(
        StateDelta(
            entity_type="refund",
            entity_id=EntityId(refund_id),
            operation="create",
            fields=refund_fields,
        )
    )

    # Delta 2: update charge — mark as refunded if full refund
    if is_full_refund:
        deltas.append(
            StateDelta(
                entity_type="charge",
                entity_id=EntityId(charge_id),
                operation="update",
                fields={"refunded": True},
                previous_fields={"refunded": charge.get("refunded", False)},
            )
        )

    return ResponseProposal(
        response_body=refund_fields,
        proposed_state_deltas=deltas,
    )


# ---------------------------------------------------------------------------
# create_invoice
# ---------------------------------------------------------------------------


async def handle_create_invoice(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``create_invoice`` action.

    Creates a new invoice entity with status="draft".
    """
    invoice_id = _new_id("in")
    now = _now_unix()

    invoice_fields: dict[str, Any] = {
        "id": invoice_id,
        "object": "invoice",
        "customer": input_data["customer"],
        "description": input_data.get("description"),
        "status": "draft",
        "metadata": input_data.get("metadata", {}),
        "created": now,
    }

    delta = StateDelta(
        entity_type="invoice",
        entity_id=EntityId(invoice_id),
        operation="create",
        fields=invoice_fields,
    )

    return ResponseProposal(
        response_body=invoice_fields,
        proposed_state_deltas=[delta],
    )


# ---------------------------------------------------------------------------
# list_invoices
# ---------------------------------------------------------------------------


async def handle_list_invoices(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``list_invoices`` action.

    Filters state["invoices"] by optional customer and status.
    Paginates via limit.  No state mutations.
    """
    invoices: list[dict[str, Any]] = state.get("invoices", [])

    customer = input_data.get("customer")
    if customer:
        invoices = [inv for inv in invoices if inv.get("customer") == customer]

    status = input_data.get("status")
    if status:
        invoices = [inv for inv in invoices if inv.get("status") == status]

    limit = input_data.get("limit", 10)
    has_more = len(invoices) > limit
    invoices = invoices[:limit]

    return ResponseProposal(
        response_body=_stripe_list(invoices, has_more=has_more),
    )


# ---------------------------------------------------------------------------
# list_disputes
# ---------------------------------------------------------------------------


async def handle_list_disputes(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``list_disputes`` action.

    Returns state["disputes"] paginated via limit.  No state mutations.
    """
    disputes: list[dict[str, Any]] = state.get("disputes", [])

    limit = input_data.get("limit", 10)
    has_more = len(disputes) > limit
    disputes = disputes[:limit]

    return ResponseProposal(
        response_body=_stripe_list(disputes, has_more=has_more),
    )


# ---------------------------------------------------------------------------
# update_dispute
# ---------------------------------------------------------------------------


async def handle_update_dispute(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``update_dispute`` action.

    Finds the dispute by id, updates evidence and/or metadata.
    """
    dispute_id = input_data["id"]
    disputes: list[dict[str, Any]] = state.get("disputes", [])

    dispute: dict[str, Any] | None = None
    for d in disputes:
        if d.get("id") == dispute_id:
            dispute = d
            break

    if dispute is None:
        return ResponseProposal(
            response_body={
                "error": {
                    "type": "invalid_request_error",
                    "message": f"No such dispute: '{dispute_id}'",
                    "param": "id",
                },
            },
        )

    updated_fields: dict[str, Any] = {}
    previous_fields: dict[str, Any] = {}

    evidence = input_data.get("evidence")
    if evidence is not None:
        previous_fields["evidence"] = dispute.get("evidence")
        updated_fields["evidence"] = evidence

    metadata = input_data.get("metadata")
    if metadata is not None:
        previous_fields["metadata"] = dispute.get("metadata")
        updated_fields["metadata"] = metadata

    deltas: list[StateDelta] = []
    if updated_fields:
        deltas.append(
            StateDelta(
                entity_type="dispute",
                entity_id=EntityId(dispute_id),
                operation="update",
                fields=updated_fields,
                previous_fields=previous_fields,
            )
        )

    # Build response with merged dispute data
    response_dispute = {**dispute, **updated_fields}

    return ResponseProposal(
        response_body=response_dispute,
        proposed_state_deltas=deltas,
    )
