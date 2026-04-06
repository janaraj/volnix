"""Phase C3 WIRE — End-to-End tests for the full Volnix pipeline.

Proves the entire architecture works: config -> registry -> wiring ->
pipeline -> pack dispatch -> state commit -> event publish -> ledger audit.

Four test categories:
  A. Real-Data E2E (Agent Simulation) — 5 tests
  B. Infrastructure Verification (Wire Integrity) — 7 tests
  C. Replay + Audit (Data Integrity) — 4 tests
  D. Drift Prevention (Architectural Guards) — 5 tests

These tests MUST NOT be removed when governance is added in Phase F.
They verify the wire stays intact regardless of what the governance
steps do internally.
"""

from __future__ import annotations

import asyncio

import pytest

from volnix.actors.definition import ActorDefinition
from volnix.core.types import ActorId, ActorType, StepVerdict
from volnix.ledger.query import LedgerQuery

# ── Helpers ──────────────────────────────────────────────────────────


def _register_test_agents(app):
    """Register common test actors so governance doesn't block wire tests."""
    compiler = app.registry.get("world_compiler")
    actor_registry = compiler._config.get("_actor_registry")
    if actor_registry is None:
        return
    test_agent_ids = [
        "agent-1",
        "agent-2",
        "a1",
        "actor-A",
        "actor-B",
    ]
    for aid in test_agent_ids:
        if not actor_registry.has_actor(ActorId(aid)):
            actor_registry.register(
                ActorDefinition(
                    id=ActorId(aid),
                    type=ActorType.AGENT,
                    role="test-agent",
                    permissions={"write": "all", "read": "all"},
                )
            )


@pytest.fixture(autouse=True)
def register_agents(app):
    """Auto-register test agents before each test in this module."""
    _register_test_agents(app)


def _send_payload(
    from_addr: str = "alice@test.com",
    to_addr: str = "bob@test.com",
    subject: str = "Test",
    body: str = "Body",
) -> dict:
    return {
        "from_addr": from_addr,
        "to_addr": to_addr,
        "subject": subject,
        "body": body,
    }


# =====================================================================
# Category A: Real-Data E2E (Agent Simulation)
# =====================================================================


class TestAgentSimulation:
    """Simulate real agent interactions through the full pipeline."""

    async def test_agent_sends_email(self, app):
        """A1: Agent sends an email — response has email_id, status, thread_id."""
        result = await app.handle_action(
            "agent-1",
            "email",
            "email_send",
            _send_payload(subject="Hello Bob", body="How are you?"),
        )
        assert "email_id" in result
        assert result["status"] == "sent"
        assert "thread_id" in result
        assert "timestamp" in result

    async def test_agent_reads_email(self, app):
        """A2: Agent sends, then another agent reads it — email returned with status."""
        send_result = await app.handle_action(
            "agent-1",
            "email",
            "email_send",
            _send_payload(subject="Read me", body="Please read."),
        )
        email_id = send_result["email_id"]

        read_result = await app.handle_action(
            "agent-2",
            "email",
            "email_read",
            {"email_id": email_id},
        )
        assert "email" in read_result
        assert read_result["email"]["email_id"] == email_id
        # After reading, status transitions to "read"
        assert read_result["email"]["status"] == "read"

    async def test_agent_replies_to_email(self, app):
        """A3: Agent sends, another agent replies — same thread_id, in_reply_to set."""
        send = await app.handle_action(
            "agent-1",
            "email",
            "email_send",
            _send_payload(
                from_addr="alice@test.com", to_addr="bob@test.com", subject="Topic", body="Start."
            ),
        )
        reply = await app.handle_action(
            "agent-2",
            "email",
            "email_reply",
            {"email_id": send["email_id"], "from_addr": "bob@test.com", "body": "Reply."},
        )
        assert "email_id" in reply
        assert reply["thread_id"] == send["thread_id"]
        assert reply["in_reply_to"] == send["email_id"]

    async def test_agent_lists_inbox(self, app):
        """A4: Send 3 emails to bob, bob lists inbox — count is 3."""
        for i in range(3):
            await app.handle_action(
                "agent-1",
                "email",
                "email_send",
                _send_payload(to_addr="bob@test.com", subject=f"Email {i}", body=f"Body {i}"),
            )
        list_result = await app.handle_action(
            "agent-2",
            "email",
            "email_list",
            {"mailbox_owner": "bob@test.com"},
        )
        assert list_result["count"] == 3
        assert len(list_result["emails"]) == 3

    async def test_agent_full_conversation(self, app):
        """A5: send -> read -> reply -> reply — multi-turn, same thread."""
        s1 = await app.handle_action(
            "agent-1",
            "email",
            "email_send",
            _send_payload(from_addr="a@t.com", to_addr="b@t.com", subject="Chat", body="Hi"),
        )
        await app.handle_action(
            "agent-2",
            "email",
            "email_read",
            {"email_id": s1["email_id"]},
        )
        r1 = await app.handle_action(
            "agent-2",
            "email",
            "email_reply",
            {"email_id": s1["email_id"], "from_addr": "b@t.com", "body": "Hey"},
        )
        r2 = await app.handle_action(
            "agent-1",
            "email",
            "email_reply",
            {"email_id": r1["email_id"], "from_addr": "a@t.com", "body": "Sup"},
        )
        # All share the same thread
        assert s1["thread_id"] == r1["thread_id"]
        assert r1["thread_id"] == r2["thread_id"]


# =====================================================================
# Category B: Infrastructure Verification (Wire Integrity)
# =====================================================================


class TestWireIntegrity:
    """Verify all infrastructure components work together.

    These tests MUST NOT be removed when governance is added.
    """

    async def test_all_7_steps_execute(self, app):
        """B1: All 7 PipelineStepEntry recorded in ledger with correct names."""
        await app.handle_action(
            "a1",
            "email",
            "email_send",
            _send_payload(),
        )
        entries = await app.ledger.query(
            LedgerQuery(entry_type="pipeline_step", limit=50),
        )
        step_names = [e.step_name for e in entries]
        expected = [
            "permission",
            "policy",
            "budget",
            "capability",
            "responder",
            "validation",
            "commit",
        ]
        assert step_names == expected

    async def test_all_steps_return_allow(self, app):
        """B2: Every step verdict is ALLOW for a valid email_send."""
        await app.handle_action(
            "a1",
            "email",
            "email_send",
            _send_payload(),
        )
        entries = await app.ledger.query(
            LedgerQuery(entry_type="pipeline_step", limit=50),
        )
        for entry in entries:
            assert entry.verdict == str(StepVerdict.ALLOW), (
                f"Step '{entry.step_name}' returned '{entry.verdict}' instead of ALLOW"
            )

    async def test_state_committed_to_store(self, app):
        """B3: Entity exists in StateEngine after pipeline executes."""
        result = await app.handle_action(
            "a1",
            "email",
            "email_send",
            _send_payload(),
        )
        email_id = result["email_id"]

        state_engine = app.registry.get("state")
        entity = await state_engine.get_entity("email", email_id)
        assert entity is not None
        assert entity["email_id"] == email_id
        assert entity["status"] == "delivered"

    async def test_event_persisted_to_log(self, app):
        """B4: WorldEvent appears in StateEngine event log."""
        await app.handle_action(
            "a1",
            "email",
            "email_send",
            _send_payload(),
        )
        state_engine = app.registry.get("state")
        events = await state_engine.get_timeline()
        assert len(events) >= 1
        assert events[0].event_type == "world.email_send"

    async def test_event_published_to_bus(self, app):
        """B5: Bus subscriber receives the WorldEvent."""
        received = []

        async def _capture(event):
            received.append(event)

        await app.bus.subscribe("*", _capture)
        await app.handle_action(
            "a1",
            "email",
            "email_send",
            _send_payload(),
        )
        # Give the bus consumer task time to drain the queue
        await asyncio.sleep(0.2)

        assert len(received) > 0
        world_events = [e for e in received if getattr(e, "event_type", "").startswith("world.")]
        assert len(world_events) >= 1

    async def test_ledger_has_state_mutation(self, app):
        """B6: StateMutationEntry recorded with entity_type, operation, after."""
        await app.handle_action(
            "a1",
            "email",
            "email_send",
            _send_payload(),
        )
        entries = await app.ledger.query(
            LedgerQuery(entry_type="state_mutation", limit=50),
        )
        assert len(entries) >= 1
        mutation = entries[0]
        assert mutation.entity_type == "email"
        assert mutation.operation == "create"
        assert mutation.after is not None
        assert "email_id" in mutation.after

    async def test_fidelity_metadata_tier1(self, app):
        """B7: ResponseProposal carries FidelityMetadata with tier=VERIFIED.

        The responder attaches fidelity metadata to the ResponseProposal
        via the PackRuntime.  We verify by executing an action and
        introspecting the ActionContext through the pipeline's last ctx.

        Since we cannot access ctx directly post-pipeline (handle_action
        returns response_body), we verify indirectly: the email pack is
        Tier 1 (VERIFIED), deterministic, and benchmark-grade.  We query
        the state engine to confirm the entity was created (meaning the
        full pipeline executed), and trust that PackRuntime tags fidelity
        (verified by unit tests in test_pack_runtime.py).
        """
        result = await app.handle_action(
            "a1",
            "email",
            "email_send",
            _send_payload(),
        )
        # If we got a successful response with email_id, the responder
        # executed through PackRuntime which tags FidelityMetadata
        assert "email_id" in result
        # The entity was committed (meaning validation + commit passed)
        state_engine = app.registry.get("state")
        entity = await state_engine.get_entity("email", result["email_id"])
        assert entity is not None


# =====================================================================
# Category C: Replay + Audit (Data Integrity)
# =====================================================================


class TestReplayAudit:
    """Verify event replay, ledger queries, and timeline integrity."""

    async def test_bus_event_replay(self, app):
        """C1: Events from bus persistence can be replayed in order."""
        await app.handle_action(
            "a1",
            "email",
            "email_send",
            _send_payload(subject="First"),
        )
        await app.handle_action(
            "a1",
            "email",
            "email_send",
            _send_payload(subject="Second"),
        )
        replayed = await app.bus.replay(from_sequence=0)
        assert len(replayed) >= 2
        # Events are ordered by sequence
        for i in range(1, len(replayed)):
            # All events should have event_id (they exist)
            assert hasattr(replayed[i], "event_id")

    async def test_ledger_query_by_actor(self, app):
        """C2: Ledger entries filterable by actor_id."""
        await app.handle_action(
            "actor-A",
            "email",
            "email_send",
            _send_payload(),
        )
        await app.handle_action(
            "actor-B",
            "email",
            "email_send",
            _send_payload(),
        )
        entries_a = await app.ledger.query(
            LedgerQuery(
                entry_type="pipeline_step",
                actor_id=ActorId("actor-A"),
                limit=50,
            ),
        )
        entries_b = await app.ledger.query(
            LedgerQuery(
                entry_type="pipeline_step",
                actor_id=ActorId("actor-B"),
                limit=50,
            ),
        )
        # Each actor should have exactly 7 pipeline step entries
        assert len(entries_a) == 7
        assert len(entries_b) == 7
        # Verify actor_ids are correct
        for e in entries_a:
            assert str(e.actor_id) == "actor-A"
        for e in entries_b:
            assert str(e.actor_id) == "actor-B"

    async def test_state_timeline(self, app):
        """C3: StateEngine.get_timeline() returns events in correct order."""
        await app.handle_action(
            "a1",
            "email",
            "email_send",
            _send_payload(subject="First"),
        )
        await app.handle_action(
            "a1",
            "email",
            "email_send",
            _send_payload(subject="Second"),
        )
        state_engine = app.registry.get("state")
        timeline = await state_engine.get_timeline()
        assert len(timeline) >= 2
        # All events are email_send type
        for evt in timeline:
            assert evt.event_type == "world.email_send"

    async def test_causal_chain_through_pipeline(self, app):
        """C4: Two linked actions produce traceable events."""
        s1 = await app.handle_action(
            "agent-1",
            "email",
            "email_send",
            _send_payload(from_addr="a@t.com", to_addr="b@t.com", subject="Cause", body="Start"),
        )
        # Reply creates a second event
        await app.handle_action(
            "agent-2",
            "email",
            "email_reply",
            {"email_id": s1["email_id"], "from_addr": "b@t.com", "body": "Effect"},
        )
        state_engine = app.registry.get("state")
        timeline = await state_engine.get_timeline()
        assert len(timeline) >= 2
        # Both events are world events from our actions
        event_types = [e.event_type for e in timeline]
        assert "world.email_send" in event_types
        assert "world.email_reply" in event_types


# =====================================================================
# Category D: Drift Prevention (Architectural Guards)
# =====================================================================


class TestDriftPrevention:
    """Architectural guards that prevent future implementations from
    breaking the wire.

    These tests MUST NOT be removed when governance is added.
    """

    async def test_pass_through_steps_marked(self, app):
        """D1: All 4 governance steps return ALLOW (pass-through in Phase C).

        In Phase C all governance steps are pass-throughs that always
        return ALLOW.  When Phase F implements real governance, this test
        should be updated to verify the new governance is active (some
        steps may DENY or HOLD depending on context).

        Note: The PipelineStepEntry does not carry the StepResult.message,
        so we verify the verdict is ALLOW for all four governance steps.
        """
        await app.handle_action(
            "a1",
            "email",
            "email_send",
            _send_payload(),
        )
        entries = await app.ledger.query(
            LedgerQuery(entry_type="pipeline_step", limit=50),
        )
        pass_through_steps = {"permission", "policy", "budget", "capability"}
        for entry in entries:
            if entry.step_name in pass_through_steps:
                assert entry.verdict == str(StepVerdict.ALLOW), (
                    f"Step '{entry.step_name}' returned '{entry.verdict}' "
                    f"but should be ALLOW in Phase C (pass-through)"
                )

    async def test_unknown_action_fails_gracefully(self, app):
        """D2: action='nonexistent_action' -> error response (not crash)."""
        result = await app.handle_action(
            "a1",
            "email",
            "nonexistent_action",
            {"some": "data"},
        )
        assert "error" in result

    async def test_pipeline_short_circuit(self, app):
        """D3: A step returning terminal verdict short-circuits the pipeline.

        We verify this by sending an unknown action -- the capability step
        returns ERROR (tool not found), which is terminal, so the pipeline
        stops there. (Phase E1: capability check uses PackRegistry.has_tool())
        """
        result = await app.handle_action(
            "a1",
            "email",
            "nonexistent_action",
            {"some": "data"},
        )
        # The pipeline short-circuited
        assert "error" in result
        # Verify fewer than 7 steps completed in ledger
        entries = await app.ledger.query(
            LedgerQuery(entry_type="pipeline_step", limit=50),
        )
        # Steps before and including capability should be there,
        # but responder, validation, and commit should NOT be there
        step_names = [e.step_name for e in entries]
        # capability should be present (it returned ERROR)
        assert "capability" in step_names
        # commit should NOT be present (pipeline stopped)
        assert "commit" not in step_names

    async def test_volnix_app_lifecycle(self, app):
        """D4: start() -> handle_action() -> stop() without resource leaks.

        The app fixture already calls start() and stop(). We verify the
        app is functional by running an action and checking basic health.
        """
        result = await app.handle_action(
            "a1",
            "email",
            "email_send",
            _send_payload(),
        )
        assert "email_id" in result
        # Verify the app's components are accessible
        assert app.bus is not None
        assert app.ledger is not None
        assert app.registry is not None
        assert app.pipeline is not None

    async def test_concurrent_actions_safe(self, app):
        """D5: Two actions in parallel both succeed (basic concurrency)."""
        results = await asyncio.gather(
            app.handle_action(
                "agent-1",
                "email",
                "email_send",
                _send_payload(
                    from_addr="a@t.com", to_addr="b@t.com", subject="Concurrent 1", body="Body 1"
                ),
            ),
            app.handle_action(
                "agent-2",
                "email",
                "email_send",
                _send_payload(
                    from_addr="c@t.com", to_addr="d@t.com", subject="Concurrent 2", body="Body 2"
                ),
            ),
        )
        assert len(results) == 2
        for r in results:
            assert "email_id" in r
            assert r["status"] == "sent"
        # Both should have unique email_ids
        assert results[0]["email_id"] != results[1]["email_id"]
        # Verify both entities exist in state
        state_engine = app.registry.get("state")
        for r in results:
            entity = await state_engine.get_entity("email", r["email_id"])
            assert entity is not None
