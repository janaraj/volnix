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


def _stripe_list(
    data: list[dict[str, Any]],
    url: str,
    has_more: bool = False,
) -> dict[str, Any]:
    """Build a Stripe-style list response envelope."""
    return {
        "object": "list",
        "data": data,
        "has_more": has_more,
        "url": url,
    }


def _stripe_error(
    message: str,
    param: str | None = None,
    error_type: str = "invalid_request_error",
) -> dict[str, Any]:
    """Build a standardised Stripe error response."""
    err: dict[str, Any] = {
        "type": error_type,
        "message": message,
    }
    if param is not None:
        err["param"] = param
    return {"error": err}


def _find_entity(
    entities: list[dict[str, Any]],
    entity_id: str,
) -> dict[str, Any] | None:
    """Find an entity by id in a list."""
    for e in entities:
        if e.get("id") == entity_id:
            return e
    return None


# ---------------------------------------------------------------------------
# create_payment_intent
# ---------------------------------------------------------------------------


async def handle_create_payment_intent(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``create_payment_intent`` action.

    Creates a payment intent with status="requires_payment_method".
    """
    amount: int = input_data["amount"]
    currency: str = input_data["currency"]

    if amount < 0:
        return ResponseProposal(
            response_body=_stripe_error("Invalid positive integer", param="amount"),
        )

    pi_id = _new_id("pi")
    now = _now_unix()
    client_secret = f"{pi_id}_secret_{uuid.uuid4().hex[:16]}"

    pi_fields: dict[str, Any] = {
        "id": pi_id,
        "object": "payment_intent",
        "amount": amount,
        "currency": currency.lower(),
        "status": "requires_payment_method",
        "customer": input_data.get("customer"),
        "payment_method": input_data.get("payment_method"),
        "description": input_data.get("description"),
        "receipt_email": input_data.get("receipt_email"),
        "confirmation_method": input_data.get("confirmation_method", "automatic"),
        "capture_method": input_data.get("capture_method", "automatic"),
        "client_secret": client_secret,
        "livemode": False,
        "next_action": None,
        "last_payment_error": None,
        "shipping": None,
        "metadata": input_data.get("metadata", {}),
        "amount_capturable": 0,
        "amount_received": 0,
        "canceled_at": None,
        "cancellation_reason": None,
        "created": now,
    }

    delta = StateDelta(
        entity_type="payment_intent",
        entity_id=EntityId(pi_id),
        operation="create",
        fields=pi_fields,
    )

    return ResponseProposal(
        response_body=pi_fields,
        proposed_state_deltas=[delta],
    )


# ---------------------------------------------------------------------------
# get_payment_intent
# ---------------------------------------------------------------------------


async def handle_get_payment_intent(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``get_payment_intent`` action.

    Retrieves a single payment intent by ID.
    """
    pi_id = input_data["id"]
    intents: list[dict[str, Any]] = state.get("payment_intents", [])
    pi = _find_entity(intents, pi_id)

    if pi is None:
        return ResponseProposal(
            response_body=_stripe_error(f"No such payment_intent: '{pi_id}'", param="id"),
        )

    body = {**pi}
    body.setdefault("object", "payment_intent")
    return ResponseProposal(response_body=body)


# ---------------------------------------------------------------------------
# confirm_payment_intent
# ---------------------------------------------------------------------------


async def handle_confirm_payment_intent(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``confirm_payment_intent`` action.

    Transitions a payment intent to "processing" then "succeeded".
    Creates a Charge entity automatically.
    Only valid from requires_payment_method or requires_confirmation.
    """
    pi_id = input_data["id"]
    intents: list[dict[str, Any]] = state.get("payment_intents", [])
    pi = _find_entity(intents, pi_id)

    if pi is None:
        return ResponseProposal(
            response_body=_stripe_error(f"No such payment_intent: '{pi_id}'", param="id"),
        )

    confirmable_statuses = {
        "requires_payment_method",
        "requires_confirmation",
    }
    current_status = pi.get("status", "")
    if current_status not in confirmable_statuses:
        return ResponseProposal(
            response_body=_stripe_error(
                f"PaymentIntent has status '{current_status}' and cannot be confirmed. "
                f"Only intents with status in {sorted(confirmable_statuses)} can be confirmed.",
                param="id",
            ),
        )

    now = _now_unix()
    charge_id = _new_id("ch")

    # Build charge entity
    charge_fields: dict[str, Any] = {
        "id": charge_id,
        "object": "charge",
        "amount": pi.get("amount", 0),
        "currency": pi.get("currency", "usd"),
        "customer": pi.get("customer"),
        "payment_intent": pi_id,
        "paid": True,
        "captured": True,
        "refunded": False,
        "disputed": False,
        "failure_code": None,
        "failure_message": None,
        "receipt_email": pi.get("receipt_email"),
        "receipt_number": None,
        "statement_descriptor": None,
        "balance_transaction": f"txn_{uuid.uuid4().hex[:24]}",
        "livemode": False,
        "outcome": {
            "network_status": "approved_by_network",
            "reason": None,
            "risk_level": "normal",
            "risk_score": 32,
            "seller_message": "Payment complete.",
            "type": "authorized",
        },
        "created": now,
    }

    # Updated payment intent fields
    updated_pi_fields: dict[str, Any] = {
        "status": "succeeded",
        "amount_received": pi.get("amount", 0),
    }

    deltas: list[StateDelta] = [
        # Delta 1: update payment intent to succeeded
        StateDelta(
            entity_type="payment_intent",
            entity_id=EntityId(pi_id),
            operation="update",
            fields=updated_pi_fields,
            previous_fields={
                "status": current_status,
                "amount_received": pi.get("amount_received", 0),
            },
        ),
        # Delta 2: create charge
        StateDelta(
            entity_type="charge",
            entity_id=EntityId(charge_id),
            operation="create",
            fields=charge_fields,
        ),
    ]

    # Build response body: merged PI
    response_pi = {**pi, **updated_pi_fields}
    response_pi.setdefault("object", "payment_intent")

    return ResponseProposal(
        response_body=response_pi,
        proposed_state_deltas=deltas,
    )


# ---------------------------------------------------------------------------
# cancel_payment_intent
# ---------------------------------------------------------------------------


async def handle_cancel_payment_intent(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``cancel_payment_intent`` action.

    Transitions a payment intent to "canceled".
    """
    pi_id = input_data["id"]
    intents: list[dict[str, Any]] = state.get("payment_intents", [])
    pi = _find_entity(intents, pi_id)

    if pi is None:
        return ResponseProposal(
            response_body=_stripe_error(f"No such payment_intent: '{pi_id}'", param="id"),
        )

    terminal_statuses = {"succeeded", "canceled"}
    current_status = pi.get("status", "")
    if current_status in terminal_statuses:
        return ResponseProposal(
            response_body=_stripe_error(
                f"PaymentIntent has status '{current_status}' and cannot be canceled.",
                param="id",
            ),
        )

    now = _now_unix()
    updated_fields: dict[str, Any] = {
        "status": "canceled",
        "canceled_at": now,
        "cancellation_reason": input_data.get("cancellation_reason"),
    }

    delta = StateDelta(
        entity_type="payment_intent",
        entity_id=EntityId(pi_id),
        operation="update",
        fields=updated_fields,
        previous_fields={
            "status": current_status,
            "canceled_at": pi.get("canceled_at"),
            "cancellation_reason": pi.get("cancellation_reason"),
        },
    )

    response_pi = {**pi, **updated_fields}
    response_pi.setdefault("object", "payment_intent")

    return ResponseProposal(
        response_body=response_pi,
        proposed_state_deltas=[delta],
    )


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
        response_body=_stripe_list(intents, url="/v1/payment_intents", has_more=has_more),
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
        "livemode": False,
        "delinquent": False,
        "invoice_settings": {"default_payment_method": None},
        "default_source": None,
        "invoice_prefix": customer_id[:8].upper(),
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
# get_customer
# ---------------------------------------------------------------------------


async def handle_get_customer(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``get_customer`` action.

    Retrieves a single customer by ID.
    """
    cus_id = input_data["id"]
    customers: list[dict[str, Any]] = state.get("customers", [])
    customer = _find_entity(customers, cus_id)

    if customer is None:
        return ResponseProposal(
            response_body=_stripe_error(f"No such customer: '{cus_id}'", param="id"),
        )

    body = {**customer}
    body.setdefault("object", "customer")
    return ResponseProposal(response_body=body)


# ---------------------------------------------------------------------------
# update_customer
# ---------------------------------------------------------------------------


async def handle_update_customer(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``update_customer`` action.

    Updates mutable customer fields (name, email, phone, description, metadata).
    """
    cus_id = input_data["id"]
    customers: list[dict[str, Any]] = state.get("customers", [])
    customer = _find_entity(customers, cus_id)

    if customer is None:
        return ResponseProposal(
            response_body=_stripe_error(f"No such customer: '{cus_id}'", param="id"),
        )

    updatable = ("name", "email", "phone", "description", "metadata")
    updated_fields: dict[str, Any] = {}
    previous_fields: dict[str, Any] = {}

    for field in updatable:
        if field in input_data:
            previous_fields[field] = customer.get(field)
            updated_fields[field] = input_data[field]

    deltas: list[StateDelta] = []
    if updated_fields:
        deltas.append(
            StateDelta(
                entity_type="customer",
                entity_id=EntityId(cus_id),
                operation="update",
                fields=updated_fields,
                previous_fields=previous_fields,
            )
        )

    response_customer = {**customer, **updated_fields}
    response_customer.setdefault("object", "customer")

    return ResponseProposal(
        response_body=response_customer,
        proposed_state_deltas=deltas,
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
        response_body=_stripe_list(customers, url="/v1/customers", has_more=has_more),
    )


# ---------------------------------------------------------------------------
# get_charge
# ---------------------------------------------------------------------------


async def handle_get_charge(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``get_charge`` action.

    Retrieves a single charge by ID.
    """
    charge_id = input_data["id"]
    charges: list[dict[str, Any]] = state.get("charges", [])
    charge = _find_entity(charges, charge_id)

    if charge is None:
        return ResponseProposal(
            response_body=_stripe_error(f"No such charge: '{charge_id}'", param="id"),
        )

    body = {**charge}
    body.setdefault("object", "charge")
    return ResponseProposal(response_body=body)


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

    charge = _find_entity(charges, charge_id)

    if charge is None:
        return ResponseProposal(
            response_body=_stripe_error(f"No such charge: '{charge_id}'", param="charge"),
        )

    # Charge must be paid
    if not charge.get("paid", False):
        return ResponseProposal(
            response_body=_stripe_error(
                f"Charge '{charge_id}' has not been paid and cannot be refunded.",
                param="charge",
            ),
        )

    charge_amount: int = charge.get("amount", 0)
    refund_amount: int = input_data.get("amount", charge_amount)

    # Refund amount must not exceed charge amount
    if refund_amount > charge_amount:
        return ResponseProposal(
            response_body=_stripe_error(
                f"Refund amount ({refund_amount}) is greater than charge amount ({charge_amount}).",
                param="amount",
            ),
        )

    # Refund amount must be positive
    if refund_amount <= 0:
        return ResponseProposal(
            response_body=_stripe_error(
                "Refund amount must be a positive integer.",
                param="amount",
            ),
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
        "balance_transaction": None,
        "receipt_number": None,
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

    # Delta 2: update charge -- mark as refunded if full refund
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
# get_refund
# ---------------------------------------------------------------------------


async def handle_get_refund(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``get_refund`` action.

    Retrieves a single refund by ID.
    """
    refund_id = input_data["id"]
    refunds: list[dict[str, Any]] = state.get("refunds", [])
    refund = _find_entity(refunds, refund_id)

    if refund is None:
        return ResponseProposal(
            response_body=_stripe_error(f"No such refund: '{refund_id}'", param="id"),
        )

    body = {**refund}
    body.setdefault("object", "refund")
    return ResponseProposal(response_body=body)


# ---------------------------------------------------------------------------
# list_refunds
# ---------------------------------------------------------------------------


async def handle_list_refunds(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``list_refunds`` action.

    Lists refunds, optionally filtered by charge. Paginates via limit.
    """
    refunds: list[dict[str, Any]] = state.get("refunds", [])

    charge = input_data.get("charge")
    if charge:
        refunds = [r for r in refunds if r.get("charge") == charge]

    limit = input_data.get("limit", 10)
    has_more = len(refunds) > limit
    refunds = refunds[:limit]

    return ResponseProposal(
        response_body=_stripe_list(refunds, url="/v1/refunds", has_more=has_more),
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
    invoice_number = f"INV-{uuid.uuid4().hex[:8].upper()}"

    invoice_fields: dict[str, Any] = {
        "id": invoice_id,
        "object": "invoice",
        "customer": input_data["customer"],
        "description": input_data.get("description"),
        "status": "draft",
        "amount_due": 0,
        "amount_paid": 0,
        "amount_remaining": 0,
        "currency": input_data.get("currency", "usd"),
        "due_date": None,
        "livemode": False,
        "number": invoice_number,
        "lines": {
            "object": "list",
            "data": [],
            "has_more": False,
            "url": f"/v1/invoices/{invoice_id}/lines",
        },
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
# get_invoice
# ---------------------------------------------------------------------------


async def handle_get_invoice(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``get_invoice`` action.

    Retrieves a single invoice by ID.
    """
    inv_id = input_data["id"]
    invoices: list[dict[str, Any]] = state.get("invoices", [])
    invoice = _find_entity(invoices, inv_id)

    if invoice is None:
        return ResponseProposal(
            response_body=_stripe_error(f"No such invoice: '{inv_id}'", param="id"),
        )

    body = {**invoice}
    body.setdefault("object", "invoice")
    return ResponseProposal(response_body=body)


# ---------------------------------------------------------------------------
# finalize_invoice
# ---------------------------------------------------------------------------


async def handle_finalize_invoice(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``finalize_invoice`` action.

    Transitions a draft invoice to open.
    """
    inv_id = input_data["id"]
    invoices: list[dict[str, Any]] = state.get("invoices", [])
    invoice = _find_entity(invoices, inv_id)

    if invoice is None:
        return ResponseProposal(
            response_body=_stripe_error(f"No such invoice: '{inv_id}'", param="id"),
        )

    current_status = invoice.get("status", "")
    if current_status != "draft":
        return ResponseProposal(
            response_body=_stripe_error(
                f"Invoice has status '{current_status}' and cannot be finalized. "
                "Only draft invoices can be finalized.",
                param="id",
            ),
        )

    updated_fields: dict[str, Any] = {"status": "open"}

    delta = StateDelta(
        entity_type="invoice",
        entity_id=EntityId(inv_id),
        operation="update",
        fields=updated_fields,
        previous_fields={"status": "draft"},
    )

    response_invoice = {**invoice, **updated_fields}
    response_invoice.setdefault("object", "invoice")

    return ResponseProposal(
        response_body=response_invoice,
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
        response_body=_stripe_list(invoices, url="/v1/invoices", has_more=has_more),
    )


# ---------------------------------------------------------------------------
# get_dispute
# ---------------------------------------------------------------------------


async def handle_get_dispute(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``get_dispute`` action.

    Retrieves a single dispute by ID.
    """
    dispute_id = input_data["id"]
    disputes: list[dict[str, Any]] = state.get("disputes", [])
    dispute = _find_entity(disputes, dispute_id)

    if dispute is None:
        return ResponseProposal(
            response_body=_stripe_error(f"No such dispute: '{dispute_id}'", param="id"),
        )

    body = {**dispute}
    body.setdefault("object", "dispute")
    return ResponseProposal(response_body=body)


# ---------------------------------------------------------------------------
# close_dispute
# ---------------------------------------------------------------------------


async def handle_close_dispute(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``close_dispute`` action.

    Accepts the dispute by transitioning its status to "lost".
    Closing a dispute means the merchant accepts the chargeback.
    """
    dispute_id = input_data["id"]
    disputes: list[dict[str, Any]] = state.get("disputes", [])
    dispute = _find_entity(disputes, dispute_id)

    if dispute is None:
        return ResponseProposal(
            response_body=_stripe_error(f"No such dispute: '{dispute_id}'", param="id"),
        )

    terminal = {"won", "lost", "charge_refunded", "warning_closed"}
    current_status = dispute.get("status", "")
    if current_status in terminal:
        return ResponseProposal(
            response_body=_stripe_error(
                f"Dispute has status '{current_status}' and cannot be closed.",
                param="id",
            ),
        )

    updated_fields: dict[str, Any] = {"status": "lost"}

    delta = StateDelta(
        entity_type="dispute",
        entity_id=EntityId(dispute_id),
        operation="update",
        fields=updated_fields,
        previous_fields={"status": current_status},
    )

    response_dispute = {**dispute, **updated_fields}
    response_dispute.setdefault("object", "dispute")

    return ResponseProposal(
        response_body=response_dispute,
        proposed_state_deltas=[delta],
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
        response_body=_stripe_list(disputes, url="/v1/disputes", has_more=has_more),
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

    dispute = _find_entity(disputes, dispute_id)

    if dispute is None:
        return ResponseProposal(
            response_body=_stripe_error(f"No such dispute: '{dispute_id}'", param="id"),
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
    response_dispute.setdefault("object", "dispute")

    return ResponseProposal(
        response_body=response_dispute,
        proposed_state_deltas=deltas,
    )
