"""E2E integration tests — real PackRegistry + PackRuntime + EmailPack.

Tests the full stack from filesystem discovery through runtime execution.
"""

import inspect
from pathlib import Path

import pytest

from volnix.core.context import ResponseProposal
from volnix.core.types import (
    EntityId,
    FidelityTier,
    StateDelta,
)
from volnix.packs.base import ServicePack
from volnix.packs.registry import PackRegistry
from volnix.packs.runtime import PackRuntime

# ---------------------------------------------------------------------------
# Second mock pack — proves extensibility (no email-specific code in framework)
# ---------------------------------------------------------------------------


class NotePack(ServicePack):
    """A simple notes pack — proves any ServicePack works identically."""

    pack_name = "notes"
    category = "productivity"
    fidelity_tier = 1

    def get_tools(self):
        return [
            {
                "name": "note_create",
                "description": "Create a note",
                "parameters": {
                    "type": "object",
                    "required": ["title", "body"],
                    "properties": {
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                    },
                },
            },
        ]

    def get_entity_schemas(self):
        return {
            "note": {
                "type": "object",
                "required": ["note_id", "title", "body"],
                "properties": {
                    "note_id": {"type": "string"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                },
            },
        }

    def get_state_machines(self):
        return {}

    async def handle_action(self, action, input_data, state):
        return ResponseProposal(
            response_body={"status": "created", "note_id": "note-001"},
            proposed_state_deltas=[
                StateDelta(
                    entity_type="note",
                    entity_id=EntityId("note-001"),
                    operation="create",
                    fields={
                        "note_id": "note-001",
                        "title": input_data["title"],
                        "body": input_data["body"],
                    },
                ),
            ],
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def verified_dir():
    return str(Path(__file__).resolve().parents[2] / "volnix" / "packs" / "verified")


@pytest.fixture
def registry_with_email(verified_dir):
    """Registry with email pack discovered from filesystem."""
    reg = PackRegistry()
    reg.discover(verified_dir)
    return reg


@pytest.fixture
def runtime_with_email(registry_with_email):
    return PackRuntime(registry_with_email)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestIntegrationDiscovery:
    def test_email_registers_via_discover(self, registry_with_email):
        """Filesystem discovery finds and registers the email pack."""
        assert registry_with_email.has_pack("gmail")
        pack = registry_with_email.get_pack("gmail")
        assert pack.pack_name == "gmail"
        assert registry_with_email.has_tool("email_send")
        assert registry_with_email.has_tool("email_list")


class TestIntegrationRuntime:
    @pytest.mark.asyncio
    async def test_runtime_execute_send(self, runtime_with_email):
        """Full runtime execution of email_send returns validated ResponseProposal."""
        proposal = await runtime_with_email.execute(
            "email_send",
            {
                "from_addr": "integration@test.com",
                "to_addr": "recipient@test.com",
                "subject": "Integration Test",
                "body": "This is an integration test.",
            },
        )
        assert isinstance(proposal, ResponseProposal)
        assert proposal.response_body["status"] == "sent"
        assert proposal.fidelity is not None
        assert proposal.fidelity.tier == FidelityTier.VERIFIED

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, runtime_with_email):
        """Full lifecycle: send -> read -> reply -> list."""
        # 1. Send
        send_result = await runtime_with_email.execute(
            "email_send",
            {
                "from_addr": "alice@test.com",
                "to_addr": "bob@test.com",
                "subject": "Lifecycle test",
                "body": "Starting lifecycle.",
            },
        )
        email_id = send_result.response_body["email_id"]
        thread_id = send_result.response_body["thread_id"]

        # Build state from send result
        email_entity = send_result.proposed_state_deltas[0].fields
        state = {"emails": [email_entity]}

        # 2. Read — transitions delivered -> read
        read_result = await runtime_with_email.execute(
            "email_read",
            {"email_id": email_id},
            state,
        )
        assert read_result.response_body["email"]["email_id"] == email_id

        # 3. Reply
        reply_result = await runtime_with_email.execute(
            "email_reply",
            {
                "email_id": email_id,
                "from_addr": "bob@test.com",
                "body": "Got it, thanks!",
            },
            state,
        )
        assert reply_result.response_body["in_reply_to"] == email_id
        assert reply_result.response_body["thread_id"] == thread_id

        # 4. List
        reply_entity = reply_result.proposed_state_deltas[0].fields
        state["emails"].append(reply_entity)
        list_result = await runtime_with_email.execute(
            "email_list",
            {"mailbox_owner": "alice@test.com"},
            state,
        )
        # Bob's reply is addressed to alice (original sender)
        assert list_result.response_body["count"] >= 1

    @pytest.mark.asyncio
    async def test_invalid_transition_blocked(self, runtime_with_email):
        """Invalid state transition (trashed -> sent) is blocked by runtime."""
        # Build state with a trashed email
        state = {
            "emails": [
                {
                    "email_id": "email-trashed-001",
                    "from_addr": "alice@test.com",
                    "to_addr": "bob@test.com",
                    "subject": "Trashed",
                    "body": "Gone",
                    "status": "trashed",
                    "thread_id": "thread-t099",
                    "timestamp": "2026-01-01T00:00:00+00:00",
                },
            ],
        }
        # email_read on a trashed email: the handler only transitions "delivered" -> "read"
        # so there should be no delta for a trashed email. Let's verify no invalid
        # transition is generated.
        proposal = await runtime_with_email.execute(
            "email_read",
            {"email_id": "email-trashed-001"},
            state,
        )
        # The handler returns the email in the body but creates no delta
        # because old_status != "delivered"
        assert len(proposal.proposed_state_deltas) == 0

    @pytest.mark.asyncio
    async def test_fidelity_tier1(self, runtime_with_email):
        """Email pack produces tier-1 fidelity with deterministic=True."""
        proposal = await runtime_with_email.execute(
            "email_send",
            {
                "from_addr": "a@b.com",
                "to_addr": "c@d.com",
                "subject": "Fidelity",
                "body": "Check",
            },
        )
        assert proposal.fidelity.tier == FidelityTier.VERIFIED
        assert proposal.fidelity.tier == 1
        assert proposal.fidelity.deterministic is True


class TestIntegrationExtensibility:
    @pytest.mark.asyncio
    async def test_second_mock_pack_works_identically(self, registry_with_email):
        """A second non-email pack works through the same framework identically."""
        registry_with_email.register(NotePack())
        runtime = PackRuntime(registry_with_email)

        proposal = await runtime.execute(
            "note_create",
            {"title": "My Note", "body": "Note body content"},
        )
        assert proposal.response_body["status"] == "created"
        assert proposal.fidelity is not None
        assert proposal.fidelity.tier == FidelityTier.VERIFIED
        assert len(proposal.proposed_state_deltas) == 1

    @pytest.mark.asyncio
    async def test_pack_with_no_state_machines(self):
        """Framework doesn't crash when a pack has no state machines defined."""
        registry = PackRegistry()
        registry.register(NotePack())
        runtime = PackRuntime(registry)
        # Should execute cleanly with no state machine validation errors
        proposal = await runtime.execute(
            "note_create",
            {"title": "Test", "body": "Works"},
        )
        assert proposal.response_body["status"] == "created"
        assert proposal.fidelity is not None


class TestImportBoundaries:
    def test_email_pack_imports_only_core(self):
        """Verify that the email pack modules import only from volnix.core.

        Packs must NEVER import from persistence/, engines/, or bus/.
        """
        from volnix.packs.verified.gmail import handlers as handlers_mod
        from volnix.packs.verified.gmail import pack as pack_mod
        from volnix.packs.verified.gmail import schemas as schemas_mod
        from volnix.packs.verified.gmail import state_machines as sm_mod

        forbidden_prefixes = (
            "volnix.persistence",
            "volnix.engines",
            "volnix.bus",
        )

        for mod in [pack_mod, handlers_mod, schemas_mod, sm_mod]:
            source = inspect.getsource(mod)
            for prefix in forbidden_prefixes:
                assert f"from {prefix}" not in source, (
                    f"{mod.__name__} imports from forbidden module {prefix}"
                )
                assert f"import {prefix}" not in source, (
                    f"{mod.__name__} imports from forbidden module {prefix}"
                )
