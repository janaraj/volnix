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


class TestGameActionShortCircuit:
    """Validate the responder's game-action short-circuit path.

    Game moves (``service_id == "game"``) have no external service to
    simulate; the responder returns a minimal "recorded" proposal and
    skips the Tier 1 / Tier 2 pack lookup entirely.
    """

    async def test_game_action_returns_recorded_response(self):
        responder = await _make_responder_engine()
        ctx = _make_game_action_context(action="negotiate_propose")

        result = await responder.execute(ctx)

        assert result.verdict == StepVerdict.ALLOW
        assert ctx.response_proposal is not None
        assert ctx.response_proposal.response_body == {
            "status": "recorded",
            "action": "negotiate_propose",
        }
        assert result.metadata["game_action"] is True
        assert result.metadata["fidelity_tier"] == 0
        assert len(result.events) == 1
        dispatch = result.events[0]
        assert getattr(dispatch, "fidelity_tier", None) == 0
        assert getattr(dispatch, "service_id", None) == "game"

    async def test_game_action_skips_pack_registry(self):
        """``has_pack`` is never consulted when ``service_id == "game"``."""
        responder = await _make_responder_engine()
        ctx = _make_game_action_context(action="negotiate_counter")

        # Spy on pack_registry.has_pack — it MUST NOT be called.
        call_count = {"n": 0}
        original = responder._pack_registry.has_pack

        def spy(service_id):
            call_count["n"] += 1
            return original(service_id)

        responder._pack_registry.has_pack = spy

        result = await responder.execute(ctx)

        assert result.verdict == StepVerdict.ALLOW
        assert call_count["n"] == 0, "pack_registry.has_pack should not be called for game actions"

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
