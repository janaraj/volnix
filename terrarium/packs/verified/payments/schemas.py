"""Entity schemas and tool definitions for the payments service pack.

Pure data -- no logic, no imports beyond stdlib.  Aligned with Stripe's
API object shapes and the official @stripe/mcp tool surface.
"""

from __future__ import annotations

from terrarium.packs.verified.payments.state_machines import (
    PAYMENT_INTENT_STATES,
    REFUND_STATES,
)

# ---------------------------------------------------------------------------
# Entity schemas
# ---------------------------------------------------------------------------

PAYMENT_INTENT_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "amount", "currency", "status", "created"],
    "properties": {
        "id": {"type": "string"},
        "amount": {"type": "integer", "minimum": 0},
        "currency": {"type": "string"},
        "status": {
            "type": "string",
            "enum": PAYMENT_INTENT_STATES,
        },
        "customer": {"type": "string", "x-terrarium-ref": "customer"},
        "payment_method": {"type": "string"},
        "description": {"type": "string"},
        "metadata": {"type": "object"},
        "created": {"type": "integer"},
        "canceled_at": {"type": "integer"},
        "cancellation_reason": {"type": "string"},
        "amount_capturable": {"type": "integer"},
        "amount_received": {"type": "integer"},
    },
}

CHARGE_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "amount", "currency", "created"],
    "properties": {
        "id": {"type": "string"},
        "amount": {"type": "integer"},
        "currency": {"type": "string"},
        "customer": {"type": "string", "x-terrarium-ref": "customer"},
        "payment_intent": {"type": "string", "x-terrarium-ref": "payment_intent"},
        "paid": {"type": "boolean"},
        "captured": {"type": "boolean"},
        "refunded": {"type": "boolean"},
        "disputed": {"type": "boolean"},
        "failure_code": {"type": "string"},
        "failure_message": {"type": "string"},
        "receipt_email": {"type": "string"},
        "created": {"type": "integer"},
    },
}

CUSTOMER_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "created"],
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "email": {"type": "string"},
        "phone": {"type": "string"},
        "description": {"type": "string"},
        "address": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "country": {"type": "string"},
                "line1": {"type": "string"},
                "line2": {"type": "string"},
                "postal_code": {"type": "string"},
                "state": {"type": "string"},
            },
        },
        "balance": {"type": "integer", "default": 0},
        "currency": {"type": "string"},
        "metadata": {"type": "object"},
        "created": {"type": "integer"},
    },
}

REFUND_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "amount", "charge", "currency", "status", "created"],
    "properties": {
        "id": {"type": "string"},
        "amount": {"type": "integer"},
        "charge": {"type": "string", "x-terrarium-ref": "charge"},
        "currency": {"type": "string"},
        "status": {
            "type": "string",
            "enum": REFUND_STATES,
        },
        "reason": {
            "type": "string",
            "enum": ["duplicate", "fraudulent", "requested_by_customer"],
        },
        "payment_intent": {"type": "string"},
        "failure_reason": {"type": "string"},
        "created": {"type": "integer"},
        "metadata": {"type": "object"},
    },
}

# ---------------------------------------------------------------------------
# Tool definitions (aligned with official @stripe/mcp)
# ---------------------------------------------------------------------------

PAYMENTS_TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "list_payment_intents",
        "description": "List payment intents, optionally filtered by customer or status.",
        "http_path": "/v1/payment_intents",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "customer": {
                    "type": "string",
                    "description": "Filter by customer ID.",
                },
                "status": {
                    "type": "string",
                    "description": "Filter by payment intent status.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                    "default": 10,
                },
            },
        },
    },
    {
        "name": "create_customer",
        "description": "Create a new customer.",
        "http_path": "/v1/customers",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Customer's full name.",
                },
                "email": {
                    "type": "string",
                    "description": "Customer's email address.",
                },
                "phone": {
                    "type": "string",
                    "description": "Customer's phone number.",
                },
                "description": {
                    "type": "string",
                    "description": "Arbitrary description of the customer.",
                },
                "metadata": {
                    "type": "object",
                    "description": "Key-value metadata.",
                },
            },
        },
    },
    {
        "name": "list_customers",
        "description": "List customers, optionally filtered by email.",
        "http_path": "/v1/customers",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "email": {
                    "type": "string",
                    "description": "Filter by customer email.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                    "default": 10,
                },
            },
        },
    },
    {
        "name": "create_refund",
        "description": "Create a refund for a charge. Omit amount for a full refund.",
        "http_path": "/v1/refunds",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["charge"],
            "properties": {
                "charge": {
                    "type": "string",
                    "description": "ID of the charge to refund.",
                },
                "amount": {
                    "type": "integer",
                    "description": "Amount to refund in cents. Omit for full refund.",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for the refund.",
                    "enum": ["duplicate", "fraudulent", "requested_by_customer"],
                },
            },
        },
    },
    {
        "name": "list_invoices",
        "description": "List invoices, optionally filtered by customer or status.",
        "http_path": "/v1/invoices",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "customer": {
                    "type": "string",
                    "description": "Filter by customer ID.",
                },
                "status": {
                    "type": "string",
                    "description": "Filter by invoice status.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                },
            },
        },
    },
    {
        "name": "create_invoice",
        "description": "Create a new invoice for a customer.",
        "http_path": "/v1/invoices",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["customer"],
            "properties": {
                "customer": {
                    "type": "string",
                    "description": "Customer ID to invoice.",
                },
                "description": {
                    "type": "string",
                    "description": "Description for the invoice.",
                },
                "metadata": {
                    "type": "object",
                    "description": "Key-value metadata.",
                },
            },
        },
    },
    {
        "name": "list_disputes",
        "description": "List disputes.",
        "http_path": "/v1/disputes",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                },
            },
        },
    },
    {
        "name": "update_dispute",
        "description": "Update a dispute with evidence or metadata.",
        "http_path": "/v1/disputes/{id}",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "ID of the dispute to update.",
                },
                "evidence": {
                    "type": "object",
                    "description": "Evidence to attach to the dispute.",
                },
                "metadata": {
                    "type": "object",
                    "description": "Key-value metadata.",
                },
            },
        },
    },
]
