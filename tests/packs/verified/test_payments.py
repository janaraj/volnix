"""Tests for terrarium.packs.verified.payments — PaymentsPack through pack's own handle_action."""

import pytest

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.verified.payments.pack import PaymentsPack
from terrarium.validation.schema import SchemaValidator
from terrarium.validation.state_machine import StateMachineValidator


@pytest.fixture
def payments_pack():
    return PaymentsPack()


@pytest.fixture
def sample_state():
    """State with pre-existing charges, customers, payment intents, invoices, and disputes."""
    return {
        "customers": [
            {
                "id": "cus_existing001",
                "object": "customer",
                "name": "Alice Smith",
                "email": "alice@example.com",
                "balance": 0,
                "created": 1700000000,
            },
            {
                "id": "cus_existing002",
                "object": "customer",
                "name": "Bob Jones",
                "email": "bob@example.com",
                "balance": 0,
                "created": 1700000100,
            },
        ],
        "charges": [
            {
                "id": "ch_paid001",
                "amount": 5000,
                "currency": "usd",
                "customer": "cus_existing001",
                "paid": True,
                "captured": True,
                "refunded": False,
                "disputed": False,
                "payment_intent": "pi_intent001",
                "created": 1700001000,
            },
            {
                "id": "ch_unpaid002",
                "amount": 3000,
                "currency": "usd",
                "customer": "cus_existing002",
                "paid": False,
                "captured": False,
                "refunded": False,
                "disputed": False,
                "created": 1700001100,
            },
            {
                "id": "ch_small003",
                "amount": 1000,
                "currency": "eur",
                "customer": "cus_existing001",
                "paid": True,
                "captured": True,
                "refunded": False,
                "disputed": False,
                "created": 1700001200,
            },
        ],
        "payment_intents": [
            {
                "id": "pi_intent001",
                "amount": 5000,
                "currency": "usd",
                "status": "succeeded",
                "customer": "cus_existing001",
                "created": 1700000500,
            },
            {
                "id": "pi_intent002",
                "amount": 3000,
                "currency": "usd",
                "status": "requires_payment_method",
                "customer": "cus_existing002",
                "created": 1700000600,
            },
        ],
        "invoices": [
            {
                "id": "in_inv001",
                "object": "invoice",
                "customer": "cus_existing001",
                "status": "paid",
                "created": 1700002000,
            },
            {
                "id": "in_inv002",
                "object": "invoice",
                "customer": "cus_existing002",
                "status": "draft",
                "created": 1700002100,
            },
        ],
        "disputes": [
            {
                "id": "dp_disp001",
                "object": "dispute",
                "charge": "ch_paid001",
                "amount": 5000,
                "status": "needs_response",
                "evidence": None,
                "metadata": {},
                "created": 1700003000,
            },
        ],
    }


class TestPaymentsPackMetadata:
    def test_metadata(self, payments_pack):
        """pack_name, category, fidelity_tier are correct."""
        assert payments_pack.pack_name == "payments"
        assert payments_pack.category == "money"
        assert payments_pack.fidelity_tier == 1

    def test_tools_count_and_names(self, payments_pack):
        """PaymentsPack exposes 8 tools with expected names."""
        tools = payments_pack.get_tools()
        assert len(tools) == 8
        tool_names = {t["name"] for t in tools}
        assert tool_names == {
            "list_payment_intents",
            "create_customer",
            "list_customers",
            "create_refund",
            "list_invoices",
            "create_invoice",
            "list_disputes",
            "update_dispute",
        }

    def test_entity_schemas(self, payments_pack):
        """payment_intent, charge, customer, refund entity schemas are present."""
        schemas = payments_pack.get_entity_schemas()
        assert "payment_intent" in schemas
        assert "charge" in schemas
        assert "customer" in schemas
        assert "refund" in schemas

    def test_state_machines(self, payments_pack):
        """Payment intent and refund state machines are present."""
        sms = payments_pack.get_state_machines()
        assert "payment_intent" in sms
        assert "transitions" in sms["payment_intent"]
        assert "refund" in sms
        assert "transitions" in sms["refund"]
        # Verify key transitions
        pi_transitions = sms["payment_intent"]["transitions"]
        assert "succeeded" in pi_transitions["processing"]
        assert pi_transitions["succeeded"] == []  # terminal state


class TestPaymentsPackActions:
    async def test_create_customer(self, payments_pack):
        """create_customer creates entity with balance=0 and generated id."""
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
        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.entity_type == "customer"
        assert delta.operation == "create"

    async def test_list_customers(self, payments_pack, sample_state):
        """list_customers returns filtered customers."""
        # List all
        proposal = await payments_pack.handle_action(
            ToolName("list_customers"),
            {},
            sample_state,
        )
        body = proposal.response_body
        assert body["object"] == "list"
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

    async def test_list_payment_intents(self, payments_pack, sample_state):
        """list_payment_intents filters by customer and status."""
        # Filter by customer
        proposal = await payments_pack.handle_action(
            ToolName("list_payment_intents"),
            {"customer": "cus_existing001"},
            sample_state,
        )
        assert len(proposal.response_body["data"]) == 1
        assert proposal.response_body["data"][0]["id"] == "pi_intent001"

        # Filter by status
        proposal2 = await payments_pack.handle_action(
            ToolName("list_payment_intents"),
            {"status": "requires_payment_method"},
            sample_state,
        )
        assert len(proposal2.response_body["data"]) == 1
        assert proposal2.response_body["data"][0]["id"] == "pi_intent002"

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
        assert body["amount"] == 5000  # full charge amount
        assert body["charge"] == "ch_paid001"
        assert body["currency"] == "usd"
        assert body["status"] == "pending"

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

    async def test_create_invoice(self, payments_pack):
        """create_invoice creates a draft invoice."""
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
        assert len(proposal.proposed_state_deltas) == 1
        assert proposal.proposed_state_deltas[0].entity_type == "invoice"
        assert proposal.proposed_state_deltas[0].operation == "create"

    async def test_list_invoices(self, payments_pack, sample_state):
        """list_invoices filters by customer and status."""
        # All invoices
        proposal = await payments_pack.handle_action(
            ToolName("list_invoices"),
            {},
            sample_state,
        )
        assert len(proposal.response_body["data"]) == 2

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

    async def test_list_disputes(self, payments_pack, sample_state):
        """list_disputes returns disputes with Stripe list format."""
        proposal = await payments_pack.handle_action(
            ToolName("list_disputes"),
            {},
            sample_state,
        )
        body = proposal.response_body
        assert body["object"] == "list"
        assert len(body["data"]) == 1
        assert body["data"][0]["id"] == "dp_disp001"
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

        # pending -> succeeded is valid
        result = sm_validator.validate_transition("pending", "succeeded", sm)
        assert result.valid

        # pending -> failed is valid
        result2 = sm_validator.validate_transition("pending", "failed", sm)
        assert result2.valid

        # succeeded -> pending is NOT valid (terminal state)
        result3 = sm_validator.validate_transition("succeeded", "pending", sm)
        assert not result3.valid

        # failed -> pending is NOT valid (terminal state)
        result4 = sm_validator.validate_transition("failed", "pending", sm)
        assert not result4.valid
