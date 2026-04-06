"""Tests for volnix.packs.verified.stripe -- PaymentsPack through pack's own handle_action."""

import pytest

from volnix.core.context import ResponseProposal
from volnix.core.types import ToolName
from volnix.packs.verified.stripe.pack import PaymentsPack
from volnix.validation.schema import SchemaValidator
from volnix.validation.state_machine import StateMachineValidator


@pytest.fixture
def payments_pack():
    return PaymentsPack()


@pytest.fixture
def sample_state():
    """State with pre-existing charges, customers, payment intents, invoices, disputes, refunds."""
    return {
        "customers": [
            {
                "id": "cus_existing001",
                "object": "customer",
                "name": "Alice Smith",
                "email": "alice@example.com",
                "balance": 0,
                "livemode": False,
                "delinquent": False,
                "created": 1700000000,
            },
            {
                "id": "cus_existing002",
                "object": "customer",
                "name": "Bob Jones",
                "email": "bob@example.com",
                "balance": 0,
                "livemode": False,
                "delinquent": False,
                "created": 1700000100,
            },
        ],
        "charges": [
            {
                "id": "ch_paid001",
                "object": "charge",
                "amount": 5000,
                "currency": "usd",
                "customer": "cus_existing001",
                "paid": True,
                "captured": True,
                "refunded": False,
                "disputed": False,
                "payment_intent": "pi_intent001",
                "livemode": False,
                "created": 1700001000,
            },
            {
                "id": "ch_unpaid002",
                "object": "charge",
                "amount": 3000,
                "currency": "usd",
                "customer": "cus_existing002",
                "paid": False,
                "captured": False,
                "refunded": False,
                "disputed": False,
                "livemode": False,
                "created": 1700001100,
            },
            {
                "id": "ch_small003",
                "object": "charge",
                "amount": 1000,
                "currency": "eur",
                "customer": "cus_existing001",
                "paid": True,
                "captured": True,
                "refunded": False,
                "disputed": False,
                "livemode": False,
                "created": 1700001200,
            },
        ],
        "payment_intents": [
            {
                "id": "pi_intent001",
                "object": "payment_intent",
                "amount": 5000,
                "currency": "usd",
                "status": "succeeded",
                "customer": "cus_existing001",
                "livemode": False,
                "amount_received": 5000,
                "created": 1700000500,
            },
            {
                "id": "pi_intent002",
                "object": "payment_intent",
                "amount": 3000,
                "currency": "usd",
                "status": "requires_payment_method",
                "customer": "cus_existing002",
                "livemode": False,
                "amount_received": 0,
                "created": 1700000600,
            },
            {
                "id": "pi_confirmable003",
                "object": "payment_intent",
                "amount": 7500,
                "currency": "usd",
                "status": "requires_confirmation",
                "customer": "cus_existing001",
                "livemode": False,
                "amount_received": 0,
                "created": 1700000700,
            },
        ],
        "invoices": [
            {
                "id": "in_inv001",
                "object": "invoice",
                "customer": "cus_existing001",
                "status": "paid",
                "currency": "usd",
                "amount_due": 5000,
                "amount_paid": 5000,
                "amount_remaining": 0,
                "livemode": False,
                "created": 1700002000,
            },
            {
                "id": "in_inv002",
                "object": "invoice",
                "customer": "cus_existing002",
                "status": "draft",
                "currency": "usd",
                "amount_due": 3000,
                "amount_paid": 0,
                "amount_remaining": 3000,
                "livemode": False,
                "created": 1700002100,
            },
        ],
        "disputes": [
            {
                "id": "dp_disp001",
                "object": "dispute",
                "charge": "ch_paid001",
                "amount": 5000,
                "currency": "usd",
                "status": "needs_response",
                "evidence": None,
                "metadata": {},
                "created": 1700003000,
            },
            {
                "id": "dp_disp_closed",
                "object": "dispute",
                "charge": "ch_small003",
                "amount": 1000,
                "currency": "eur",
                "status": "lost",
                "evidence": None,
                "metadata": {},
                "created": 1700003100,
            },
        ],
        "refunds": [
            {
                "id": "re_existing001",
                "object": "refund",
                "amount": 1000,
                "charge": "ch_small003",
                "currency": "eur",
                "status": "succeeded",
                "reason": "requested_by_customer",
                "payment_intent": None,
                "created": 1700004000,
            },
        ],
    }


# ===================================================================
# Metadata tests
# ===================================================================


class TestPaymentsPackMetadata:
    def test_metadata(self, payments_pack):
        """pack_name, category, fidelity_tier are correct."""
        assert payments_pack.pack_name == "stripe"
        assert payments_pack.category == "money"
        assert payments_pack.fidelity_tier == 1

    def test_tools_count_and_names(self, payments_pack):
        """PaymentsPack exposes 21 tools with expected names."""
        tools = payments_pack.get_tools()
        assert len(tools) == 21
        tool_names = {t["name"] for t in tools}
        assert tool_names == {
            "create_payment_intent",
            "get_payment_intent",
            "confirm_payment_intent",
            "cancel_payment_intent",
            "list_payment_intents",
            "create_customer",
            "get_customer",
            "update_customer",
            "list_customers",
            "get_charge",
            "create_refund",
            "get_refund",
            "list_refunds",
            "create_invoice",
            "get_invoice",
            "finalize_invoice",
            "list_invoices",
            "get_dispute",
            "close_dispute",
            "list_disputes",
            "update_dispute",
        }

    def test_entity_schemas_six_types(self, payments_pack):
        """All 6 entity schemas are present."""
        schemas = payments_pack.get_entity_schemas()
        expected = {"payment_intent", "charge", "customer", "refund", "invoice", "dispute"}
        assert set(schemas.keys()) == expected

    def test_state_machines_four_types(self, payments_pack):
        """State machines for payment_intent, refund, invoice, dispute."""
        sms = payments_pack.get_state_machines()
        expected = {"payment_intent", "refund", "invoice", "dispute"}
        assert set(sms.keys()) == expected
        for key in expected:
            assert "transitions" in sms[key]

    def test_payment_intent_transitions(self, payments_pack):
        pi = payments_pack.get_state_machines()["payment_intent"]["transitions"]
        assert "succeeded" in pi["processing"]
        assert pi["succeeded"] == []  # terminal

    def test_invoice_transitions(self, payments_pack):
        inv = payments_pack.get_state_machines()["invoice"]["transitions"]
        assert "open" in inv["draft"]
        assert "void" in inv["draft"]
        assert "paid" in inv["open"]
        assert inv["paid"] == []

    def test_dispute_transitions(self, payments_pack):
        dsp = payments_pack.get_state_machines()["dispute"]["transitions"]
        assert "warning_under_review" in dsp["warning_needs_response"]
        assert "under_review" in dsp["needs_response"]
        assert dsp["won"] == []
        assert dsp["lost"] == []


# ===================================================================
# P0: Payment Intent CRUD
# ===================================================================


class TestPaymentIntentActions:
    async def test_create_payment_intent(self, payments_pack):
        """create_payment_intent creates entity with status=requires_payment_method."""
        proposal = await payments_pack.handle_action(
            ToolName("create_payment_intent"),
            {"amount": 2500, "currency": "usd", "customer": "cus_existing001"},
            {},
        )
        assert isinstance(proposal, ResponseProposal)
        body = proposal.response_body
        assert body["object"] == "payment_intent"
        assert body["amount"] == 2500
        assert body["currency"] == "usd"
        assert body["status"] == "requires_payment_method"
        assert body["customer"] == "cus_existing001"
        assert body["id"].startswith("pi_")
        assert body["livemode"] is False
        assert body["confirmation_method"] == "automatic"
        assert body["capture_method"] == "automatic"
        assert body["client_secret"].startswith(body["id"])
        assert body["next_action"] is None
        assert body["last_payment_error"] is None
        assert body["amount_received"] == 0
        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.entity_type == "payment_intent"
        assert delta.operation == "create"

    async def test_create_payment_intent_with_options(self, payments_pack):
        """create_payment_intent respects confirmation_method, capture_method."""
        proposal = await payments_pack.handle_action(
            ToolName("create_payment_intent"),
            {
                "amount": 1000,
                "currency": "eur",
                "confirmation_method": "manual",
                "capture_method": "manual",
                "receipt_email": "test@example.com",
            },
            {},
        )
        body = proposal.response_body
        assert body["confirmation_method"] == "manual"
        assert body["capture_method"] == "manual"
        assert body["receipt_email"] == "test@example.com"

    async def test_get_payment_intent(self, payments_pack, sample_state):
        """get_payment_intent retrieves a single PI."""
        proposal = await payments_pack.handle_action(
            ToolName("get_payment_intent"),
            {"id": "pi_intent001"},
            sample_state,
        )
        body = proposal.response_body
        assert body["id"] == "pi_intent001"
        assert body["object"] == "payment_intent"
        assert body["amount"] == 5000
        assert body["status"] == "succeeded"
        assert len(proposal.proposed_state_deltas) == 0

    async def test_get_payment_intent_not_found(self, payments_pack, sample_state):
        """get_payment_intent returns Stripe error for missing ID."""
        proposal = await payments_pack.handle_action(
            ToolName("get_payment_intent"),
            {"id": "pi_nonexistent"},
            sample_state,
        )
        assert "error" in proposal.response_body
        assert proposal.response_body["error"]["type"] == "invalid_request_error"
        assert "No such payment_intent" in proposal.response_body["error"]["message"]

    async def test_confirm_payment_intent_from_requires_payment_method(
        self, payments_pack, sample_state
    ):
        """confirm_payment_intent transitions to succeeded and creates charge."""
        proposal = await payments_pack.handle_action(
            ToolName("confirm_payment_intent"),
            {"id": "pi_intent002"},
            sample_state,
        )
        body = proposal.response_body
        assert body["status"] == "succeeded"
        assert body["amount_received"] == 3000
        assert body["object"] == "payment_intent"
        # Should produce 2 deltas: PI update + charge create
        assert len(proposal.proposed_state_deltas) == 2
        pi_delta = proposal.proposed_state_deltas[0]
        assert pi_delta.entity_type == "payment_intent"
        assert pi_delta.operation == "update"
        assert pi_delta.fields["status"] == "succeeded"
        charge_delta = proposal.proposed_state_deltas[1]
        assert charge_delta.entity_type == "charge"
        assert charge_delta.operation == "create"
        charge = charge_delta.fields
        assert charge["object"] == "charge"
        assert charge["amount"] == 3000
        assert charge["paid"] is True
        assert charge["payment_intent"] == "pi_intent002"
        assert charge["livemode"] is False
        assert charge["outcome"]["network_status"] == "approved_by_network"

    async def test_confirm_payment_intent_from_requires_confirmation(
        self, payments_pack, sample_state
    ):
        """confirm_payment_intent also works from requires_confirmation."""
        proposal = await payments_pack.handle_action(
            ToolName("confirm_payment_intent"),
            {"id": "pi_confirmable003"},
            sample_state,
        )
        assert proposal.response_body["status"] == "succeeded"
        assert len(proposal.proposed_state_deltas) == 2

    async def test_confirm_payment_intent_already_succeeded(self, payments_pack, sample_state):
        """confirm_payment_intent fails for already-succeeded PI."""
        proposal = await payments_pack.handle_action(
            ToolName("confirm_payment_intent"),
            {"id": "pi_intent001"},
            sample_state,
        )
        assert "error" in proposal.response_body
        assert "cannot be confirmed" in proposal.response_body["error"]["message"]

    async def test_confirm_payment_intent_not_found(self, payments_pack, sample_state):
        """confirm_payment_intent fails for missing PI."""
        proposal = await payments_pack.handle_action(
            ToolName("confirm_payment_intent"),
            {"id": "pi_ghost"},
            sample_state,
        )
        assert "error" in proposal.response_body
        assert "No such payment_intent" in proposal.response_body["error"]["message"]

    async def test_cancel_payment_intent(self, payments_pack, sample_state):
        """cancel_payment_intent transitions to canceled."""
        proposal = await payments_pack.handle_action(
            ToolName("cancel_payment_intent"),
            {"id": "pi_intent002", "cancellation_reason": "abandoned"},
            sample_state,
        )
        body = proposal.response_body
        assert body["status"] == "canceled"
        assert body["cancellation_reason"] == "abandoned"
        assert body["canceled_at"] is not None
        assert body["object"] == "payment_intent"
        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.fields["status"] == "canceled"

    async def test_cancel_payment_intent_already_succeeded(self, payments_pack, sample_state):
        """cancel_payment_intent fails for already-succeeded PI."""
        proposal = await payments_pack.handle_action(
            ToolName("cancel_payment_intent"),
            {"id": "pi_intent001"},
            sample_state,
        )
        assert "error" in proposal.response_body
        assert "cannot be canceled" in proposal.response_body["error"]["message"]

    async def test_cancel_payment_intent_not_found(self, payments_pack, sample_state):
        """cancel_payment_intent fails for missing PI."""
        proposal = await payments_pack.handle_action(
            ToolName("cancel_payment_intent"),
            {"id": "pi_ghost"},
            sample_state,
        )
        assert "error" in proposal.response_body

    async def test_list_payment_intents(self, payments_pack, sample_state):
        """list_payment_intents filters by customer and status."""
        # Filter by customer
        proposal = await payments_pack.handle_action(
            ToolName("list_payment_intents"),
            {"customer": "cus_existing001"},
            sample_state,
        )
        data = proposal.response_body["data"]
        assert len(data) == 2  # pi_intent001 and pi_confirmable003
        assert proposal.response_body["object"] == "list"
        assert proposal.response_body["url"] == "/v1/payment_intents"

        # Filter by status
        proposal2 = await payments_pack.handle_action(
            ToolName("list_payment_intents"),
            {"status": "requires_payment_method"},
            sample_state,
        )
        assert len(proposal2.response_body["data"]) == 1
        assert proposal2.response_body["data"][0]["id"] == "pi_intent002"

    async def test_list_payment_intents_pagination(self, payments_pack, sample_state):
        """list_payment_intents respects limit and has_more."""
        proposal = await payments_pack.handle_action(
            ToolName("list_payment_intents"),
            {"limit": 1},
            sample_state,
        )
        assert len(proposal.response_body["data"]) == 1
        assert proposal.response_body["has_more"] is True


# ===================================================================
# P0 + P1: Customer CRUD
# ===================================================================


class TestCustomerActions:
    async def test_create_customer(self, payments_pack):
        """create_customer creates entity with balance=0, new P1 fields."""
        proposal = await payments_pack.handle_action(
            ToolName("create_customer"),
            {
                "name": "Jane Doe",
                "email": "jane@example.com",
                "phone": "+1234567890",
            },
            {},
        )
        assert isinstance(proposal, ResponseProposal)
        body = proposal.response_body
        assert body["object"] == "customer"
        assert body["name"] == "Jane Doe"
        assert body["email"] == "jane@example.com"
        assert body["balance"] == 0
        assert body["id"].startswith("cus_")
        assert isinstance(body["created"], int)
        assert body["livemode"] is False
        assert body["delinquent"] is False
        assert body["invoice_settings"] == {"default_payment_method": None}
        assert body["default_source"] is None
        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.entity_type == "customer"
        assert delta.operation == "create"

    async def test_get_customer(self, payments_pack, sample_state):
        """get_customer retrieves a single customer."""
        proposal = await payments_pack.handle_action(
            ToolName("get_customer"),
            {"id": "cus_existing001"},
            sample_state,
        )
        body = proposal.response_body
        assert body["id"] == "cus_existing001"
        assert body["object"] == "customer"
        assert body["name"] == "Alice Smith"
        assert len(proposal.proposed_state_deltas) == 0

    async def test_get_customer_not_found(self, payments_pack, sample_state):
        """get_customer returns Stripe error for missing customer."""
        proposal = await payments_pack.handle_action(
            ToolName("get_customer"),
            {"id": "cus_ghost"},
            sample_state,
        )
        assert "error" in proposal.response_body
        assert "No such customer" in proposal.response_body["error"]["message"]
        assert proposal.response_body["error"]["type"] == "invalid_request_error"

    async def test_update_customer(self, payments_pack, sample_state):
        """update_customer updates mutable fields."""
        proposal = await payments_pack.handle_action(
            ToolName("update_customer"),
            {"id": "cus_existing001", "name": "Alice Updated", "email": "alice-new@example.com"},
            sample_state,
        )
        body = proposal.response_body
        assert body["id"] == "cus_existing001"
        assert body["name"] == "Alice Updated"
        assert body["email"] == "alice-new@example.com"
        assert body["object"] == "customer"
        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.entity_type == "customer"
        assert delta.operation == "update"
        assert delta.fields["name"] == "Alice Updated"
        assert delta.previous_fields["name"] == "Alice Smith"

    async def test_update_customer_not_found(self, payments_pack, sample_state):
        """update_customer returns error for missing customer."""
        proposal = await payments_pack.handle_action(
            ToolName("update_customer"),
            {"id": "cus_ghost", "name": "Ghost"},
            sample_state,
        )
        assert "error" in proposal.response_body

    async def test_update_customer_no_changes(self, payments_pack, sample_state):
        """update_customer with only id produces no deltas."""
        proposal = await payments_pack.handle_action(
            ToolName("update_customer"),
            {"id": "cus_existing001"},
            sample_state,
        )
        assert len(proposal.proposed_state_deltas) == 0

    async def test_list_customers(self, payments_pack, sample_state):
        """list_customers returns filtered customers with Stripe list format."""
        # List all
        proposal = await payments_pack.handle_action(
            ToolName("list_customers"),
            {},
            sample_state,
        )
        body = proposal.response_body
        assert body["object"] == "list"
        assert body["url"] == "/v1/customers"
        assert len(body["data"]) == 2
        assert body["has_more"] is False

        # Filter by email
        proposal2 = await payments_pack.handle_action(
            ToolName("list_customers"),
            {"email": "alice@example.com"},
            sample_state,
        )
        assert len(proposal2.response_body["data"]) == 1
        assert proposal2.response_body["data"][0]["id"] == "cus_existing001"


# ===================================================================
# Charge read
# ===================================================================


class TestChargeActions:
    async def test_get_charge(self, payments_pack, sample_state):
        """get_charge retrieves a single charge."""
        proposal = await payments_pack.handle_action(
            ToolName("get_charge"),
            {"id": "ch_paid001"},
            sample_state,
        )
        body = proposal.response_body
        assert body["id"] == "ch_paid001"
        assert body["object"] == "charge"
        assert body["amount"] == 5000
        assert body["paid"] is True
        assert len(proposal.proposed_state_deltas) == 0

    async def test_get_charge_not_found(self, payments_pack, sample_state):
        """get_charge returns Stripe error for missing charge."""
        proposal = await payments_pack.handle_action(
            ToolName("get_charge"),
            {"id": "ch_ghost"},
            sample_state,
        )
        assert "error" in proposal.response_body
        assert "No such charge" in proposal.response_body["error"]["message"]
        assert proposal.response_body["error"]["type"] == "invalid_request_error"


# ===================================================================
# Refund CRUD
# ===================================================================


class TestRefundActions:
    async def test_create_refund_full(self, payments_pack, sample_state):
        """create_refund with no amount does a full refund and marks charge.refunded=True."""
        proposal = await payments_pack.handle_action(
            ToolName("create_refund"),
            {"charge": "ch_paid001"},
            sample_state,
        )
        assert isinstance(proposal, ResponseProposal)
        body = proposal.response_body
        assert body["id"].startswith("re_")
        assert body["object"] == "refund"
        assert body["amount"] == 5000  # full charge amount
        assert body["charge"] == "ch_paid001"
        assert body["currency"] == "usd"
        assert body["status"] == "pending"
        assert body["balance_transaction"] is None
        assert body["receipt_number"] is None

        # Two deltas: refund create + charge update
        assert len(proposal.proposed_state_deltas) == 2
        refund_delta = proposal.proposed_state_deltas[0]
        assert refund_delta.entity_type == "refund"
        assert refund_delta.operation == "create"
        charge_delta = proposal.proposed_state_deltas[1]
        assert charge_delta.entity_type == "charge"
        assert charge_delta.operation == "update"
        assert charge_delta.fields["refunded"] is True
        assert charge_delta.previous_fields["refunded"] is False

    async def test_create_refund_partial(self, payments_pack, sample_state):
        """create_refund with explicit amount < charge amount is a partial refund."""
        proposal = await payments_pack.handle_action(
            ToolName("create_refund"),
            {"charge": "ch_paid001", "amount": 2000, "reason": "duplicate"},
            sample_state,
        )
        body = proposal.response_body
        assert body["amount"] == 2000
        assert body["reason"] == "duplicate"

        # Only 1 delta: refund create (no charge update for partial refund)
        assert len(proposal.proposed_state_deltas) == 1
        assert proposal.proposed_state_deltas[0].entity_type == "refund"
        assert proposal.proposed_state_deltas[0].operation == "create"

    async def test_create_refund_charge_not_found(self, payments_pack, sample_state):
        """create_refund returns error when charge does not exist."""
        proposal = await payments_pack.handle_action(
            ToolName("create_refund"),
            {"charge": "ch_nonexistent"},
            sample_state,
        )
        assert "error" in proposal.response_body
        assert "No such charge" in proposal.response_body["error"]["message"]
        assert proposal.response_body["error"]["type"] == "invalid_request_error"
        assert len(proposal.proposed_state_deltas) == 0

    async def test_create_refund_charge_not_paid(self, payments_pack, sample_state):
        """create_refund returns error when charge is not paid."""
        proposal = await payments_pack.handle_action(
            ToolName("create_refund"),
            {"charge": "ch_unpaid002"},
            sample_state,
        )
        assert "error" in proposal.response_body
        assert "not been paid" in proposal.response_body["error"]["message"]
        assert len(proposal.proposed_state_deltas) == 0

    async def test_create_refund_exceeds_amount(self, payments_pack, sample_state):
        """create_refund returns error when refund amount exceeds charge amount."""
        proposal = await payments_pack.handle_action(
            ToolName("create_refund"),
            {"charge": "ch_small003", "amount": 9999},
            sample_state,
        )
        assert "error" in proposal.response_body
        assert "greater than" in proposal.response_body["error"]["message"]
        assert len(proposal.proposed_state_deltas) == 0

    async def test_get_refund(self, payments_pack, sample_state):
        """get_refund retrieves a single refund."""
        proposal = await payments_pack.handle_action(
            ToolName("get_refund"),
            {"id": "re_existing001"},
            sample_state,
        )
        body = proposal.response_body
        assert body["id"] == "re_existing001"
        assert body["object"] == "refund"
        assert body["amount"] == 1000
        assert len(proposal.proposed_state_deltas) == 0

    async def test_get_refund_not_found(self, payments_pack, sample_state):
        """get_refund returns Stripe error for missing refund."""
        proposal = await payments_pack.handle_action(
            ToolName("get_refund"),
            {"id": "re_ghost"},
            sample_state,
        )
        assert "error" in proposal.response_body
        assert "No such refund" in proposal.response_body["error"]["message"]

    async def test_list_refunds(self, payments_pack, sample_state):
        """list_refunds returns all refunds with Stripe list format."""
        proposal = await payments_pack.handle_action(
            ToolName("list_refunds"),
            {},
            sample_state,
        )
        body = proposal.response_body
        assert body["object"] == "list"
        assert body["url"] == "/v1/refunds"
        assert len(body["data"]) == 1

    async def test_list_refunds_filter_by_charge(self, payments_pack, sample_state):
        """list_refunds filters by charge."""
        proposal = await payments_pack.handle_action(
            ToolName("list_refunds"),
            {"charge": "ch_small003"},
            sample_state,
        )
        assert len(proposal.response_body["data"]) == 1
        assert proposal.response_body["data"][0]["charge"] == "ch_small003"

    async def test_list_refunds_no_match(self, payments_pack, sample_state):
        """list_refunds returns empty when no charge matches."""
        proposal = await payments_pack.handle_action(
            ToolName("list_refunds"),
            {"charge": "ch_nonexistent"},
            sample_state,
        )
        assert len(proposal.response_body["data"]) == 0


# ===================================================================
# Invoice CRUD
# ===================================================================


class TestInvoiceActions:
    async def test_create_invoice(self, payments_pack):
        """create_invoice creates a draft invoice with all P1 fields."""
        proposal = await payments_pack.handle_action(
            ToolName("create_invoice"),
            {"customer": "cus_existing001", "description": "Monthly subscription"},
            {},
        )
        body = proposal.response_body
        assert body["id"].startswith("in_")
        assert body["object"] == "invoice"
        assert body["customer"] == "cus_existing001"
        assert body["status"] == "draft"
        assert body["description"] == "Monthly subscription"
        assert body["amount_due"] == 0
        assert body["amount_paid"] == 0
        assert body["amount_remaining"] == 0
        assert body["currency"] == "usd"
        assert body["livemode"] is False
        assert body["number"] is not None
        assert body["lines"]["object"] == "list"
        assert body["lines"]["data"] == []
        assert len(proposal.proposed_state_deltas) == 1
        assert proposal.proposed_state_deltas[0].entity_type == "invoice"
        assert proposal.proposed_state_deltas[0].operation == "create"

    async def test_get_invoice(self, payments_pack, sample_state):
        """get_invoice retrieves a single invoice."""
        proposal = await payments_pack.handle_action(
            ToolName("get_invoice"),
            {"id": "in_inv001"},
            sample_state,
        )
        body = proposal.response_body
        assert body["id"] == "in_inv001"
        assert body["object"] == "invoice"
        assert body["customer"] == "cus_existing001"
        assert len(proposal.proposed_state_deltas) == 0

    async def test_get_invoice_not_found(self, payments_pack, sample_state):
        """get_invoice returns Stripe error for missing invoice."""
        proposal = await payments_pack.handle_action(
            ToolName("get_invoice"),
            {"id": "in_ghost"},
            sample_state,
        )
        assert "error" in proposal.response_body
        assert "No such invoice" in proposal.response_body["error"]["message"]

    async def test_finalize_invoice(self, payments_pack, sample_state):
        """finalize_invoice transitions draft to open."""
        proposal = await payments_pack.handle_action(
            ToolName("finalize_invoice"),
            {"id": "in_inv002"},
            sample_state,
        )
        body = proposal.response_body
        assert body["id"] == "in_inv002"
        assert body["status"] == "open"
        assert body["object"] == "invoice"
        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.entity_type == "invoice"
        assert delta.operation == "update"
        assert delta.fields["status"] == "open"
        assert delta.previous_fields["status"] == "draft"

    async def test_finalize_invoice_already_open(self, payments_pack, sample_state):
        """finalize_invoice fails for non-draft invoice."""
        # in_inv001 has status "paid"
        proposal = await payments_pack.handle_action(
            ToolName("finalize_invoice"),
            {"id": "in_inv001"},
            sample_state,
        )
        assert "error" in proposal.response_body
        assert "cannot be finalized" in proposal.response_body["error"]["message"]

    async def test_finalize_invoice_not_found(self, payments_pack, sample_state):
        """finalize_invoice fails for missing invoice."""
        proposal = await payments_pack.handle_action(
            ToolName("finalize_invoice"),
            {"id": "in_ghost"},
            sample_state,
        )
        assert "error" in proposal.response_body

    async def test_list_invoices(self, payments_pack, sample_state):
        """list_invoices filters by customer and status."""
        # All invoices
        proposal = await payments_pack.handle_action(
            ToolName("list_invoices"),
            {},
            sample_state,
        )
        body = proposal.response_body
        assert body["object"] == "list"
        assert body["url"] == "/v1/invoices"
        assert len(body["data"]) == 2

        # Filter by customer
        proposal2 = await payments_pack.handle_action(
            ToolName("list_invoices"),
            {"customer": "cus_existing001"},
            sample_state,
        )
        assert len(proposal2.response_body["data"]) == 1
        assert proposal2.response_body["data"][0]["id"] == "in_inv001"

        # Filter by status
        proposal3 = await payments_pack.handle_action(
            ToolName("list_invoices"),
            {"status": "draft"},
            sample_state,
        )
        assert len(proposal3.response_body["data"]) == 1
        assert proposal3.response_body["data"][0]["id"] == "in_inv002"


# ===================================================================
# Dispute CRUD
# ===================================================================


class TestDisputeActions:
    async def test_get_dispute(self, payments_pack, sample_state):
        """get_dispute retrieves a single dispute."""
        proposal = await payments_pack.handle_action(
            ToolName("get_dispute"),
            {"id": "dp_disp001"},
            sample_state,
        )
        body = proposal.response_body
        assert body["id"] == "dp_disp001"
        assert body["object"] == "dispute"
        assert body["status"] == "needs_response"
        assert len(proposal.proposed_state_deltas) == 0

    async def test_get_dispute_not_found(self, payments_pack, sample_state):
        """get_dispute returns Stripe error for missing dispute."""
        proposal = await payments_pack.handle_action(
            ToolName("get_dispute"),
            {"id": "dp_ghost"},
            sample_state,
        )
        assert "error" in proposal.response_body
        assert "No such dispute" in proposal.response_body["error"]["message"]

    async def test_close_dispute(self, payments_pack, sample_state):
        """close_dispute transitions to lost (merchant accepts chargeback)."""
        proposal = await payments_pack.handle_action(
            ToolName("close_dispute"),
            {"id": "dp_disp001"},
            sample_state,
        )
        body = proposal.response_body
        assert body["id"] == "dp_disp001"
        assert body["status"] == "lost"
        assert body["object"] == "dispute"
        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.entity_type == "dispute"
        assert delta.operation == "update"
        assert delta.fields["status"] == "lost"
        assert delta.previous_fields["status"] == "needs_response"

    async def test_close_dispute_already_terminal(self, payments_pack, sample_state):
        """close_dispute fails for already-terminal dispute."""
        proposal = await payments_pack.handle_action(
            ToolName("close_dispute"),
            {"id": "dp_disp_closed"},
            sample_state,
        )
        assert "error" in proposal.response_body
        assert "cannot be closed" in proposal.response_body["error"]["message"]

    async def test_close_dispute_not_found(self, payments_pack, sample_state):
        """close_dispute fails for missing dispute."""
        proposal = await payments_pack.handle_action(
            ToolName("close_dispute"),
            {"id": "dp_ghost"},
            sample_state,
        )
        assert "error" in proposal.response_body

    async def test_list_disputes(self, payments_pack, sample_state):
        """list_disputes returns disputes with Stripe list format."""
        proposal = await payments_pack.handle_action(
            ToolName("list_disputes"),
            {},
            sample_state,
        )
        body = proposal.response_body
        assert body["object"] == "list"
        assert body["url"] == "/v1/disputes"
        assert len(body["data"]) == 2
        assert body["has_more"] is False

    async def test_update_dispute(self, payments_pack, sample_state):
        """update_dispute updates evidence and metadata."""
        evidence = {"customer_name": "Alice Smith", "product_description": "Widget"}
        proposal = await payments_pack.handle_action(
            ToolName("update_dispute"),
            {"id": "dp_disp001", "evidence": evidence, "metadata": {"key": "value"}},
            sample_state,
        )
        body = proposal.response_body
        assert body["id"] == "dp_disp001"
        assert body["evidence"] == evidence
        assert body["metadata"] == {"key": "value"}
        assert body["object"] == "dispute"
        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.entity_type == "dispute"
        assert delta.operation == "update"

    async def test_update_dispute_not_found(self, payments_pack, sample_state):
        """update_dispute returns error when dispute does not exist."""
        proposal = await payments_pack.handle_action(
            ToolName("update_dispute"),
            {"id": "dp_nonexistent"},
            sample_state,
        )
        assert "error" in proposal.response_body
        assert "No such dispute" in proposal.response_body["error"]["message"]


# ===================================================================
# P2: Stripe response format compliance
# ===================================================================


class TestStripeResponseFormat:
    """Verify all list and entity responses follow Stripe conventions."""

    async def test_list_responses_have_url_field(self, payments_pack, sample_state):
        """All list endpoints include url field."""
        list_tools = [
            ("list_payment_intents", "/v1/payment_intents"),
            ("list_customers", "/v1/customers"),
            ("list_refunds", "/v1/refunds"),
            ("list_invoices", "/v1/invoices"),
            ("list_disputes", "/v1/disputes"),
        ]
        for tool_name, expected_url in list_tools:
            proposal = await payments_pack.handle_action(ToolName(tool_name), {}, sample_state)
            body = proposal.response_body
            assert body["object"] == "list", f"{tool_name} missing object=list"
            assert body["url"] == expected_url, f"{tool_name} wrong url"
            assert "has_more" in body, f"{tool_name} missing has_more"
            assert "data" in body, f"{tool_name} missing data"

    async def test_error_format_standardized(self, payments_pack, sample_state):
        """Error responses follow Stripe format."""
        # Test various error-producing actions
        error_calls = [
            ("get_payment_intent", {"id": "nope"}),
            ("get_customer", {"id": "nope"}),
            ("get_charge", {"id": "nope"}),
            ("get_refund", {"id": "nope"}),
            ("get_invoice", {"id": "nope"}),
            ("get_dispute", {"id": "nope"}),
        ]
        for tool_name, params in error_calls:
            proposal = await payments_pack.handle_action(ToolName(tool_name), params, sample_state)
            body = proposal.response_body
            assert "error" in body, f"{tool_name} should return error"
            err = body["error"]
            assert "type" in err, f"{tool_name} error missing type"
            assert "message" in err, f"{tool_name} error missing message"
            assert err["type"] == "invalid_request_error"

    async def test_entity_responses_have_object_field(self, payments_pack, sample_state):
        """Single-entity GET responses include the object field."""
        # get_payment_intent
        p = await payments_pack.handle_action(
            ToolName("get_payment_intent"), {"id": "pi_intent001"}, sample_state
        )
        assert p.response_body["object"] == "payment_intent"

        # get_customer
        p = await payments_pack.handle_action(
            ToolName("get_customer"), {"id": "cus_existing001"}, sample_state
        )
        assert p.response_body["object"] == "customer"

        # get_charge
        p = await payments_pack.handle_action(
            ToolName("get_charge"), {"id": "ch_paid001"}, sample_state
        )
        assert p.response_body["object"] == "charge"

        # get_refund
        p = await payments_pack.handle_action(
            ToolName("get_refund"), {"id": "re_existing001"}, sample_state
        )
        assert p.response_body["object"] == "refund"

        # get_invoice
        p = await payments_pack.handle_action(
            ToolName("get_invoice"), {"id": "in_inv001"}, sample_state
        )
        assert p.response_body["object"] == "invoice"

        # get_dispute
        p = await payments_pack.handle_action(
            ToolName("get_dispute"), {"id": "dp_disp001"}, sample_state
        )
        assert p.response_body["object"] == "dispute"


# ===================================================================
# Schema and state machine validation
# ===================================================================


class TestPaymentsPackValidation:
    def test_schemas_validate(self, payments_pack):
        """Entity data matching the schemas passes SchemaValidator."""
        validator = SchemaValidator()
        schemas = payments_pack.get_entity_schemas()

        # Valid payment intent
        valid_pi = {
            "id": "pi_test001",
            "amount": 5000,
            "currency": "usd",
            "status": "succeeded",
            "created": 1700000000,
        }
        result = validator.validate_entity(valid_pi, schemas["payment_intent"])
        assert result.valid, f"PaymentIntent validation errors: {result.errors}"

        # Valid charge
        valid_charge = {
            "id": "ch_test001",
            "amount": 5000,
            "currency": "usd",
            "created": 1700000000,
        }
        result2 = validator.validate_entity(valid_charge, schemas["charge"])
        assert result2.valid, f"Charge validation errors: {result2.errors}"

        # Valid customer
        valid_customer = {
            "id": "cus_test001",
            "created": 1700000000,
        }
        result3 = validator.validate_entity(valid_customer, schemas["customer"])
        assert result3.valid, f"Customer validation errors: {result3.errors}"

        # Valid refund
        valid_refund = {
            "id": "re_test001",
            "amount": 2500,
            "charge": "ch_test001",
            "currency": "usd",
            "status": "pending",
            "created": 1700000000,
        }
        result4 = validator.validate_entity(valid_refund, schemas["refund"])
        assert result4.valid, f"Refund validation errors: {result4.errors}"

    def test_invoice_schema_validates(self, payments_pack):
        """Invoice entity data passes SchemaValidator."""
        validator = SchemaValidator()
        schemas = payments_pack.get_entity_schemas()
        valid_invoice = {
            "id": "in_test001",
            "customer": "cus_test001",
            "currency": "usd",
            "status": "draft",
            "created": 1700000000,
        }
        result = validator.validate_entity(valid_invoice, schemas["invoice"])
        assert result.valid, f"Invoice validation errors: {result.errors}"

    def test_dispute_schema_validates(self, payments_pack):
        """Dispute entity data passes SchemaValidator."""
        validator = SchemaValidator()
        schemas = payments_pack.get_entity_schemas()
        valid_dispute = {
            "id": "dp_test001",
            "charge": "ch_test001",
            "amount": 5000,
            "currency": "usd",
            "status": "needs_response",
            "created": 1700000000,
        }
        result = validator.validate_entity(valid_dispute, schemas["dispute"])
        assert result.valid, f"Dispute validation errors: {result.errors}"

    def test_payment_intent_state_machine(self, payments_pack):
        """Valid payment intent transitions pass StateMachineValidator."""
        sm_validator = StateMachineValidator()
        sm = payments_pack.get_state_machines()["payment_intent"]

        # requires_payment_method -> requires_confirmation is valid
        result = sm_validator.validate_transition(
            "requires_payment_method", "requires_confirmation", sm
        )
        assert result.valid

        # processing -> succeeded is valid
        result2 = sm_validator.validate_transition("processing", "succeeded", sm)
        assert result2.valid

        # succeeded -> requires_payment_method is NOT valid (terminal state)
        result3 = sm_validator.validate_transition("succeeded", "requires_payment_method", sm)
        assert not result3.valid

    def test_refund_state_machine(self, payments_pack):
        """Valid refund transitions pass StateMachineValidator."""
        sm_validator = StateMachineValidator()
        sm = payments_pack.get_state_machines()["refund"]

        result = sm_validator.validate_transition("pending", "succeeded", sm)
        assert result.valid

        result2 = sm_validator.validate_transition("pending", "failed", sm)
        assert result2.valid

        result3 = sm_validator.validate_transition("succeeded", "pending", sm)
        assert not result3.valid

        result4 = sm_validator.validate_transition("failed", "pending", sm)
        assert not result4.valid

    def test_invoice_state_machine(self, payments_pack):
        """Invoice state machine transitions are valid."""
        sm_validator = StateMachineValidator()
        sm = payments_pack.get_state_machines()["invoice"]

        # draft -> open is valid (finalize)
        assert sm_validator.validate_transition("draft", "open", sm).valid
        # open -> paid is valid
        assert sm_validator.validate_transition("open", "paid", sm).valid
        # draft -> void is valid
        assert sm_validator.validate_transition("draft", "void", sm).valid
        # open -> uncollectible is valid
        assert sm_validator.validate_transition("open", "uncollectible", sm).valid
        # paid is terminal
        assert not sm_validator.validate_transition("paid", "draft", sm).valid
        # void is terminal
        assert not sm_validator.validate_transition("void", "open", sm).valid

    def test_dispute_state_machine(self, payments_pack):
        """Dispute state machine transitions are valid."""
        sm_validator = StateMachineValidator()
        sm = payments_pack.get_state_machines()["dispute"]

        assert sm_validator.validate_transition(
            "warning_needs_response", "warning_under_review", sm
        ).valid
        assert sm_validator.validate_transition("warning_under_review", "warning_closed", sm).valid
        assert sm_validator.validate_transition("needs_response", "under_review", sm).valid
        assert sm_validator.validate_transition("under_review", "won", sm).valid
        assert sm_validator.validate_transition("under_review", "lost", sm).valid
        # Terminal states
        assert not sm_validator.validate_transition("won", "lost", sm).valid
        assert not sm_validator.validate_transition("lost", "won", sm).valid
        assert not sm_validator.validate_transition(
            "warning_closed", "warning_needs_response", sm
        ).valid
