"""Entity schemas and tool definitions for the payments service pack.

Pure data -- no logic, no imports beyond stdlib.  Aligned with Stripe's
API object shapes and the official @stripe/mcp tool surface.
"""

from __future__ import annotations

from terrarium.packs.verified.payments.state_machines import (
    DISPUTE_STATES,
    INVOICE_STATES,
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
        "object": {"type": "string", "const": "payment_intent"},
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
        "receipt_email": {"type": "string"},
        "confirmation_method": {
            "type": "string",
            "enum": ["automatic", "manual"],
        },
        "client_secret": {"type": "string"},
        "livemode": {"type": "boolean"},
        "next_action": {"type": ["object", "null"]},
        "last_payment_error": {"type": ["object", "null"]},
        "shipping": {"type": ["object", "null"]},
        "capture_method": {
            "type": "string",
            "enum": ["automatic", "manual"],
        },
    },
}

CHARGE_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "amount", "currency", "created"],
    "properties": {
        "id": {"type": "string"},
        "object": {"type": "string", "const": "charge"},
        "amount": {"type": "integer"},
        "currency": {"type": "string"},
        "customer": {"type": "string", "x-terrarium-ref": "customer"},
        "payment_intent": {
            "type": "string",
            "x-terrarium-ref": "payment_intent",
        },
        "paid": {"type": "boolean"},
        "captured": {"type": "boolean"},
        "refunded": {"type": "boolean"},
        "disputed": {"type": "boolean"},
        "failure_code": {"type": "string"},
        "failure_message": {"type": "string"},
        "receipt_email": {"type": "string"},
        "created": {"type": "integer"},
        "receipt_number": {"type": ["string", "null"]},
        "statement_descriptor": {"type": ["string", "null"]},
        "balance_transaction": {"type": ["string", "null"]},
        "livemode": {"type": "boolean"},
        "outcome": {
            "type": ["object", "null"],
            "properties": {
                "network_status": {"type": "string"},
                "reason": {"type": ["string", "null"]},
                "risk_level": {"type": "string"},
                "risk_score": {"type": "integer"},
                "seller_message": {"type": "string"},
                "type": {"type": "string"},
            },
        },
    },
}

CUSTOMER_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "created"],
    "properties": {
        "id": {"type": "string"},
        "object": {"type": "string", "const": "customer"},
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
        "invoice_settings": {
            "type": "object",
            "properties": {
                "default_payment_method": {"type": ["string", "null"]},
            },
        },
        "default_source": {"type": ["string", "null"]},
        "livemode": {"type": "boolean"},
        "delinquent": {"type": "boolean"},
        "invoice_prefix": {"type": "string"},
    },
}

REFUND_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "amount", "charge", "currency", "status", "created"],
    "properties": {
        "id": {"type": "string"},
        "object": {"type": "string", "const": "refund"},
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
        "balance_transaction": {"type": ["string", "null"]},
        "receipt_number": {"type": ["string", "null"]},
    },
}

INVOICE_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "customer", "currency", "status", "created"],
    "properties": {
        "id": {"type": "string"},
        "object": {"type": "string", "const": "invoice"},
        "customer": {"type": "string", "x-terrarium-ref": "customer"},
        "amount_due": {"type": "integer"},
        "amount_paid": {"type": "integer"},
        "amount_remaining": {"type": "integer"},
        "currency": {"type": "string"},
        "status": {
            "type": "string",
            "enum": INVOICE_STATES,
        },
        "description": {"type": "string"},
        "due_date": {"type": ["integer", "null"]},
        "created": {"type": "integer"},
        "metadata": {"type": "object"},
        "livemode": {"type": "boolean"},
        "number": {"type": ["string", "null"]},
        "lines": {
            "type": "object",
            "properties": {
                "object": {"type": "string", "const": "list"},
                "data": {"type": "array"},
                "has_more": {"type": "boolean"},
                "url": {"type": "string"},
            },
        },
    },
}

DISPUTE_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "charge", "amount", "currency", "status", "created"],
    "properties": {
        "id": {"type": "string"},
        "object": {"type": "string", "const": "dispute"},
        "charge": {"type": "string", "x-terrarium-ref": "charge"},
        "amount": {"type": "integer"},
        "currency": {"type": "string"},
        "status": {
            "type": "string",
            "enum": DISPUTE_STATES,
        },
        "reason": {
            "type": "string",
            "enum": [
                "duplicate",
                "fraudulent",
                "subscription_canceled",
                "product_unacceptable",
                "product_not_received",
                "unrecognized",
                "credit_not_processed",
                "general",
            ],
        },
        "evidence": {"type": ["object", "null"]},
        "created": {"type": "integer"},
        "metadata": {"type": "object"},
    },
}

# ---------------------------------------------------------------------------
# Stripe list response schema (shared by all list endpoints)
# ---------------------------------------------------------------------------

_STRIPE_LIST_RESPONSE: dict = {
    "type": "object",
    "properties": {
        "object": {"const": "list"},
        "data": {"type": "array"},
        "has_more": {"type": "boolean"},
        "url": {"type": "string"},
    },
}

# ---------------------------------------------------------------------------
# Tool definitions (aligned with official @stripe/mcp)
# ---------------------------------------------------------------------------

PAYMENTS_TOOL_DEFINITIONS: list[dict] = [
    # -- Payment Intents --
    {
        "name": "create_payment_intent",
        "description": "Create a new payment intent.",
        "http_path": "/v1/payment_intents",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["amount", "currency"],
            "properties": {
                "amount": {
                    "type": "integer",
                    "description": "Amount in smallest currency unit (e.g. cents).",
                },
                "currency": {
                    "type": "string",
                    "description": "Three-letter ISO currency code.",
                },
                "customer": {
                    "type": "string",
                    "description": "ID of the customer.",
                },
                "description": {
                    "type": "string",
                    "description": "Description of the payment intent.",
                },
                "receipt_email": {
                    "type": "string",
                    "description": "Email to send the receipt to.",
                },
                "confirmation_method": {
                    "type": "string",
                    "description": "'automatic' or 'manual'.",
                    "enum": ["automatic", "manual"],
                },
                "capture_method": {
                    "type": "string",
                    "description": "'automatic' or 'manual'.",
                    "enum": ["automatic", "manual"],
                },
                "payment_method": {
                    "type": "string",
                    "description": "ID of the payment method to attach.",
                },
                "metadata": {
                    "type": "object",
                    "description": "Key-value metadata.",
                },
            },
        },
        "response_schema": {"type": "object"},
    },
    {
        "name": "get_payment_intent",
        "description": "Retrieve a single payment intent by ID.",
        "http_path": "/v1/payment_intents/{id}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "ID of the payment intent to retrieve.",
                },
            },
        },
        "response_schema": {"type": "object"},
    },
    {
        "name": "confirm_payment_intent",
        "description": "Confirm a payment intent, transitioning it to processing/succeeded.",
        "http_path": "/v1/payment_intents/{id}/confirm",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "ID of the payment intent to confirm.",
                },
                "payment_method": {
                    "type": "string",
                    "description": "Payment method to use for confirmation.",
                },
            },
        },
        "response_schema": {"type": "object"},
    },
    {
        "name": "cancel_payment_intent",
        "description": "Cancel a payment intent.",
        "http_path": "/v1/payment_intents/{id}/cancel",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "ID of the payment intent to cancel.",
                },
                "cancellation_reason": {
                    "type": "string",
                    "description": "Reason for cancellation.",
                    "enum": [
                        "duplicate",
                        "fraudulent",
                        "requested_by_customer",
                        "abandoned",
                    ],
                },
            },
        },
        "response_schema": {"type": "object"},
    },
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
        "response_schema": _STRIPE_LIST_RESPONSE,
    },
    # -- Customers --
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
        "response_schema": {"type": "object"},
    },
    {
        "name": "get_customer",
        "description": "Retrieve a single customer by ID.",
        "http_path": "/v1/customers/{id}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "ID of the customer to retrieve.",
                },
            },
        },
        "response_schema": {"type": "object"},
    },
    {
        "name": "update_customer",
        "description": "Update a customer's fields.",
        "http_path": "/v1/customers/{id}",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "ID of the customer to update.",
                },
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
        "response_schema": {"type": "object"},
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
        "response_schema": _STRIPE_LIST_RESPONSE,
    },
    # -- Charges --
    {
        "name": "get_charge",
        "description": "Retrieve a single charge by ID.",
        "http_path": "/v1/charges/{id}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "ID of the charge to retrieve.",
                },
            },
        },
        "response_schema": {"type": "object"},
    },
    # -- Refunds --
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
        "response_schema": {"type": "object"},
    },
    {
        "name": "get_refund",
        "description": "Retrieve a single refund by ID.",
        "http_path": "/v1/refunds/{id}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "ID of the refund to retrieve.",
                },
            },
        },
        "response_schema": {"type": "object"},
    },
    {
        "name": "list_refunds",
        "description": "List refunds, optionally filtered by charge.",
        "http_path": "/v1/refunds",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "charge": {
                    "type": "string",
                    "description": "Filter by charge ID.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                    "default": 10,
                },
            },
        },
        "response_schema": _STRIPE_LIST_RESPONSE,
    },
    # -- Invoices --
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
        "response_schema": {"type": "object"},
    },
    {
        "name": "get_invoice",
        "description": "Retrieve a single invoice by ID.",
        "http_path": "/v1/invoices/{id}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "ID of the invoice to retrieve.",
                },
            },
        },
        "response_schema": {"type": "object"},
    },
    {
        "name": "finalize_invoice",
        "description": "Finalize a draft invoice, transitioning it to open.",
        "http_path": "/v1/invoices/{id}/finalize",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "ID of the invoice to finalize.",
                },
            },
        },
        "response_schema": {"type": "object"},
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
        "response_schema": _STRIPE_LIST_RESPONSE,
    },
    # -- Disputes --
    {
        "name": "get_dispute",
        "description": "Retrieve a single dispute by ID.",
        "http_path": "/v1/disputes/{id}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "ID of the dispute to retrieve.",
                },
            },
        },
        "response_schema": {"type": "object"},
    },
    {
        "name": "close_dispute",
        "description": "Close a dispute by accepting it.",
        "http_path": "/v1/disputes/{id}/close",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "ID of the dispute to close.",
                },
            },
        },
        "response_schema": {"type": "object"},
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
        "response_schema": _STRIPE_LIST_RESPONSE,
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
        "response_schema": {"type": "object"},
    },
]
