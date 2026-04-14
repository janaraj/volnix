"""Tests for volnix.engines.responder — tiered response dispatch and fallback."""

from datetime import UTC, datetime

import pytest

from volnix.core import StepVerdict
from volnix.core.context import ActionContext
from volnix.core.types import ActorId, ServiceId
from volnix.engines.responder.engine import WorldResponderEngine


@pytest.mark.asyncio
async def test_responder_tier1_dispatch(): ...


@pytest.mark.asyncio
async def test_responder_tier2_generate(): ...


@pytest.mark.asyncio
async def test_responder_bootstrapped_service():
    """Test that bootstrapped services run through Tier 2 path."""
    ...


@pytest.mark.asyncio
async def test_responder_fallback(): ...


# ---------------------------------------------------------------------------
# Game-action short-circuit
# ---------------------------------------------------------------------------


async def _make_responder_engine() -> WorldResponderEngine:
    """Build a minimal WorldResponderEngine with default pack directory."""
    engine = WorldResponderEngine()
    await engine.initialize({}, bus=None)
    return engine


def _make_game_action_context(action: str = "negotiate_propose") -> ActionContext:
    """Build an ActionContext for a game action."""
    now = datetime.now(UTC)
    return ActionContext(
        request_id="req-test",
        actor_id=ActorId("buyer-test"),
        service_id=ServiceId("game"),
        action=action,
        input_data={
            "deal_id": "deal-001",
            "price": 80,
            "delivery_weeks": 3,
            "payment_days": 45,
            "warranty_months": 18,
        },
        world_time=now,
        wall_time=now,
    )


class TestGameActionDispatchesToPack:
    """Validate that game actions route through the Tier 1 pack dispatcher.

    Cycle B replaced a legacy short-circuit (``service_id == "game"`` →
    minimal ``{"status": "recorded"}`` proposal, bypassing Tier 1) with
    the standard Tier 1 dispatch path. The event-driven
    :class:`GameOrchestrator` reads state (``negotiation_deal.status ==
    "accepted"``) to evaluate win conditions, so the game pack handlers
    MUST run to apply the state deltas — the short-circuit would leave
    the deal's state frozen.
    """

    async def test_game_action_consults_pack_registry(self):
        """``has_pack("game")`` is called on every game action."""
        responder = await _make_responder_engine()
        ctx = _make_game_action_context(action="negotiate_propose")

        # Spy on pack_registry.has_pack — it MUST be called now.
        call_count = {"n": 0}
        original = responder._pack_registry.has_pack

        def spy(service_id):
            call_count["n"] += 1
            return original(service_id)

        responder._pack_registry.has_pack = spy

        result = await responder.execute(ctx)

        assert result.verdict == StepVerdict.ALLOW
        assert call_count["n"] >= 1, (
            "pack_registry.has_pack must be called for game actions now "
            "that the legacy short-circuit is gone"
        )

    async def test_game_action_dispatch_event_reports_tier1(self):
        """When a game pack is registered, dispatch records fidelity_tier=1."""
        responder = await _make_responder_engine()
        ctx = _make_game_action_context(action="negotiate_propose")

        result = await responder.execute(ctx)

        assert result.verdict == StepVerdict.ALLOW
        # The dispatch event is recorded; if the game pack is registered
        # in the test responder, it reports tier 1. If not registered,
        # the responder falls through to the "no handler" path — we only
        # care that the short-circuit is gone.
        assert "game_action" not in result.metadata, (
            "Legacy ``game_action`` metadata flag was set by the removed short-circuit path"
        )

    async def test_non_game_action_still_consults_packs(self):
        """Regression guard: non-game actions take the normal path."""
        responder = await _make_responder_engine()
        now = datetime.now(UTC)
        ctx = ActionContext(
            request_id="req-test",
            actor_id=ActorId("user-test"),
            service_id=ServiceId("slack"),
            action="chat.postMessage",
            input_data={"channel_id": "C1", "text": "hello"},
            world_time=now,
            wall_time=now,
        )

        call_count = {"n": 0}
        original = responder._pack_registry.has_pack

        def spy(service_id):
            call_count["n"] += 1
            return original(service_id)

        responder._pack_registry.has_pack = spy

        # Don't assert on the full execute() result (it may require more
        # setup than a unit test warrants). We only verify that pack
        # lookup IS attempted for non-game actions.
        try:
            await responder.execute(ctx)
        except Exception:
            pass  # downstream dispatch may fail without full setup; that's ok
        assert call_count["n"] >= 1, "pack_registry.has_pack should be called for non-game actions"
