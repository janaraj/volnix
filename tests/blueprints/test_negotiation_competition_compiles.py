"""Compile smoke test for ``negotiation_competition.yaml`` (Q3 Steel).

Exercises the Cycle B event-driven blueprint shape end-to-end:

- YAML parses cleanly via :class:`YAMLParser`
- Produces a :class:`GameDefinition` with ``scoring_mode=competitive``
- Declares one deal (``deal-q3-steel``) with both player briefs
- Declares two ``target_terms`` (one per role, competitive mode only)
- Win conditions include the event-driven termination set
- Agents blueprint (``agents_negotiation.yaml``) declares two roles
  with scoped permissions

This is a static parse test — it does NOT run the LLM seed expander,
so it can run in CI without network access.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from volnix.engines.world_compiler.yaml_parser import YAMLParser
from volnix.reality.expander import ConditionExpander

REPO_ROOT = Path(__file__).resolve().parents[2]
WORLD_YAML = REPO_ROOT / "volnix/blueprints/official/negotiation_competition.yaml"
AGENTS_YAML = REPO_ROOT / "volnix/blueprints/official/agents_negotiation.yaml"


@pytest.fixture(scope="module")
def world_def() -> dict:
    with WORLD_YAML.open() as f:
        data = yaml.safe_load(f)
    assert "world" in data
    return data["world"]


@pytest.fixture(scope="module")
def agents_def() -> dict:
    with AGENTS_YAML.open() as f:
        data = yaml.safe_load(f)
    assert "agents" in data
    return data


@pytest.fixture(scope="module")
async def compiled_plan():
    parser = YAMLParser(ConditionExpander())
    plan, _ = await parser.parse(str(WORLD_YAML))
    return plan


# ---------------------------------------------------------------------------
# Game config — event-driven + competitive
# ---------------------------------------------------------------------------


class TestGameConfig:
    def test_game_enabled(self, world_def):
        assert world_def["game"]["enabled"] is True
        assert world_def["game"]["mode"] == "negotiation"
        assert world_def["game"]["scoring_mode"] == "competitive"

    def test_flow_is_event_driven(self, world_def):
        flow = world_def["game"]["flow"]
        assert flow["type"] == "event_driven"
        assert flow["activation_mode"] == "serial"
        assert flow["first_mover"] == "buyer"
        assert flow["max_events"] > 0
        assert flow["max_wall_clock_seconds"] > 0
        assert flow["bonus_per_event"] > 0

    def test_negotiation_fields(self, world_def):
        """Domain schema: price, delivery_weeks, payment_days, warranty_months."""
        fields = world_def["game"]["negotiation_fields"]
        field_names = {f["name"] for f in fields}
        assert field_names == {
            "price",
            "delivery_weeks",
            "payment_days",
            "warranty_months",
        }

    def test_no_legacy_type_config_block(self, world_def):
        """NF1 (B-cleanup.1b): ``type_config`` removed in favor of flattened ``negotiation_fields``."""
        assert "type_config" not in world_def["game"]

    def test_no_legacy_round_keys(self, world_def):
        """Legacy ``rounds`` / ``between_rounds`` / ``turn_protocol`` must be absent."""
        game = world_def["game"]
        assert "rounds" not in game
        assert "between_rounds" not in game
        assert "turn_protocol" not in game
        assert "resource_reset_per_round" not in game


# ---------------------------------------------------------------------------
# Game entities — deal + briefs + target terms
# ---------------------------------------------------------------------------


class TestGameEntities:
    def test_single_deal(self, world_def):
        deals = world_def["game"]["entities"]["deals"]
        assert len(deals) == 1
        deal = deals[0]
        assert deal["id"] == "deal-q3-steel"
        assert set(deal["parties"]) == {"buyer", "supplier"}
        assert deal["status"] == "open"
        assert deal["terms"] == {}
        assert "terms_template" in deal

    def test_two_player_briefs(self, world_def):
        briefs = world_def["game"]["entities"]["player_briefs"]
        assert len(briefs) == 2
        roles = {b["actor_role"] for b in briefs}
        assert roles == {"buyer", "supplier"}
        for brief in briefs:
            assert brief["deal_id"] == "deal-q3-steel"
            assert brief.get("brief_content"), f"Brief for {brief['actor_role']} must have content"
            assert brief.get("mission"), f"Brief for {brief['actor_role']} must have mission"

    def test_target_terms_declared(self, world_def):
        """Competitive mode must declare target_terms (one per role)."""
        targets = world_def["game"]["entities"]["target_terms"]
        assert len(targets) == 2
        roles = {t["actor_role"] for t in targets}
        assert roles == {"buyer", "supplier"}
        for target in targets:
            assert target["deal_id"] == "deal-q3-steel"
            assert "ideal_terms" in target
            assert "term_weights" in target
            assert "term_ranges" in target
            assert target["batna_score"] > 0


# ---------------------------------------------------------------------------
# Win conditions
# ---------------------------------------------------------------------------


class TestWinConditions:
    def test_natural_win_conditions_declared(self, world_def):
        types = {w["type"] for w in world_def["game"]["win_conditions"]}
        assert "deal_closed" in types
        assert "deal_rejected" in types

    def test_timeout_win_conditions_declared(self, world_def):
        types = {w["type"] for w in world_def["game"]["win_conditions"]}
        assert "stalemate_timeout" in types
        assert "wall_clock_elapsed" in types
        assert "max_events_exceeded" in types
        assert "all_budgets_exhausted" in types

    def test_competitive_score_threshold(self, world_def):
        """Competitive mode may declare score_threshold (filtered in behavioral)."""
        types = {w["type"] for w in world_def["game"]["win_conditions"]}
        assert "score_threshold" in types


# ---------------------------------------------------------------------------
# Agents blueprint — roles + permissions
# ---------------------------------------------------------------------------


class TestAgentsBlueprint:
    def test_two_roles_declared(self, agents_def):
        roles = {a["role"] for a in agents_def["agents"]}
        assert roles == {"buyer", "supplier"}

    def test_both_roles_have_game_write_permission(self, agents_def):
        for agent in agents_def["agents"]:
            write = set(agent["permissions"]["write"])
            assert "game" in write, f"Agent {agent['role']} missing 'game' write permission"

    def test_both_roles_have_slack_permissions(self, agents_def):
        for agent in agents_def["agents"]:
            read = set(agent["permissions"]["read"])
            write = set(agent["permissions"]["write"])
            assert "slack" in read
            assert "slack" in write


# ---------------------------------------------------------------------------
# End-to-end parser compile
# ---------------------------------------------------------------------------


class TestParserCompile:
    """Parse through YAMLParser to validate the Pydantic shape."""

    @pytest.mark.asyncio
    async def test_yaml_parser_produces_plan(self, compiled_plan):
        assert compiled_plan is not None
        assert compiled_plan.game is not None
        assert compiled_plan.game.enabled is True
        assert compiled_plan.game.scoring_mode == "competitive"

    @pytest.mark.asyncio
    async def test_compiled_plan_has_flow_config(self, compiled_plan):
        flow = compiled_plan.game.flow
        assert flow.type == "event_driven"
        assert flow.activation_mode == "serial"
        assert flow.first_mover == "buyer"

    @pytest.mark.asyncio
    async def test_compiled_plan_has_game_entities(self, compiled_plan):
        entities = compiled_plan.game.entities
        assert len(entities.deals) == 1
        assert len(entities.player_briefs) == 2
        assert len(entities.target_terms) == 2  # competitive mode
