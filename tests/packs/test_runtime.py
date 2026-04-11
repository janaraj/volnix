"""Tests for volnix.packs.runtime — PackRuntime with generic MockPack (never EmailPack).

Key framework enforcement tests prove that bypassing the runtime loses
validation and fidelity tagging.
"""

import pytest

from volnix.core.context import ResponseProposal
from volnix.core.errors import PackNotFoundError, ValidationError
from volnix.core.types import (
    EntityId,
    FidelityMetadata,
    FidelitySource,
    FidelityTier,
    StateDelta,
    ToolName,
)
from volnix.packs.base import ServicePack
from volnix.packs.registry import PackRegistry
from volnix.packs.runtime import PackRuntime

# ---------------------------------------------------------------------------
# MockPack variants
# ---------------------------------------------------------------------------


class MockPack(ServicePack):
    """Basic mock pack with one tool and a simple entity schema."""

    pack_name = "mock"
    category = "test_category"
    fidelity_tier = 1

    def get_tools(self):
        return [
            {
                "name": "mock_action",
                "description": "A mock action",
                "parameters": {
                    "type": "object",
                    "required": ["x"],
                    "properties": {
                        "x": {"type": "integer"},
                    },
                },
            },
            {
                "name": "mock_read",
                "description": "A read-only mock action (no deltas)",
                "parameters": {
                    "type": "object",
                    "required": [],
                    "properties": {},
                },
            },
        ]

    def get_entity_schemas(self):
        return {
            "mock_entity": {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}},
            },
        }

    def get_state_machines(self):
        return {
            "mock_entity": {
                "transitions": {
                    "new": ["active", "deleted"],
                    "active": ["archived", "deleted"],
                    "archived": ["active", "deleted"],
                    "deleted": [],
                },
            },
        }

    async def handle_action(self, action, input_data, state):
        if str(action) == "mock_read":
            return ResponseProposal(response_body={"items": []})
        return ResponseProposal(
            response_body={"result": "ok"},
            proposed_state_deltas=[
                StateDelta(
                    entity_type="mock_entity",
                    entity_id=EntityId("me-001"),
                    operation="create",
                    fields={"name": "test-entity", "status": "new"},
                ),
            ],
        )


class MockPackBadEntity(ServicePack):
    """Returns a create delta with missing required fields."""

    pack_name = "bad_entity"
    category = "test_category"
    fidelity_tier = 1

    def get_tools(self):
        return [
            {
                "name": "bad_create",
                "description": "Creates invalid entity data",
                "parameters": {
                    "type": "object",
                    "required": [],
                    "properties": {},
                },
            },
        ]

    def get_entity_schemas(self):
        return {
            "strict_entity": {
                "type": "object",
                "required": ["name", "code"],
                "properties": {
                    "name": {"type": "string"},
                    "code": {"type": "integer"},
                },
            },
        }

    def get_state_machines(self):
        return {}

    async def handle_action(self, action, input_data, state):
        # Deliberately missing required "code" field
        return ResponseProposal(
            response_body={"result": "created"},
            proposed_state_deltas=[
                StateDelta(
                    entity_type="strict_entity",
                    entity_id=EntityId("se-001"),
                    operation="create",
                    fields={"name": "incomplete"},
                ),
            ],
        )


class MockPackPretagged(ServicePack):
    """Pack that sets its own FidelityMetadata on the response."""

    pack_name = "pretagged"
    category = "test_category"
    fidelity_tier = 1

    def get_tools(self):
        return [{"name": "pretagged_action", "description": "Pre-tagged"}]

    def get_entity_schemas(self):
        return {}

    def get_state_machines(self):
        return {}

    async def handle_action(self, action, input_data, state):
        return ResponseProposal(
            response_body={"status": "ok"},
            fidelity=FidelityMetadata(
                tier=FidelityTier.VERIFIED,
                source="custom_source",
                fidelity_source=FidelitySource.VERIFIED_PACK,
                deterministic=False,
                replay_stable=False,
                benchmark_grade=False,
            ),
        )


class MockPackInvalidTransition(ServicePack):
    """Pack that produces an invalid state transition in its output."""

    pack_name = "invalid_transition"
    category = "test_category"
    fidelity_tier = 1

    def get_tools(self):
        return [{"name": "invalid_trans_action", "description": "Bad transition"}]

    def get_entity_schemas(self):
        return {
            "ordered_entity": {
                "type": "object",
                "required": ["status"],
                "properties": {"status": {"type": "string"}},
            },
        }

    def get_state_machines(self):
        return {
            "ordered_entity": {
                "transitions": {
                    "open": ["in_progress", "closed"],
                    "in_progress": ["closed"],
                    "closed": [],
                },
            },
        }

    async def handle_action(self, action, input_data, state):
        # Attempt to go from "closed" back to "open" — not allowed
        return ResponseProposal(
            response_body={"result": "transitioned"},
            proposed_state_deltas=[
                StateDelta(
                    entity_type="ordered_entity",
                    entity_id=EntityId("oe-001"),
                    operation="update",
                    fields={"status": "open"},
                    previous_fields={"status": "closed"},
                ),
            ],
        )


# ---------------------------------------------------------------------------
# Helper to build a registry + runtime quickly
# ---------------------------------------------------------------------------


def _make_runtime(*packs: ServicePack) -> PackRuntime:
    registry = PackRegistry()
    for p in packs:
        registry.register(p)
    return PackRuntime(registry)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPackRuntime:
    @pytest.mark.asyncio
    async def test_execute_valid(self):
        """Valid execution returns a ResponseProposal with correct body."""
        runtime = _make_runtime(MockPack())
        proposal = await runtime.execute("mock_action", {"x": 1})
        assert proposal.response_body["result"] == "ok"
        assert len(proposal.proposed_state_deltas) == 1

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        """Unknown tool raises PackNotFoundError."""
        runtime = _make_runtime(MockPack())
        with pytest.raises(PackNotFoundError, match="no_such_tool"):
            await runtime.execute("no_such_tool", {})

    @pytest.mark.asyncio
    async def test_execute_tags_fidelity(self):
        """Runtime.execute always tags FidelityMetadata on proposals that lack it."""
        runtime = _make_runtime(MockPack())
        proposal = await runtime.execute("mock_action", {"x": 1})
        assert proposal.fidelity is not None
        assert proposal.fidelity.tier == FidelityTier.VERIFIED
        assert proposal.fidelity.deterministic is True

    @pytest.mark.asyncio
    async def test_execute_preserves_existing_fidelity(self):
        """Runtime does not overwrite FidelityMetadata already set by pack."""
        runtime = _make_runtime(MockPackPretagged())
        proposal = await runtime.execute("pretagged_action", {})
        assert proposal.fidelity is not None
        assert proposal.fidelity.source == "custom_source"
        assert proposal.fidelity.deterministic is False

    @pytest.mark.asyncio
    async def test_execute_validates_input_schema(self):
        """Bad input (missing required field) raises ValidationError."""
        runtime = _make_runtime(MockPack())
        with pytest.raises(ValidationError, match="Input validation failed"):
            await runtime.execute("mock_action", {})  # missing "x"

    @pytest.mark.asyncio
    async def test_execute_validates_entity_deltas(self):
        """Bad entity data in output raises ValidationError."""
        runtime = _make_runtime(MockPackBadEntity())
        with pytest.raises(ValidationError, match="Entity schema validation failed"):
            await runtime.execute("bad_create", {})

    @pytest.mark.asyncio
    async def test_execute_validates_transitions(self):
        """Invalid state transition in output raises ValidationError."""
        runtime = _make_runtime(MockPackInvalidTransition())
        with pytest.raises(ValidationError, match="State transition invalid"):
            await runtime.execute("invalid_trans_action", {})

    @pytest.mark.asyncio
    async def test_execute_valid_create_initial_state(self):
        """New entity with valid initial state passes validation."""
        runtime = _make_runtime(MockPack())
        proposal = await runtime.execute("mock_action", {"x": 42})
        # "new" is a valid state in mock_entity's state machine
        delta = proposal.proposed_state_deltas[0]
        assert delta.fields["status"] == "new"

    @pytest.mark.asyncio
    async def test_execute_read_only_no_deltas(self):
        """Action with no deltas passes cleanly (no validation errors)."""
        runtime = _make_runtime(MockPack())
        proposal = await runtime.execute("mock_read", {})
        assert proposal.response_body == {"items": []}
        assert proposal.proposed_state_deltas == []
        assert proposal.fidelity is not None

    @pytest.mark.asyncio
    async def test_bypass_direct_call_lacks_fidelity(self):
        """Calling pack.handle_action directly produces NO FidelityMetadata."""
        pack = MockPack()
        proposal = await pack.handle_action(ToolName("mock_action"), {"x": 1}, {})
        assert proposal.fidelity is None  # No tagging without runtime

    @pytest.mark.asyncio
    async def test_runtime_always_tags_fidelity(self):
        """Runtime.execute always tags FidelityMetadata (contrast with direct call)."""
        registry = PackRegistry()
        registry.register(MockPack())
        runtime = PackRuntime(registry)
        proposal = await runtime.execute("mock_action", {"x": 1})
        assert proposal.fidelity is not None
        assert proposal.fidelity.tier == FidelityTier.VERIFIED

    @pytest.mark.asyncio
    async def test_runtime_rejects_what_direct_accepts(self):
        """Runtime rejects bad entity data that pack.handle_action would accept.

        Proves framework enforcement: direct call bypasses validation,
        but runtime catches the error.
        """
        pack = MockPackBadEntity()
        # Direct call succeeds — no validation
        direct_proposal = await pack.handle_action(ToolName("bad_create"), {}, {})
        assert direct_proposal.response_body["result"] == "created"

        # Runtime catches the invalid entity
        runtime = _make_runtime(MockPackBadEntity())
        with pytest.raises(ValidationError, match="Entity schema validation failed"):
            await runtime.execute("bad_create", {})


# ---------------------------------------------------------------------------
# Pipeline plumbing — actor_id injection (Cycle B.4)
# ---------------------------------------------------------------------------


class _ActorCapturePack(ServicePack):
    """Mock pack that records the ``_actor_id`` it received in input_data.

    Used by ``TestActorIdPlumbing`` to verify the Cycle B.4 plumbing
    change that ``PackRuntime.execute`` injects the pipeline-level
    actor_id into ``input_data["_actor_id"]`` after schema validation.
    """

    pack_name = "actor_capture"
    category = "test_category"
    fidelity_tier = 1
    last_seen_actor_id: str | None = None
    last_seen_input_keys: tuple[str, ...] = ()

    def get_tools(self):
        return [
            {
                "name": "capture",
                "description": "Records the actor_id for verification",
                "parameters": {
                    "type": "object",
                    "required": ["x"],
                    "properties": {"x": {"type": "integer"}},
                },
            },
        ]

    def get_entity_schemas(self):
        return {}

    def get_state_machines(self):
        return {}

    async def handle_action(self, action, input_data, state):
        type(self).last_seen_actor_id = input_data.get("_actor_id")
        type(self).last_seen_input_keys = tuple(sorted(input_data.keys()))
        return ResponseProposal(response_body={"ok": True})


class TestActorIdPlumbing:
    """End-to-end verification of the Cycle B.4 actor_id plumbing.

    The plumbing lives in two places:
    - ``volnix/packs/runtime.py``: ``PackRuntime.execute`` accepts an
      optional ``actor_id`` kwarg and injects it into ``input_data``
      as ``"_actor_id"`` AFTER tool-schema validation (so the
      underscore-prefixed key doesn't trip the validator).
    - ``volnix/engines/responder/tier1.py``: ``Tier1Dispatcher.dispatch``
      passes ``ctx.actor_id`` through to ``runtime.execute``.

    These tests exercise the runtime half directly (the tier1 half is
    a 1-line passthrough that's verified by the existing agency
    integration tests).
    """

    @pytest.mark.asyncio
    async def test_actor_id_is_injected_into_input_data(self):
        """When ``actor_id`` is passed to execute, handlers see it."""
        runtime = _make_runtime(_ActorCapturePack())
        await runtime.execute(
            action="capture",
            input_data={"x": 1},
            actor_id="dana-abc123",
        )
        assert _ActorCapturePack.last_seen_actor_id == "dana-abc123"

    @pytest.mark.asyncio
    async def test_actor_id_is_absent_when_not_passed(self):
        """Backward compat: handlers that don't need actor_id never see ``_actor_id``."""
        _ActorCapturePack.last_seen_actor_id = "UNSET"
        runtime = _make_runtime(_ActorCapturePack())
        await runtime.execute(
            action="capture",
            input_data={"x": 1},
        )
        assert _ActorCapturePack.last_seen_actor_id is None

    @pytest.mark.asyncio
    async def test_underscore_prefixed_key_bypasses_schema_validation(self):
        """``_actor_id`` is injected AFTER schema validation.

        The tool schema in ``_ActorCapturePack`` only declares ``x`` as a
        required property. If ``_actor_id`` were injected BEFORE
        validation, the schema validator could reject it (with strict
        ``additionalProperties: false`` schemas). By injecting after,
        the validator never sees the underscore key. We verify this by
        calling with a valid input and asserting both keys end up in
        the handler's input_data.
        """
        runtime = _make_runtime(_ActorCapturePack())
        await runtime.execute(
            action="capture",
            input_data={"x": 42},
            actor_id="buyer-001",
        )
        # Handler saw both the user key and the pipeline-injected key
        assert "x" in _ActorCapturePack.last_seen_input_keys
        assert "_actor_id" in _ActorCapturePack.last_seen_input_keys

    @pytest.mark.asyncio
    async def test_actor_id_does_not_leak_between_calls(self):
        """Each execute call sees its own actor_id, not a stale one from prior."""
        runtime = _make_runtime(_ActorCapturePack())
        await runtime.execute(action="capture", input_data={"x": 1}, actor_id="first-actor")
        assert _ActorCapturePack.last_seen_actor_id == "first-actor"
        await runtime.execute(action="capture", input_data={"x": 2}, actor_id="second-actor")
        assert _ActorCapturePack.last_seen_actor_id == "second-actor"
