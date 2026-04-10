"""Tests for NegotiationEvaluator — game tools, move parsing, deal scoring."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from volnix.engines.game.definition import PlayerScore, RoundState
from volnix.game.evaluators.base import BaseRoundEvaluator
from volnix.game.evaluators.negotiation import (
    EFFICIENCY_BONUS_PER_ROUND,
    NEGOTIATION_TOOLS,
    NegotiationEvaluator,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_move_event(
    actor_id: str, action: str, **payload
) -> SimpleNamespace:
    """Build a committed game-action event as the runner would reconstruct it.

    Mirrors the SimpleNamespace shape from
    ``GameRunner._activate_player_turn`` (volnix/game/runner.py:336-349):
    ``event_type = "world.<action>"``, ``actor_id``, ``input_data = payload``.
    """
    return SimpleNamespace(
        event_type=f"world.{action}",
        actor_id=actor_id,
        input_data=dict(payload),
    )


def _make_chat_event(
    actor_id: str, text: str, channel_id: str = "CH001"
) -> SimpleNamespace:
    """Build a chat.postMessage event (used only to verify they're ignored)."""
    return SimpleNamespace(
        event_type="world.chat.postMessage",
        actor_id=actor_id,
        input_data={"text": text, "channel_id": channel_id},
    )


def _make_event(event_type: str, actor_id: str, **input_data) -> SimpleNamespace:
    """Build a generic event."""
    return SimpleNamespace(
        event_type=event_type,
        actor_id=actor_id,
        input_data=dict(input_data),
    )


def _make_mock_store() -> AsyncMock:
    """Mock EntityStore with create/update methods."""
    store = AsyncMock()
    store.create = AsyncMock()
    store.update = AsyncMock(return_value={})
    return store


def _make_mock_state(
    store: AsyncMock | None = None,
    deals: list[dict] | None = None,
    targets: list[dict] | None = None,
    scorecards: list[dict] | None = None,
) -> MagicMock:
    """Mock state engine with _store, _ledger, and query_entities."""
    state = MagicMock()
    state._store = store or _make_mock_store()
    state._ledger = AsyncMock()
    state._ledger.append = AsyncMock()

    entity_map: dict[str, list] = {}
    if deals is not None:
        entity_map["negotiation_deal"] = deals
    if targets is not None:
        entity_map["negotiation_target"] = targets
    if scorecards is not None:
        entity_map["negotiation_scorecard"] = scorecards

    async def query_entities(entity_type: str, **kwargs):
        return entity_map.get(entity_type, [])

    state.query_entities = AsyncMock(side_effect=query_entities)
    return state


def _default_deal() -> dict:
    return {
        "id": "deal-001",
        "title": "Test Deal",
        "status": "open",
        "parties": ["buyer", "supplier"],
        "terms": {},
        "terms_template": {
            "price": [80, 120],
            "delivery_weeks": [2, 8],
        },
    }


def _default_targets() -> list[dict]:
    return [
        {
            "game_owner_id": "buyer-abc",
            "deal_id": "deal-001",
            "ideal_terms": {"price": 85, "delivery_weeks": 3},
            "term_weights": {"price": 0.6, "delivery_weeks": 0.4},
            "term_ranges": {"price": [80, 120], "delivery_weeks": [2, 8]},
            "batna_score": 25.0,
        },
        {
            "game_owner_id": "supplier-xyz",
            "deal_id": "deal-001",
            "ideal_terms": {"price": 115, "delivery_weeks": 6},
            "term_weights": {"price": 0.6, "delivery_weeks": 0.4},
            "term_ranges": {"price": [80, 120], "delivery_weeks": [2, 8]},
            "batna_score": 25.0,
        },
    ]


def _default_scorecards() -> list[dict]:
    return [
        {
            "id": "sc-buyer",
            "game_owner_id": "buyer-abc",
            "total_points": 0.0,
            "deals_closed": 0,
        },
        {
            "id": "sc-supplier",
            "game_owner_id": "supplier-xyz",
            "total_points": 0.0,
            "deals_closed": 0,
        },
    ]


# ---------------------------------------------------------------------------
# Message parsing tests
# ---------------------------------------------------------------------------


class TestGameTools:
    """Validate the structured game-move tool schemas the LLM sees."""

    def test_negotiation_exposes_four_tools(self):
        evaluator = NegotiationEvaluator()
        tools = evaluator.game_tools()
        assert len(tools) == 4
        names = {t.name for t in tools}
        assert names == {
            "negotiate_propose",
            "negotiate_counter",
            "negotiate_accept",
            "negotiate_reject",
        }

    def test_propose_and_counter_share_terms_schema(self):
        evaluator = NegotiationEvaluator()
        tools = {t.name: t for t in evaluator.game_tools()}
        for name in ("negotiate_propose", "negotiate_counter"):
            params = tools[name].parameters
            required = set(params["required"])
            assert required == {
                "deal_id",
                "price",
                "delivery_weeks",
                "payment_days",
                "warranty_months",
            }
            assert "message" in params["properties"]
            # message is optional
            assert "message" not in required

    def test_accept_and_reject_require_deal_id_only(self):
        evaluator = NegotiationEvaluator()
        tools = {t.name: t for t in evaluator.game_tools()}
        for name in ("negotiate_accept", "negotiate_reject"):
            params = tools[name].parameters
            assert params["required"] == ["deal_id"]
            assert "message" in params["properties"]

    def test_all_tools_have_service_game(self):
        evaluator = NegotiationEvaluator()
        for tool in evaluator.game_tools():
            assert tool.service == "game", (
                f"{tool.name} must have service='game' for permission scoping"
            )

    def test_additional_properties_false_on_all_schemas(self):
        """LLM providers enforce the schema — no extra fields can sneak in."""
        evaluator = NegotiationEvaluator()
        for tool in evaluator.game_tools():
            assert tool.parameters.get("additionalProperties") is False, (
                f"{tool.name} schema must set additionalProperties: false"
            )

    def test_tool_module_constant_matches_instance_method(self):
        """``NEGOTIATION_TOOLS`` constant and ``game_tools()`` are the same list."""
        assert NegotiationEvaluator().game_tools() == NEGOTIATION_TOOLS

    def test_default_evaluator_returns_empty_tool_list(self):
        """Base class default is an empty list — game types that don't need
        structured tools inherit a no-op."""
        assert BaseRoundEvaluator().game_tools() == []


class TestMoveParsing:
    """Validate ``_parse_round_moves`` — reads typed events, no regex."""

    def test_parse_propose_event(self):
        evaluator = NegotiationEvaluator()
        events = [
            _make_move_event(
                "buyer-abc",
                "negotiate_propose",
                deal_id="deal-001",
                price=80,
                delivery_weeks=3,
                payment_days=45,
                warranty_months=18,
            )
        ]
        moves = evaluator._parse_round_moves(events)
        assert len(moves) == 1
        assert moves[0].msg_type == "proposal"
        assert moves[0].actor_id == "buyer-abc"
        assert moves[0].deal_id == "deal-001"
        assert moves[0].terms == {
            "price": 80,
            "delivery_weeks": 3,
            "payment_days": 45,
            "warranty_months": 18,
        }

    def test_parse_counter_event(self):
        evaluator = NegotiationEvaluator()
        events = [
            _make_move_event(
                "supplier-xyz",
                "negotiate_counter",
                deal_id="deal-001",
                price=110,
                delivery_weeks=5,
                payment_days=30,
                warranty_months=12,
            )
        ]
        moves = evaluator._parse_round_moves(events)
        assert len(moves) == 1
        assert moves[0].msg_type == "counter"
        assert moves[0].deal_id == "deal-001"
        assert moves[0].terms["price"] == 110

    def test_parse_accept_event(self):
        evaluator = NegotiationEvaluator()
        events = [
            _make_move_event("buyer-abc", "negotiate_accept", deal_id="deal-001")
        ]
        moves = evaluator._parse_round_moves(events)
        assert len(moves) == 1
        assert moves[0].msg_type == "accept"
        assert moves[0].deal_id == "deal-001"
        assert moves[0].terms is None

    def test_parse_reject_event(self):
        evaluator = NegotiationEvaluator()
        events = [
            _make_move_event("supplier-xyz", "negotiate_reject", deal_id="deal-001")
        ]
        moves = evaluator._parse_round_moves(events)
        assert len(moves) == 1
        assert moves[0].msg_type == "reject"
        assert moves[0].deal_id == "deal-001"

    def test_ignore_chat_post_message(self):
        """Chat dialogue is not a game move — the parser skips it silently."""
        evaluator = NegotiationEvaluator()
        events = [
            _make_chat_event(
                "buyer-abc",
                "Here's my opening offer — let me know what you think.",
            )
        ]
        moves = evaluator._parse_round_moves(events)
        assert moves == []

    def test_ignore_propose_without_deal_id(self):
        """Malformed payload (no deal_id) is dropped gracefully."""
        evaluator = NegotiationEvaluator()
        events = [
            _make_move_event("buyer-abc", "negotiate_propose", price=80)
        ]
        moves = evaluator._parse_round_moves(events)
        assert moves == []

    def test_ignore_propose_without_terms(self):
        """Malformed payload (no term fields) is dropped gracefully."""
        evaluator = NegotiationEvaluator()
        events = [
            _make_move_event("buyer-abc", "negotiate_propose", deal_id="deal-001")
        ]
        moves = evaluator._parse_round_moves(events)
        assert moves == []

    def test_mixed_events_one_round(self):
        """Interleaved dialogue + game moves → only moves are extracted, in order."""
        evaluator = NegotiationEvaluator()
        events = [
            _make_chat_event("buyer-abc", "Hey, here's my number."),
            _make_move_event(
                "buyer-abc",
                "negotiate_propose",
                deal_id="deal-001",
                price=80,
                delivery_weeks=3,
                payment_days=45,
                warranty_months=18,
            ),
            _make_chat_event("supplier-xyz", "Tough ask."),
            _make_move_event(
                "supplier-xyz",
                "negotiate_counter",
                deal_id="deal-001",
                price=110,
                delivery_weeks=5,
                payment_days=30,
                warranty_months=12,
            ),
            _make_event("world.get_account", "buyer-abc"),  # totally unrelated
        ]
        moves = evaluator._parse_round_moves(events)
        assert len(moves) == 2
        assert moves[0].msg_type == "proposal"
        assert moves[0].actor_id == "buyer-abc"
        assert moves[1].msg_type == "counter"
        assert moves[1].actor_id == "supplier-xyz"

    def test_empty_events(self):
        evaluator = NegotiationEvaluator()
        assert evaluator._parse_round_moves([]) == []


# ---------------------------------------------------------------------------
# Deal scoring tests
# ---------------------------------------------------------------------------


class TestDealScoring:
    def test_perfect_match_scores_100(self):
        target = {
            "ideal_terms": {"price": 85, "delivery_weeks": 3},
            "term_weights": {"price": 0.6, "delivery_weeks": 0.4},
            "term_ranges": {"price": [80, 120], "delivery_weeks": [2, 8]},
        }
        actual = {"price": 85, "delivery_weeks": 3}
        score = NegotiationEvaluator._compute_deal_score(actual, target)
        assert score == pytest.approx(100.0)

    def test_worst_case_scores_zero(self):
        target = {
            "ideal_terms": {"price": 80},
            "term_weights": {"price": 1.0},
            "term_ranges": {"price": [80, 120]},
        }
        actual = {"price": 120}
        score = NegotiationEvaluator._compute_deal_score(actual, target)
        assert score == pytest.approx(0.0)

    def test_midpoint_scores_50(self):
        target = {
            "ideal_terms": {"price": 80},
            "term_weights": {"price": 1.0},
            "term_ranges": {"price": [80, 120]},
        }
        actual = {"price": 100}
        score = NegotiationEvaluator._compute_deal_score(actual, target)
        assert score == pytest.approx(50.0)

    def test_weights_affect_score(self):
        target = {
            "ideal_terms": {"price": 80, "delivery": 2},
            "term_weights": {"price": 0.9, "delivery": 0.1},
            "term_ranges": {"price": [80, 120], "delivery": [2, 10]},
        }
        actual = {"price": 80, "delivery": 10}
        score = NegotiationEvaluator._compute_deal_score(actual, target)
        assert score == pytest.approx(90.0)

    def test_zero_range_exact_match(self):
        target = {
            "ideal_terms": {"fixed": 50},
            "term_weights": {"fixed": 1.0},
            "term_ranges": {"fixed": [50, 50]},
        }
        actual = {"fixed": 50}
        score = NegotiationEvaluator._compute_deal_score(actual, target)
        assert score == pytest.approx(100.0)

    def test_zero_range_mismatch(self):
        target = {
            "ideal_terms": {"fixed": 50},
            "term_weights": {"fixed": 1.0},
            "term_ranges": {"fixed": [50, 50]},
        }
        actual = {"fixed": 60}
        score = NegotiationEvaluator._compute_deal_score(actual, target)
        assert score == pytest.approx(0.0)

    def test_empty_terms_returns_zero(self):
        target = {
            "ideal_terms": {"price": 85},
            "term_weights": {"price": 1.0},
            "term_ranges": {"price": [80, 120]},
        }
        score = NegotiationEvaluator._compute_deal_score({}, target)
        assert score == pytest.approx(0.0)

    def test_missing_target_fields_returns_zero(self):
        score = NegotiationEvaluator._compute_deal_score({"price": 100}, {})
        assert score == pytest.approx(0.0)

    def test_partial_terms_scored(self):
        target = {
            "ideal_terms": {"price": 80, "delivery": 2, "warranty": 12},
            "term_weights": {"price": 0.5, "delivery": 0.3, "warranty": 0.2},
            "term_ranges": {"price": [80, 120], "delivery": [2, 10], "warranty": [6, 24]},
        }
        actual = {"price": 80}
        score = NegotiationEvaluator._compute_deal_score(actual, target)
        assert score == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Efficiency bonus tests
# ---------------------------------------------------------------------------


class TestEfficiencyBonus:
    def test_early_deal_max_bonus(self):
        bonus = max(0.0, (8 - 1) * EFFICIENCY_BONUS_PER_ROUND)
        assert bonus == pytest.approx(14.0)

    def test_last_round_zero_bonus(self):
        bonus = max(0.0, (8 - 8) * EFFICIENCY_BONUS_PER_ROUND)
        assert bonus == pytest.approx(0.0)

    def test_mid_game_bonus(self):
        bonus = max(0.0, (8 - 4) * EFFICIENCY_BONUS_PER_ROUND)
        assert bonus == pytest.approx(8.0)


# ---------------------------------------------------------------------------
# Evaluator integration tests
# ---------------------------------------------------------------------------


class TestEvaluatorIntegration:
    async def test_proposal_creates_entity(self):
        store = _make_mock_store()
        state = _make_mock_state(store=store, deals=[_default_deal()])
        events = [
            _make_move_event(
                "buyer-abc",
                "negotiate_propose",
                deal_id="deal-001",
                price=90,
                delivery_weeks=4,
                payment_days=30,
                warranty_months=12,
            )
        ]
        round_state = RoundState(current_round=1, total_rounds=8)
        player_scores = {"buyer-abc": PlayerScore(actor_id="buyer-abc")}

        evaluator = NegotiationEvaluator()
        await evaluator.evaluate(state, events, round_state, player_scores)

        store.create.assert_awaited_once()
        call_args = store.create.call_args
        assert call_args[0][0] == "negotiation_proposal"
        proposal_data = call_args[0][2]
        assert proposal_data["proposed_by"] == "buyer-abc"
        assert proposal_data["terms"] == {
            "price": 90,
            "delivery_weeks": 4,
            "payment_days": 30,
            "warranty_months": 12,
        }

        update_calls = [
            c for c in store.update.call_args_list if c[0][0] == "negotiation_deal"
        ]
        assert len(update_calls) >= 1
        assert update_calls[0][0][2]["status"] == "proposed"

    async def test_counter_updates_deal_status(self):
        deal = _default_deal()
        deal["status"] = "proposed"
        store = _make_mock_store()
        state = _make_mock_state(store=store, deals=[deal])
        events = [
            _make_move_event(
                "supplier-xyz",
                "negotiate_counter",
                deal_id="deal-001",
                price=110,
                delivery_weeks=5,
                payment_days=30,
                warranty_months=12,
            )
        ]
        round_state = RoundState(current_round=2, total_rounds=8)

        evaluator = NegotiationEvaluator()
        await evaluator.evaluate(state, events, round_state, {})

        update_calls = [
            c for c in store.update.call_args_list if c[0][0] == "negotiation_deal"
        ]
        assert len(update_calls) >= 1
        assert update_calls[0][0][2]["status"] == "countered"

    async def test_accept_updates_both_scorecards(self):
        deal = _default_deal()
        deal["status"] = "proposed"
        deal["terms"] = {"price": 100, "delivery_weeks": 4}
        store = _make_mock_store()
        state = _make_mock_state(
            store=store,
            deals=[deal],
            targets=_default_targets(),
            scorecards=_default_scorecards(),
        )
        events = [
            _make_move_event("buyer-abc", "negotiate_accept", deal_id="deal-001")
        ]
        round_state = RoundState(current_round=3, total_rounds=8)
        player_scores = {
            "buyer-abc": PlayerScore(actor_id="buyer-abc"),
            "supplier-xyz": PlayerScore(actor_id="supplier-xyz"),
        }

        evaluator = NegotiationEvaluator()
        await evaluator.evaluate(state, events, round_state, player_scores)

        deal_updates = [
            c for c in store.update.call_args_list if c[0][0] == "negotiation_deal"
        ]
        assert any(c[0][2].get("status") == "accepted" for c in deal_updates)

        sc_updates = [
            c for c in store.update.call_args_list if c[0][0] == "negotiation_scorecard"
        ]
        assert len(sc_updates) == 2
        for call in sc_updates:
            fields = call[0][2]
            assert "total_points" in fields
            assert fields["total_points"] > 0

    async def test_reject_updates_deal_status(self):
        deal = _default_deal()
        deal["status"] = "countered"
        store = _make_mock_store()
        state = _make_mock_state(store=store, deals=[deal])
        events = [
            _make_move_event("buyer-abc", "negotiate_reject", deal_id="deal-001")
        ]
        round_state = RoundState(current_round=5, total_rounds=8)

        evaluator = NegotiationEvaluator()
        await evaluator.evaluate(state, events, round_state, {})

        update_calls = [
            c for c in store.update.call_args_list if c[0][0] == "negotiation_deal"
        ]
        assert any(c[0][2].get("status") == "rejected" for c in update_calls)

    async def test_no_messages_is_noop(self):
        store = _make_mock_store()
        state = _make_mock_state(store=store, deals=[_default_deal()])
        round_state = RoundState(current_round=1, total_rounds=8)

        evaluator = NegotiationEvaluator()
        await evaluator.evaluate(state, [], round_state, {})

        store.create.assert_not_awaited()
        store.update.assert_not_awaited()

    async def test_final_round_batna(self):
        store = _make_mock_store()
        state = _make_mock_state(
            store=store,
            deals=[_default_deal()],
            targets=_default_targets(),
            scorecards=_default_scorecards(),
        )
        round_state = RoundState(current_round=8, total_rounds=8)
        player_scores = {
            "buyer-abc": PlayerScore(actor_id="buyer-abc"),
            "supplier-xyz": PlayerScore(actor_id="supplier-xyz"),
        }

        evaluator = NegotiationEvaluator()
        await evaluator.evaluate(state, [], round_state, player_scores)

        sc_updates = [
            c for c in store.update.call_args_list if c[0][0] == "negotiation_scorecard"
        ]
        assert len(sc_updates) == 2
        for call in sc_updates:
            assert call[0][2]["total_points"] == 25.0

    async def test_none_state_engine_is_noop(self):
        evaluator = NegotiationEvaluator()
        events = [_make_chat_event("buyer-abc", 'PROPOSAL: {"price": 90}')]
        round_state = RoundState(current_round=1, total_rounds=8)
        await evaluator.evaluate(None, events, round_state, {})

    async def test_no_store_on_state_is_noop(self):
        state = MagicMock()
        state._store = None
        evaluator = NegotiationEvaluator()
        events = [_make_chat_event("buyer-abc", 'PROPOSAL: {"price": 90}')]
        round_state = RoundState(current_round=1, total_rounds=8)
        await evaluator.evaluate(state, events, round_state, {})

    async def test_store_write_failure_logged_not_raised(self):
        store = _make_mock_store()
        store.create = AsyncMock(side_effect=RuntimeError("DB error"))
        state = _make_mock_state(store=store, deals=[_default_deal()])
        events = [_make_chat_event("buyer-abc", 'PROPOSAL: {"price": 90}')]
        round_state = RoundState(current_round=1, total_rounds=8)

        evaluator = NegotiationEvaluator()
        await evaluator.evaluate(state, events, round_state, {})

    async def test_deal_already_accepted_skipped(self):
        deal = _default_deal()
        deal["status"] = "accepted"
        store = _make_mock_store()
        state = _make_mock_state(store=store, deals=[deal])
        events = [_make_chat_event("buyer-abc", 'PROPOSAL: {"price": 90}')]
        round_state = RoundState(current_round=1, total_rounds=8)

        evaluator = NegotiationEvaluator()
        await evaluator.evaluate(state, events, round_state, {})

        store.create.assert_not_awaited()

    async def test_counter_then_accept_same_round(self):
        """COUNTER + ACCEPT in same round: ACCEPT reads updated terms after reload."""
        deal = _default_deal()
        deal["status"] = "open"
        deal["terms"] = {}  # no terms yet
        store = _make_mock_store()

        call_count = {"n": 0}

        async def query_entities(entity_type, **kw):
            if entity_type == "negotiation_deal":
                call_count["n"] += 1
                if call_count["n"] <= 1:
                    return [deal]  # first load: no terms
                # After reload: terms updated by COUNTER
                updated = dict(deal)
                updated["terms"] = {"price": 105, "delivery_weeks": 5}
                updated["status"] = "countered"
                return [updated]
            if entity_type == "negotiation_target":
                return _default_targets()
            if entity_type == "negotiation_scorecard":
                return _default_scorecards()
            return []

        state = MagicMock()
        state._store = store
        state._ledger = AsyncMock()
        state._ledger.append = AsyncMock()
        state.query_entities = AsyncMock(side_effect=query_entities)

        events = [
            _make_move_event(
                "supplier-xyz",
                "negotiate_counter",
                deal_id="deal-001",
                price=105,
                delivery_weeks=5,
                payment_days=30,
                warranty_months=12,
            ),
            _make_move_event("buyer-abc", "negotiate_accept", deal_id="deal-001"),
        ]
        round_state = RoundState(current_round=3, total_rounds=8)
        player_scores = {
            "buyer-abc": PlayerScore(actor_id="buyer-abc"),
            "supplier-xyz": PlayerScore(actor_id="supplier-xyz"),
        }

        evaluator = NegotiationEvaluator()
        await evaluator.evaluate(state, events, round_state, player_scores)

        # Deal should be accepted (terms available after reload)
        deal_updates = [
            c for c in store.update.call_args_list if c[0][0] == "negotiation_deal"
        ]
        assert any(c[0][2].get("status") == "accepted" for c in deal_updates)

        # Both scorecards should be updated
        sc_updates = [
            c for c in store.update.call_args_list if c[0][0] == "negotiation_scorecard"
        ]
        assert len(sc_updates) == 2
        for call in sc_updates:
            assert call[0][2]["total_points"] > 0


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_evaluator_satisfies_protocol(self):
        from volnix.engines.game.protocols import RoundEvaluator

        assert isinstance(NegotiationEvaluator(), RoundEvaluator)

    def test_negotiation_importable(self):
        from volnix.game.evaluators import NegotiationEvaluator as NegEval

        assert NegEval is NegotiationEvaluator


# ---------------------------------------------------------------------------
# Deal lookup helper tests
# ---------------------------------------------------------------------------


class TestDealLookup:
    def test_find_active_deal_by_party(self):
        deals = [{"id": "d1", "status": "open", "parties": ["buyer", "supplier"]}]
        result = NegotiationEvaluator._find_active_deal(deals, "buyer-abc")
        assert result is not None
        assert result["id"] == "d1"

    def test_find_active_deal_skips_accepted(self):
        deals = [{"id": "d1", "status": "accepted", "parties": ["buyer", "supplier"]}]
        result = NegotiationEvaluator._find_active_deal(deals, "buyer-abc")
        assert result is None

    def test_find_deal_by_id(self):
        deals = [{"id": "d1"}, {"id": "d2"}]
        result = NegotiationEvaluator._find_deal_by_id(deals, "d2")
        assert result is not None
        assert result["id"] == "d2"

    def test_find_deal_by_id_missing(self):
        deals = [{"id": "d1"}]
        result = NegotiationEvaluator._find_deal_by_id(deals, "d999")
        assert result is None

    def test_find_deal_by_id_empty(self):
        result = NegotiationEvaluator._find_deal_by_id([], "d1")
        assert result is None


# ---------------------------------------------------------------------------
# build_deliverable_extras — deal summary for run deliverable
# ---------------------------------------------------------------------------


class TestBuildDeliverableExtras:
    """Tests for NegotiationEvaluator.build_deliverable_extras.

    Validates that deal outcomes are emitted as a ``deals`` array of
    flat-primitive objects so the frontend's array-of-objects renderer
    can display them as a grouped card list.
    """

    async def test_accepted_deal_entry_in_deals_array(self):
        """An accepted deal becomes a flat object in the deals array."""
        evaluator = NegotiationEvaluator()
        deal = {
            "id": "deal-001",
            "title": "Q3 Steel Supply Contract",
            "status": "accepted",
            "terms": {
                "price": 118,
                "delivery_weeks": 6,
                "payment_days": 15,
                "warranty_months": 6,
            },
            "accepted_by": "supplier-99b0e8da",
            "accepted_round": 3,
        }
        state = _make_mock_state(deals=[deal])

        extras = await evaluator.build_deliverable_extras(state)

        assert "deals" in extras
        assert len(extras["deals"]) == 1
        entry = extras["deals"][0]
        assert entry["title"] == "Q3 Steel Supply Contract"
        assert entry["status"] == "ACCEPTED"
        assert entry["round"] == 3
        assert entry["accepted_by"] == "supplier"
        terms_str = entry["terms"]
        assert "price=118" in terms_str
        assert "delivery_weeks=6" in terms_str
        assert "payment_days=15" in terms_str
        assert "warranty_months=6" in terms_str
        # Flat primitives only — no nested objects that would render as
        # "[object Object]" in the frontend.
        for k, v in entry.items():
            assert isinstance(v, (str, int, bool)), (
                f"{k!r} must be a flat primitive, got {type(v).__name__}"
            )

    async def test_rejected_deal_entry_in_deals_array(self):
        """A rejected deal entry has status REJECTED and rejected_by."""
        evaluator = NegotiationEvaluator()
        deal = {
            "id": "deal-001",
            "title": "Rejected Deal",
            "status": "rejected",
            "terms": {"price": 100},
            "rejected_by": "buyer-abc123",
        }
        state = _make_mock_state(deals=[deal])

        extras = await evaluator.build_deliverable_extras(state)

        entry = extras["deals"][0]
        assert entry["title"] == "Rejected Deal"
        assert entry["status"] == "REJECTED"
        assert entry["rejected_by"] == "buyer"
        assert "price=100" in entry["terms"]
        assert "accepted_by" not in entry
        assert "round" not in entry

    async def test_open_deal_shows_last_proposal(self):
        """An open deal entry records the last-proposing party."""
        evaluator = NegotiationEvaluator()
        deal = {
            "id": "deal-001",
            "title": "Open Deal",
            "status": "countered",
            "terms": {"price": 95, "delivery_weeks": 4},
            "last_proposed_by": "supplier-xyz",
        }
        state = _make_mock_state(deals=[deal])

        extras = await evaluator.build_deliverable_extras(state)

        entry = extras["deals"][0]
        assert entry["title"] == "Open Deal"
        assert entry["status"] == "COUNTERED"
        assert entry["last_proposed_by"] == "supplier"
        assert "price=95" in entry["terms"]

    async def test_open_deal_with_no_terms_shows_placeholder(self):
        """An open deal with no terms yet shows 'no terms proposed'."""
        evaluator = NegotiationEvaluator()
        deal = {
            "id": "deal-001",
            "title": "Empty Deal",
            "status": "open",
            "terms": {},
        }
        state = _make_mock_state(deals=[deal])

        extras = await evaluator.build_deliverable_extras(state)

        entry = extras["deals"][0]
        assert entry["terms"] == "no terms proposed"

    async def test_no_deals_returns_empty(self):
        """No deals → empty dict (no deals key at all)."""
        evaluator = NegotiationEvaluator()
        state = _make_mock_state(deals=[])

        extras = await evaluator.build_deliverable_extras(state)

        assert extras == {}

    async def test_state_engine_none_returns_empty(self):
        """None state_engine → empty dict, no crash."""
        evaluator = NegotiationEvaluator()
        extras = await evaluator.build_deliverable_extras(None)
        assert extras == {}

    async def test_query_failure_returns_empty(self):
        """If query_entities raises, return empty dict (no crash)."""
        evaluator = NegotiationEvaluator()
        state = MagicMock()
        state.query_entities = AsyncMock(side_effect=RuntimeError("boom"))

        extras = await evaluator.build_deliverable_extras(state)

        assert extras == {}

    async def test_multiple_deals_in_array(self):
        """Multiple deals appear as multiple entries in the deals array."""
        evaluator = NegotiationEvaluator()
        deals = [
            {
                "id": "deal-001",
                "title": "Deal One",
                "status": "accepted",
                "terms": {"price": 100},
                "accepted_by": "buyer-1",
                "accepted_round": 2,
            },
            {
                "id": "deal-002",
                "title": "Deal Two",
                "status": "rejected",
                "terms": {"price": 200},
                "rejected_by": "supplier-1",
            },
        ]
        state = _make_mock_state(deals=deals)

        extras = await evaluator.build_deliverable_extras(state)

        assert len(extras["deals"]) == 2
        titles = {d["title"] for d in extras["deals"]}
        assert titles == {"Deal One", "Deal Two"}
        statuses = {d["status"] for d in extras["deals"]}
        assert statuses == {"ACCEPTED", "REJECTED"}
