"""Tests for GameActivePolicy — built-in policy gate.

Covers:
- Initial state is inactive (game_active=False)
- ``set_active`` flips the flag directly
- ``on_event`` recognizes ``GameActiveStateChangedEvent`` + ignores other events
- ``evaluate`` returns ALLOW for non-negotiate actions regardless of state
- ``evaluate`` returns ALLOW for negotiate actions when game is active
- ``evaluate`` returns DENY for negotiate actions when game is not active
- ``evaluate`` recognizes service-qualified actions (``game.negotiate_propose``)
- DENY returns a PolicyBlockEvent with the policy_id and run_id set
- Integration: PolicyEngine with a registered gate short-circuits on DENY
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from volnix.core.context import ActionContext
from volnix.core.events import Event, PolicyBlockEvent
from volnix.core.types import ActorId, RunId, ServiceId, StepVerdict, Timestamp
from volnix.engines.game.events import GameActiveStateChangedEvent
from volnix.engines.policy.builtin.game_active import GameActivePolicy
from volnix.engines.policy.engine import PolicyEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(
    action: str = "negotiate_propose",
    actor_id: str = "buyer-001",
    service_id: str = "game",
    run_id: str | None = "run-active-001",
    input_data: dict[str, Any] | None = None,
) -> ActionContext:
    return ActionContext(
        request_id=f"req-{action}",
        actor_id=ActorId(actor_id),
        service_id=ServiceId(service_id),
        action=action,
        input_data=input_data or {"deal_id": "deal-q3"},
        run_id=RunId(run_id) if run_id else None,
    )


def _make_state_event(active: bool, run_id: str = "run-001") -> GameActiveStateChangedEvent:
    now = datetime.now(UTC)
    return GameActiveStateChangedEvent(
        event_type="game.active_state_changed",
        timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
        active=active,
        run_id=run_id,
    )


def _make_unrelated_event(event_type: str = "slack.message") -> Event:
    now = datetime.now(UTC)
    return Event(
        event_type=event_type,
        timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
    )


# ---------------------------------------------------------------------------
# Initial state + set_active
# ---------------------------------------------------------------------------


class TestInitialState:
    """Gate starts inactive and provides a clean setter."""

    def test_starts_inactive(self):
        gate = GameActivePolicy()
        assert gate.is_active is False

    def test_set_active_true(self):
        gate = GameActivePolicy()
        gate.set_active(True)
        assert gate.is_active is True

    def test_set_active_false(self):
        gate = GameActivePolicy()
        gate.set_active(True)
        gate.set_active(False)
        assert gate.is_active is False

    def test_set_active_coerces_truthy(self):
        gate = GameActivePolicy()
        gate.set_active(1)  # type: ignore[arg-type]
        assert gate.is_active is True


# ---------------------------------------------------------------------------
# on_event bus callback
# ---------------------------------------------------------------------------


class TestOnEvent:
    """on_event recognizes GameActiveStateChangedEvent only."""

    @pytest.mark.asyncio
    async def test_on_game_active_event_flips_to_true(self):
        gate = GameActivePolicy()
        await gate.on_event(_make_state_event(active=True))
        assert gate.is_active is True

    @pytest.mark.asyncio
    async def test_on_game_inactive_event_flips_to_false(self):
        gate = GameActivePolicy()
        gate.set_active(True)
        await gate.on_event(_make_state_event(active=False))
        assert gate.is_active is False

    @pytest.mark.asyncio
    async def test_on_unrelated_event_is_noop(self):
        """Events that aren't game.active_state_changed are silently ignored."""
        gate = GameActivePolicy()
        gate.set_active(True)
        await gate.on_event(_make_unrelated_event("slack.chat.postMessage"))
        assert gate.is_active is True

    @pytest.mark.asyncio
    async def test_on_event_idempotent(self):
        """Receiving the same state twice is a clean noop."""
        gate = GameActivePolicy()
        await gate.on_event(_make_state_event(active=True))
        await gate.on_event(_make_state_event(active=True))
        assert gate.is_active is True


# ---------------------------------------------------------------------------
# evaluate — non-negotiate actions
# ---------------------------------------------------------------------------


class TestEvaluateNonNegotiateActions:
    """Non-negotiate actions always ALLOW regardless of flag."""

    @pytest.mark.asyncio
    async def test_slack_action_allows_when_inactive(self):
        gate = GameActivePolicy()
        ctx = _make_ctx(action="chat.postMessage", service_id="slack")
        result = await gate.evaluate(ctx)
        assert result.verdict == StepVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_slack_action_allows_when_active(self):
        gate = GameActivePolicy()
        gate.set_active(True)
        ctx = _make_ctx(action="chat.postMessage", service_id="slack")
        result = await gate.evaluate(ctx)
        assert result.verdict == StepVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_notion_retrieve_allows(self):
        gate = GameActivePolicy()
        ctx = _make_ctx(action="pages.retrieve", service_id="notion")
        result = await gate.evaluate(ctx)
        assert result.verdict == StepVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_empty_action_allows(self):
        gate = GameActivePolicy()
        ctx = _make_ctx(action="")
        result = await gate.evaluate(ctx)
        assert result.verdict == StepVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_action_not_starting_with_negotiate_allows(self):
        """Actions like ``renegotiate_terms`` do NOT match (prefix must be exact)."""
        gate = GameActivePolicy()
        ctx = _make_ctx(action="renegotiate_terms")
        result = await gate.evaluate(ctx)
        assert result.verdict == StepVerdict.ALLOW


# ---------------------------------------------------------------------------
# evaluate — negotiate actions
# ---------------------------------------------------------------------------


class TestEvaluateNegotiateActions:
    """Negotiate actions gate on the active flag."""

    @pytest.mark.asyncio
    async def test_negotiate_propose_denies_when_inactive(self):
        gate = GameActivePolicy()  # starts False
        ctx = _make_ctx(action="negotiate_propose")
        result = await gate.evaluate(ctx)
        assert result.verdict == StepVerdict.DENY

    @pytest.mark.asyncio
    async def test_negotiate_propose_allows_when_active(self):
        gate = GameActivePolicy()
        gate.set_active(True)
        ctx = _make_ctx(action="negotiate_propose")
        result = await gate.evaluate(ctx)
        assert result.verdict == StepVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_negotiate_counter_denies_when_inactive(self):
        gate = GameActivePolicy()
        result = await gate.evaluate(_make_ctx(action="negotiate_counter"))
        assert result.verdict == StepVerdict.DENY

    @pytest.mark.asyncio
    async def test_negotiate_accept_denies_when_inactive(self):
        gate = GameActivePolicy()
        result = await gate.evaluate(_make_ctx(action="negotiate_accept"))
        assert result.verdict == StepVerdict.DENY

    @pytest.mark.asyncio
    async def test_negotiate_reject_denies_when_inactive(self):
        gate = GameActivePolicy()
        result = await gate.evaluate(_make_ctx(action="negotiate_reject"))
        assert result.verdict == StepVerdict.DENY

    @pytest.mark.asyncio
    async def test_service_qualified_negotiate_denies_when_inactive(self):
        """An action like ``game.negotiate_propose`` is also gated."""
        gate = GameActivePolicy()
        ctx = _make_ctx(action="game.negotiate_propose")
        result = await gate.evaluate(ctx)
        assert result.verdict == StepVerdict.DENY

    @pytest.mark.asyncio
    async def test_service_qualified_negotiate_allows_when_active(self):
        gate = GameActivePolicy()
        gate.set_active(True)
        ctx = _make_ctx(action="game.negotiate_accept")
        result = await gate.evaluate(ctx)
        assert result.verdict == StepVerdict.ALLOW


# ---------------------------------------------------------------------------
# DENY event shape
# ---------------------------------------------------------------------------


class TestDenyEventShape:
    """DENY returns a PolicyBlockEvent with complete metadata."""

    @pytest.mark.asyncio
    async def test_deny_emits_policy_block_event(self):
        gate = GameActivePolicy()
        ctx = _make_ctx(action="negotiate_propose", run_id="run-99")
        result = await gate.evaluate(ctx)
        assert result.verdict == StepVerdict.DENY
        assert len(result.events) == 1
        block = result.events[0]
        assert isinstance(block, PolicyBlockEvent)
        assert block.event_type == "policy.block"
        assert str(block.policy_id) == "game_active"
        assert str(block.actor_id) == "buyer-001"
        assert block.action == "negotiate_propose"
        assert block.run_id == "run-99"

    @pytest.mark.asyncio
    async def test_deny_sets_step_name(self):
        gate = GameActivePolicy()
        result = await gate.evaluate(_make_ctx(action="negotiate_propose"))
        assert result.step_name == "policy.game_active"

    @pytest.mark.asyncio
    async def test_deny_message_includes_action_and_actor(self):
        gate = GameActivePolicy()
        ctx = _make_ctx(action="negotiate_accept", actor_id="supplier-123")
        result = await gate.evaluate(ctx)
        assert "negotiate_accept" in result.message
        assert "supplier-123" in result.message

    @pytest.mark.asyncio
    async def test_allow_result_has_no_events(self):
        gate = GameActivePolicy()
        gate.set_active(True)
        result = await gate.evaluate(_make_ctx(action="negotiate_propose"))
        assert result.verdict == StepVerdict.ALLOW
        assert result.events == []


# ---------------------------------------------------------------------------
# PolicyEngine integration
# ---------------------------------------------------------------------------


class TestPolicyEngineGateIntegration:
    """PolicyEngine.register_gate runs gates before YAML policies."""

    @pytest.mark.asyncio
    async def test_registered_gate_deny_short_circuits_policy_engine(self):
        """A gate DENY short-circuits the engine even with no YAML policies."""
        engine = PolicyEngine()
        gate = GameActivePolicy()  # starts inactive
        engine.register_gate(gate)
        ctx = _make_ctx(action="negotiate_propose")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.DENY
        assert result.step_name == "policy.game_active"

    @pytest.mark.asyncio
    async def test_registered_gate_allow_falls_through_to_yaml_policies(self):
        """A gate ALLOW lets the engine continue to YAML policy evaluation."""
        engine = PolicyEngine()
        gate = GameActivePolicy()
        gate.set_active(True)
        engine.register_gate(gate)
        ctx = _make_ctx(action="negotiate_propose")
        result = await engine.execute(ctx)
        # With no YAML policies, the engine returns ALLOW
        assert result.verdict == StepVerdict.ALLOW
        assert result.step_name == "policy"  # not the gate's step_name

    @pytest.mark.asyncio
    async def test_non_gated_action_reaches_yaml_engine_even_when_inactive(self):
        """A slack action isn't game-gated — engine progresses to YAML stage."""
        engine = PolicyEngine()
        gate = GameActivePolicy()  # inactive
        engine.register_gate(gate)
        ctx = _make_ctx(action="chat.postMessage", service_id="slack")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW
        # Step name comes from the main engine, not the gate
        assert result.step_name == "policy"

    @pytest.mark.asyncio
    async def test_multiple_gates_run_in_registration_order(self):
        """Gates run in the order they were registered. First DENY wins."""
        engine = PolicyEngine()
        first = GameActivePolicy()
        second = GameActivePolicy()
        first.set_active(True)
        second.set_active(False)  # this one DENIES
        engine.register_gate(first)
        engine.register_gate(second)
        ctx = _make_ctx(action="negotiate_propose")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.DENY

    @pytest.mark.asyncio
    async def test_pre_approved_hold_bypasses_gates(self):
        """If policy_flags contains hold_approved, the gate is also bypassed."""
        engine = PolicyEngine()
        gate = GameActivePolicy()  # inactive — would normally deny
        engine.register_gate(gate)
        ctx = _make_ctx(action="negotiate_propose")
        ctx.policy_flags.append("hold_approved")
        result = await engine.execute(ctx)
        # hold_approved short-circuits at the top of execute — gate never runs
        assert result.verdict == StepVerdict.ALLOW
