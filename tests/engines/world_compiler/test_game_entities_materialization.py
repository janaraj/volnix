"""Tests for ``WorldCompilerEngine._materialize_game_entities``.

Validates Cycle B.8: game entities declared in ``plan.game.entities``
are compiled into ``all_entities`` so they land in the initial world
snapshot alongside seed-generated entities.

Invariants under test:

- ``negotiation_deal`` entities materialized from ``deals``
- ``page`` (notion) + ``game_player_brief`` + visibility rules
  materialized from ``player_briefs`` (MF3)
- ``negotiation_target_terms`` materialized ONLY in competitive mode
  (behavioral mode silently drops them to protect
  ``BehavioralScorer`` from ever reading competitive fields)
- ``scoring_mode="behavioral"`` logs an info message when dropping
  target_terms
- Disabled game definition is a no-op
- Empty entity config is a no-op
- Deal identities, party lists, and consent state match the blueprint

yaml_parser warnings are covered by ``test_yaml_parser.py`` additions.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from volnix.engines.game.definition import (
    DealDecl,
    GameDefinition,
    GameEntitiesConfig,
    PlayerBriefDecl,
    TargetTermsDecl,
)
from volnix.engines.world_compiler.engine import WorldCompilerEngine
from volnix.engines.world_compiler.plan import WorldPlan


async def _make_engine() -> WorldCompilerEngine:
    engine = WorldCompilerEngine()
    await engine.initialize({}, AsyncMock())
    return engine


def _make_plan(
    *,
    enabled: bool = True,
    scoring_mode: str = "behavioral",
    deals: list[DealDecl] | None = None,
    briefs: list[PlayerBriefDecl] | None = None,
    target_terms: list[TargetTermsDecl] | None = None,
) -> WorldPlan:
    return WorldPlan(
        name="test-game",
        description="",
        game=GameDefinition(
            enabled=enabled,
            mode="negotiation",
            scoring_mode=scoring_mode,  # type: ignore[arg-type]
            entities=GameEntitiesConfig(
                deals=deals or [],
                player_briefs=briefs or [],
                target_terms=target_terms or [],
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Disabled / no-op cases
# ---------------------------------------------------------------------------


class TestNoOpCases:
    @pytest.mark.asyncio
    async def test_disabled_game_is_noop(self):
        engine = await _make_engine()
        plan = _make_plan(enabled=False, deals=[DealDecl(id="d1", parties=["a", "b"])])
        all_entities: dict = {}
        count = engine._materialize_game_entities(plan, all_entities)
        assert count == 0
        assert all_entities == {}

    @pytest.mark.asyncio
    async def test_no_game_config_is_noop(self):
        engine = await _make_engine()
        plan = WorldPlan(name="no-game")  # plan.game is None
        all_entities: dict = {}
        count = engine._materialize_game_entities(plan, all_entities)
        assert count == 0

    @pytest.mark.asyncio
    async def test_empty_entities_is_noop(self):
        engine = await _make_engine()
        plan = _make_plan(deals=[], briefs=[], target_terms=[])
        all_entities: dict = {}
        count = engine._materialize_game_entities(plan, all_entities)
        assert count == 0
        assert all_entities == {}


# ---------------------------------------------------------------------------
# Deals
# ---------------------------------------------------------------------------


class TestDealMaterialization:
    @pytest.mark.asyncio
    async def test_single_deal_materialized(self):
        engine = await _make_engine()
        plan = _make_plan(
            deals=[
                DealDecl(
                    id="deal-q3",
                    title="Q3 Steel Supply",
                    parties=["buyer", "supplier"],
                    status="open",
                    terms_template={"price": {"range": [80, 120]}},
                )
            ]
        )
        all_entities: dict = {}
        count = engine._materialize_game_entities(plan, all_entities)
        assert count == 1
        deals = all_entities["negotiation_deal"]
        assert len(deals) == 1
        d = deals[0]
        assert d["id"] == "deal-q3"
        assert d["title"] == "Q3 Steel Supply"
        assert d["parties"] == ["buyer", "supplier"]
        assert d["status"] == "open"
        assert d["consent_rule"] == "unanimous"
        assert d["consent_by"] == []

    @pytest.mark.asyncio
    async def test_multiple_deals_materialized(self):
        engine = await _make_engine()
        plan = _make_plan(deals=[DealDecl(id=f"deal-{i}", parties=["a", "b"]) for i in range(3)])
        all_entities: dict = {}
        count = engine._materialize_game_entities(plan, all_entities)
        assert count == 3
        ids = [d["id"] for d in all_entities["negotiation_deal"]]
        assert ids == ["deal-0", "deal-1", "deal-2"]

    @pytest.mark.asyncio
    async def test_deal_terms_preserved_as_copy(self):
        """Deltas on the emitted deal don't mutate the blueprint DealDecl."""
        engine = await _make_engine()
        decl = DealDecl(id="d1", parties=["a", "b"], terms={"price": 85})
        plan = _make_plan(deals=[decl])
        all_entities: dict = {}
        engine._materialize_game_entities(plan, all_entities)
        emitted = all_entities["negotiation_deal"][0]
        emitted["terms"]["price"] = 999  # mutate the copy
        assert decl.terms == {"price": 85}  # original unchanged

    @pytest.mark.asyncio
    async def test_deal_appends_not_overwrites_existing(self):
        """Materialization appends to existing negotiation_deal list."""
        engine = await _make_engine()
        plan = _make_plan(deals=[DealDecl(id="new-deal", parties=["a", "b"])])
        all_entities: dict = {"negotiation_deal": [{"id": "seed-deal", "parties": ["c", "d"]}]}
        engine._materialize_game_entities(plan, all_entities)
        ids = [d["id"] for d in all_entities["negotiation_deal"]]
        assert ids == ["seed-deal", "new-deal"]


# ---------------------------------------------------------------------------
# Player briefs (page + game_player_brief + visibility rules)
# ---------------------------------------------------------------------------


class TestPlayerBriefMaterialization:
    @pytest.mark.asyncio
    async def test_brief_creates_notion_page(self):
        engine = await _make_engine()
        plan = _make_plan(
            briefs=[
                PlayerBriefDecl(
                    actor_role="buyer",
                    deal_id="deal-q3",
                    brief_content="You are Dana.",
                    mission="Close the best deal",
                )
            ]
        )
        all_entities: dict = {}
        engine._materialize_game_entities(plan, all_entities)
        pages = all_entities.get("page", [])
        assert len(pages) == 1
        p = pages[0]
        assert p["id"] == "brief-buyer-deal-q3"
        assert p["object"] == "page"
        assert p["owner_role"] == "buyer"
        assert p["content"] == "You are Dana."
        assert p["mission"] == "Close the best deal"
        assert p["properties"]["title"][0]["text"]["content"] == "Brief — buyer"

    @pytest.mark.asyncio
    async def test_brief_creates_game_player_brief_entity(self):
        engine = await _make_engine()
        plan = _make_plan(
            briefs=[
                PlayerBriefDecl(
                    actor_role="supplier",
                    deal_id="deal-q3",
                    brief_content="You are Linh.",
                    prohibited_actions=["negotiate_accept"],
                )
            ]
        )
        all_entities: dict = {}
        engine._materialize_game_entities(plan, all_entities)
        gpbs = all_entities.get("game_player_brief", [])
        assert len(gpbs) == 1
        gpb = gpbs[0]
        assert gpb["id"] == "gpb-supplier-deal-q3"
        assert gpb["actor_role"] == "supplier"
        assert gpb["deal_id"] == "deal-q3"
        assert gpb["owner_role"] == "supplier"
        assert gpb["brief_content"] == "You are Linh."
        assert gpb["prohibited_actions"] == ["negotiate_accept"]
        assert gpb["notion_page_id"] == "brief-supplier-deal-q3"

    @pytest.mark.asyncio
    async def test_brief_creates_two_visibility_rules(self):
        """One for the page, one for the game_player_brief entity."""
        engine = await _make_engine()
        plan = _make_plan(
            briefs=[PlayerBriefDecl(actor_role="buyer", deal_id="d1", brief_content="")]
        )
        all_entities: dict = {}
        engine._materialize_game_entities(plan, all_entities)
        rules = all_entities.get("visibility_rule", [])
        assert len(rules) == 2
        entity_types = {r["entity_type"] for r in rules}
        assert entity_types == {"page", "game_player_brief"}
        for rule in rules:
            assert rule["actor_role"] == "buyer"

    @pytest.mark.asyncio
    async def test_brief_count_is_4_entities_each(self):
        """Each brief creates 4 entities: page + gpb + 2 visibility rules."""
        engine = await _make_engine()
        plan = _make_plan(
            briefs=[
                PlayerBriefDecl(actor_role="buyer", deal_id="d1", brief_content=""),
                PlayerBriefDecl(actor_role="supplier", deal_id="d1", brief_content=""),
            ]
        )
        all_entities: dict = {}
        count = engine._materialize_game_entities(plan, all_entities)
        assert count == 8  # 2 briefs × 4 entities


# ---------------------------------------------------------------------------
# Target terms (competitive vs behavioral)
# ---------------------------------------------------------------------------


class TestTargetTermsMaterialization:
    @pytest.mark.asyncio
    async def test_competitive_mode_materializes_target_terms(self):
        engine = await _make_engine()
        plan = _make_plan(
            scoring_mode="competitive",
            target_terms=[
                TargetTermsDecl(
                    actor_role="buyer",
                    deal_id="deal-q3",
                    ideal_terms={"price": 85},
                    term_weights={"price": 1.0},
                    term_ranges={"price": [80.0, 120.0]},
                    batna_score=40.0,
                )
            ],
        )
        all_entities: dict = {}
        engine._materialize_game_entities(plan, all_entities)
        tts = all_entities.get("negotiation_target_terms", [])
        assert len(tts) == 1
        t = tts[0]
        assert t["id"] == "tt-buyer-deal-q3"
        assert t["actor_role"] == "buyer"
        assert t["deal_id"] == "deal-q3"
        assert t["ideal_terms"] == {"price": 85}
        assert t["term_weights"] == {"price": 1.0}
        assert t["term_ranges"] == {"price": [80.0, 120.0]}
        assert t["batna_score"] == 40.0

    @pytest.mark.asyncio
    async def test_behavioral_mode_drops_target_terms(self):
        """Critical invariant (MF3): behavioral mode never materializes target_terms."""
        engine = await _make_engine()
        plan = _make_plan(
            scoring_mode="behavioral",
            target_terms=[
                TargetTermsDecl(
                    actor_role="buyer",
                    deal_id="d1",
                    ideal_terms={"price": 85},
                    batna_score=40.0,
                )
            ],
        )
        all_entities: dict = {}
        engine._materialize_game_entities(plan, all_entities)
        assert "negotiation_target_terms" not in all_entities

    @pytest.mark.asyncio
    async def test_behavioral_mode_logs_when_dropping(self, caplog):
        """Behavioral mode logs an info message when target_terms are declared."""
        engine = await _make_engine()
        plan = _make_plan(
            scoring_mode="behavioral",
            target_terms=[
                TargetTermsDecl(actor_role="buyer", deal_id="d1"),
                TargetTermsDecl(actor_role="supplier", deal_id="d1"),
            ],
        )
        all_entities: dict = {}
        with caplog.at_level("INFO", logger="volnix.engines.world_compiler.engine"):
            engine._materialize_game_entities(plan, all_entities)
        assert any("Dropping 2 target_terms entries" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_competitive_mode_with_no_target_terms_is_fine(self):
        """Competitive mode doesn't require target_terms (scorer handles empty)."""
        engine = await _make_engine()
        plan = _make_plan(scoring_mode="competitive", target_terms=[])
        all_entities: dict = {}
        engine._materialize_game_entities(plan, all_entities)
        assert "negotiation_target_terms" not in all_entities


# ---------------------------------------------------------------------------
# End-to-end: realistic blueprint shape
# ---------------------------------------------------------------------------


class TestRealisticBlueprint:
    @pytest.mark.asyncio
    async def test_q3_steel_style_blueprint(self):
        """Mimics the Q3 Steel blueprint: 1 deal, 2 briefs, 2 target terms, competitive."""
        engine = await _make_engine()
        plan = _make_plan(
            scoring_mode="competitive",
            deals=[
                DealDecl(
                    id="deal-q3-steel",
                    title="Q3 Steel Supply",
                    parties=["buyer", "supplier"],
                )
            ],
            briefs=[
                PlayerBriefDecl(
                    actor_role="buyer",
                    deal_id="deal-q3-steel",
                    brief_content="Max $95/ton",
                    mission="Minimize cost",
                ),
                PlayerBriefDecl(
                    actor_role="supplier",
                    deal_id="deal-q3-steel",
                    brief_content="Floor $75/ton",
                    mission="Maximize revenue",
                ),
            ],
            target_terms=[
                TargetTermsDecl(
                    actor_role="buyer",
                    deal_id="deal-q3-steel",
                    ideal_terms={"price": 85},
                    batna_score=40.0,
                ),
                TargetTermsDecl(
                    actor_role="supplier",
                    deal_id="deal-q3-steel",
                    ideal_terms={"price": 110},
                    batna_score=40.0,
                ),
            ],
        )
        all_entities: dict = {}
        count = engine._materialize_game_entities(plan, all_entities)
        # 1 deal + 2×(page + gpb + 2 visibility rules) + 2 target_terms
        assert count == 1 + 8 + 2
        assert len(all_entities["negotiation_deal"]) == 1
        assert len(all_entities["page"]) == 2
        assert len(all_entities["game_player_brief"]) == 2
        assert len(all_entities["visibility_rule"]) == 4
        assert len(all_entities["negotiation_target_terms"]) == 2

    @pytest.mark.asyncio
    async def test_behavioral_supply_chain_style_blueprint(self):
        """Mimics supply_chain_disruption: 1 deal, 2 briefs, no target terms."""
        engine = await _make_engine()
        plan = _make_plan(
            scoring_mode="behavioral",
            deals=[DealDecl(id="deal-pwr7a", parties=["nimbus_buyer", "haiphong_supplier"])],
            briefs=[
                PlayerBriefDecl(
                    actor_role="nimbus_buyer",
                    deal_id="deal-pwr7a",
                    brief_content="Procurement lead",
                ),
                PlayerBriefDecl(
                    actor_role="haiphong_supplier",
                    deal_id="deal-pwr7a",
                    brief_content="Sales director",
                ),
            ],
        )
        all_entities: dict = {}
        count = engine._materialize_game_entities(plan, all_entities)
        assert count == 1 + 8  # 1 deal + 2 briefs × 4
        assert "negotiation_target_terms" not in all_entities
