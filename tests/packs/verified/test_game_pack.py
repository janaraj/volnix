"""Tests for GamePack and its handlers.

MF1 invariant: handlers write deal state via state_deltas on the
ResponseProposal — NEVER directly mutate the ``state`` dict passed
in. Tests assert both shapes: the returned ResponseProposal carries
the deltas, and the input state dict is left untouched.
"""

from __future__ import annotations

from typing import Any

import pytest

from volnix.core.types import ToolName
from volnix.packs.verified.game import GamePack
from volnix.packs.verified.game.handlers import (
    _RESERVED_KEYS,
    _extract_actor_id,
    _extract_terms,
    _find_deal,
    _new_proposal_id,
    handle_negotiate_accept,
    handle_negotiate_counter,
    handle_negotiate_propose,
    handle_negotiate_reject,
)


def _deal(**overrides: Any) -> dict[str, Any]:
    """Build a default open 2-party deal entity."""
    return {
        "id": "deal-1",
        "title": "Test deal",
        "parties": ["buyer", "supplier"],
        "status": "open",
        "terms": {},
        **overrides,
    }


def _state_with_deal(deal: dict[str, Any]) -> dict[str, Any]:
    return {"negotiation_deal": [deal]}


class TestPackSmoke:
    """Pack shape contract."""

    def test_pack_metadata(self):
        pack = GamePack()
        assert pack.pack_name == "game"
        assert pack.category == "game"
        assert pack.fidelity_tier == 1

    def test_pack_tools_count_and_names(self):
        pack = GamePack()
        tool_names = {t["name"] for t in pack.get_tools()}
        assert tool_names == {
            "negotiate_propose",
            "negotiate_counter",
            "negotiate_accept",
            "negotiate_reject",
        }

    def test_all_tools_have_service_game(self):
        pack = GamePack()
        for tool in pack.get_tools():
            assert tool["service"] == "game"

    def test_entity_schemas_include_expected_types(self):
        pack = GamePack()
        schemas = pack.get_entity_schemas()
        assert set(schemas.keys()) == {
            "negotiation_deal",
            "negotiation_proposal",
            "game_player_brief",
            "negotiation_target_terms",
        }

    def test_state_machine_for_negotiation_deal(self):
        pack = GamePack()
        sm = pack.get_state_machines()
        assert "negotiation_deal" in sm
        transitions = sm["negotiation_deal"]["transitions"]
        # Accept / reject are terminal
        assert transitions["accepted"] == []
        assert transitions["rejected"] == []
        # open → proposed, proposed → countered|accepted|rejected
        assert "proposed" in transitions["open"]
        assert "accepted" in transitions["proposed"]
        assert "rejected" in transitions["proposed"]

    async def test_dispatch_unknown_action_raises(self):
        pack = GamePack()
        from volnix.core.errors import PackNotFoundError

        with pytest.raises(PackNotFoundError):
            await pack.handle_action(ToolName("negotiate_unknown"), {}, {})


class TestHelpers:
    """Internal helper functions."""

    def test_extract_actor_id_reads_underscore_key(self):
        assert _extract_actor_id({"_actor_id": "dana-001"}) == "dana-001"
        assert _extract_actor_id({}) == ""

    def test_extract_terms_strips_reserved_keys(self):
        input_data = {
            "deal_id": "d1",
            "message": "hi",
            "reasoning": "because",
            "_actor_id": "dana-001",
            "price": 85,
            "delivery_weeks": 4,
        }
        terms = _extract_terms(input_data)
        assert terms == {"price": 85, "delivery_weeks": 4}

    def test_reserved_keys_cover_all_metadata(self):
        assert "deal_id" in _RESERVED_KEYS
        assert "_actor_id" in _RESERVED_KEYS
        assert "intended_for" in _RESERVED_KEYS

    def test_find_deal_returns_matching_deal(self):
        state = _state_with_deal(_deal(id="d1"))
        assert _find_deal(state, "d1") is not None
        assert _find_deal(state, "nonexistent") is None

    def test_find_deal_returns_none_for_empty_state(self):
        assert _find_deal({}, "d1") is None
        assert _find_deal({"negotiation_deal": []}, "d1") is None

    def test_new_proposal_id_has_prefix(self):
        pid = _new_proposal_id()
        assert pid.startswith("prop-")
        assert len(pid) > len("prop-")

    def test_new_proposal_id_is_unique(self):
        ids = {_new_proposal_id() for _ in range(100)}
        assert len(ids) == 100


class TestHandleNegotiatePropose:
    """negotiate_propose handler."""

    async def test_missing_deal_id_returns_error(self):
        result = await handle_negotiate_propose({}, {})
        assert result.response_body.get("object") == "error"
        assert result.proposed_state_deltas == []

    async def test_deal_not_found_returns_error(self):
        state = _state_with_deal(_deal(id="d1"))
        result = await handle_negotiate_propose(
            {"deal_id": "nonexistent", "_actor_id": "buyer-001"}, state
        )
        assert result.response_body.get("object") == "error"

    async def test_happy_path_produces_two_deltas(self):
        state = _state_with_deal(_deal(id="d1"))
        result = await handle_negotiate_propose(
            {
                "deal_id": "d1",
                "_actor_id": "buyer-001",
                "price": 85,
                "delivery_weeks": 4,
            },
            state,
        )
        # Two deltas: update deal + create proposal
        assert len(result.proposed_state_deltas) == 2
        deal_update = result.proposed_state_deltas[0]
        assert deal_update.entity_type == "negotiation_deal"
        assert deal_update.operation == "update"
        assert deal_update.fields["status"] == "proposed"
        assert deal_update.fields["terms"] == {"price": 85, "delivery_weeks": 4}
        assert deal_update.fields["last_proposed_by"] == "buyer-001"

        proposal_create = result.proposed_state_deltas[1]
        assert proposal_create.entity_type == "negotiation_proposal"
        assert proposal_create.operation == "create"
        assert proposal_create.fields["msg_type"] == "propose"
        assert proposal_create.fields["proposed_by"] == "buyer-001"
        assert proposal_create.fields["deal_id"] == "d1"

    async def test_mf1_invariant_input_state_not_mutated(self):
        """Handler must NOT mutate the input state dict (deltas only)."""
        original_deal = _deal(id="d1")
        state = _state_with_deal(original_deal)
        await handle_negotiate_propose(
            {"deal_id": "d1", "_actor_id": "buyer-001", "price": 85}, state
        )
        # State dict is exactly as we left it
        assert state["negotiation_deal"][0]["status"] == "open"
        assert state["negotiation_deal"][0]["terms"] == {}

    async def test_message_and_reasoning_not_in_terms(self):
        state = _state_with_deal(_deal(id="d1"))
        result = await handle_negotiate_propose(
            {
                "deal_id": "d1",
                "_actor_id": "buyer-001",
                "message": "take this deal",
                "reasoning": "internal",
                "price": 85,
            },
            state,
        )
        terms = result.proposed_state_deltas[0].fields["terms"]
        assert "message" not in terms
        assert "reasoning" not in terms
        assert terms["price"] == 85


class TestHandleNegotiateCounter:
    """negotiate_counter handler — like propose but with consent_by reset."""

    async def test_counter_resets_consent_by(self):
        state = _state_with_deal(_deal(id="d1", consent_by=["some-prior-acceptor"]))
        result = await handle_negotiate_counter(
            {
                "deal_id": "d1",
                "_actor_id": "supplier-002",
                "price": 95,
            },
            state,
        )
        deal_update = result.proposed_state_deltas[0]
        assert deal_update.fields["status"] == "countered"
        assert deal_update.fields["consent_by"] == []  # P7-ready reset

    async def test_counter_creates_proposal_entity_with_counter_msg_type(self):
        state = _state_with_deal(_deal(id="d1"))
        result = await handle_negotiate_counter(
            {"deal_id": "d1", "_actor_id": "supplier-002", "price": 95}, state
        )
        proposal_create = result.proposed_state_deltas[1]
        assert proposal_create.fields["msg_type"] == "counter"

    async def test_counter_missing_deal_id_error(self):
        result = await handle_negotiate_counter({"_actor_id": "supplier-002"}, {})
        assert result.response_body.get("object") == "error"


class TestHandleNegotiateAccept2Party:
    """negotiate_accept with 2 parties — first accept closes."""

    async def test_first_accept_closes_deal(self):
        state = _state_with_deal(_deal(id="d1", parties=["buyer", "supplier"], status="proposed"))
        result = await handle_negotiate_accept(
            {"deal_id": "d1", "_actor_id": "supplier-002"}, state
        )
        deal_update = result.proposed_state_deltas[0]
        assert deal_update.fields["status"] == "accepted"
        assert deal_update.fields["accepted_by"] == "supplier-002"
        assert result.response_body["status"] == "accepted"

    async def test_accept_missing_deal_id_error(self):
        result = await handle_negotiate_accept({"_actor_id": "buyer-001"}, {})
        assert result.response_body.get("object") == "error"

    async def test_accept_deal_not_found_error(self):
        state = _state_with_deal(_deal(id="d1"))
        result = await handle_negotiate_accept(
            {"deal_id": "nonexistent", "_actor_id": "buyer-001"}, state
        )
        assert result.response_body.get("object") == "error"


class TestHandleNegotiateAcceptNParty:
    """negotiate_accept with 3+ parties — consent ledger pattern."""

    async def test_first_acceptor_in_three_party_does_not_close(self):
        state = _state_with_deal(
            _deal(
                id="d1",
                parties=["buyer", "supplier", "regulator"],
                status="proposed",
                consent_by=[],
                consent_rule="unanimous",
            )
        )
        result = await handle_negotiate_accept({"deal_id": "d1", "_actor_id": "buyer-001"}, state)
        deal_update = result.proposed_state_deltas[0]
        # Status unchanged; consent_by appended
        assert "status" not in deal_update.fields
        assert "buyer-001" in deal_update.fields["consent_by"]

    async def test_all_three_accept_closes_deal(self):
        state = _state_with_deal(
            _deal(
                id="d1",
                parties=["buyer", "supplier", "regulator"],
                status="proposed",
                consent_by=["buyer-001", "supplier-002"],
                consent_rule="unanimous",
            )
        )
        # Third party accepts
        result = await handle_negotiate_accept(
            {"deal_id": "d1", "_actor_id": "regulator-003"}, state
        )
        deal_update = result.proposed_state_deltas[0]
        assert deal_update.fields["status"] == "accepted"
        assert "regulator-003" in deal_update.fields["consent_by"]

    async def test_duplicate_accept_from_same_party_is_idempotent(self):
        state = _state_with_deal(
            _deal(
                id="d1",
                parties=["buyer", "supplier", "regulator"],
                status="proposed",
                consent_by=["buyer-001"],
                consent_rule="unanimous",
            )
        )
        # Buyer accepts again — shouldn't add duplicate
        result = await handle_negotiate_accept({"deal_id": "d1", "_actor_id": "buyer-001"}, state)
        deal_update = result.proposed_state_deltas[0]
        assert deal_update.fields["consent_by"].count("buyer-001") == 1
        # Still not unanimous (supplier + regulator missing)
        assert "status" not in deal_update.fields

    async def test_majority_rule_closes_at_two_of_three(self):
        state = _state_with_deal(
            _deal(
                id="d1",
                parties=["buyer", "supplier", "regulator"],
                status="proposed",
                consent_by=["buyer-001"],
                consent_rule="majority",
            )
        )
        # Second party accepts — majority met (2/3)
        result = await handle_negotiate_accept(
            {"deal_id": "d1", "_actor_id": "supplier-002"}, state
        )
        deal_update = result.proposed_state_deltas[0]
        assert deal_update.fields["status"] == "accepted"


class TestHandleNegotiateReject:
    """negotiate_reject handler — one rejection kills the deal."""

    async def test_reject_sets_status_rejected(self):
        state = _state_with_deal(_deal(id="d1", status="countered"))
        result = await handle_negotiate_reject({"deal_id": "d1", "_actor_id": "buyer-001"}, state)
        deal_update = result.proposed_state_deltas[0]
        assert deal_update.fields["status"] == "rejected"
        assert deal_update.fields["rejected_by"] == "buyer-001"

    async def test_reject_missing_deal_id_error(self):
        result = await handle_negotiate_reject({"_actor_id": "buyer-001"}, {})
        assert result.response_body.get("object") == "error"

    async def test_reject_deal_not_found_error(self):
        state = _state_with_deal(_deal(id="d1"))
        result = await handle_negotiate_reject(
            {"deal_id": "nonexistent", "_actor_id": "buyer-001"}, state
        )
        assert result.response_body.get("object") == "error"


class TestDispatchViaHandleAction:
    """End-to-end dispatch through GamePack.handle_action."""

    async def test_dispatch_propose(self):
        pack = GamePack()
        state = _state_with_deal(_deal(id="d1"))
        result = await pack.handle_action(
            ToolName("negotiate_propose"),
            {"deal_id": "d1", "_actor_id": "buyer-001", "price": 85},
            state,
        )
        assert len(result.proposed_state_deltas) == 2

    async def test_dispatch_counter(self):
        pack = GamePack()
        state = _state_with_deal(_deal(id="d1"))
        result = await pack.handle_action(
            ToolName("negotiate_counter"),
            {"deal_id": "d1", "_actor_id": "supplier-002", "price": 95},
            state,
        )
        assert len(result.proposed_state_deltas) == 2

    async def test_dispatch_accept(self):
        pack = GamePack()
        state = _state_with_deal(_deal(id="d1"))
        result = await pack.handle_action(
            ToolName("negotiate_accept"),
            {"deal_id": "d1", "_actor_id": "buyer-001"},
            state,
        )
        assert result.proposed_state_deltas[0].fields["status"] == "accepted"

    async def test_dispatch_reject(self):
        pack = GamePack()
        state = _state_with_deal(_deal(id="d1"))
        result = await pack.handle_action(
            ToolName("negotiate_reject"),
            {"deal_id": "d1", "_actor_id": "buyer-001"},
            state,
        )
        assert result.proposed_state_deltas[0].fields["status"] == "rejected"
