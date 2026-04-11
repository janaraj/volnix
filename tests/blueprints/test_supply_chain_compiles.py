"""Compile smoke test for supply_chain_disruption.yaml.

Verifies the blueprint parses cleanly into a WorldPlan and asserts the
structural invariants the scenario depends on:

- 3 communication services + 1 notion service (single instance)
- Behavior is "dynamic", reality is "messy" with volatility/urgency overrides
- Animator is configured with ``at_time`` scheduled events (not triggers)
- ``negotiation_fields`` are declared with the expected shape and enums
- Agents blueprint declares the two player roles with scoped permissions
- Visibility rules are seeded for both actors

This is a static YAML-parse test — it does NOT run the LLM seed
expander, so it can run in CI without network access or LLM calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORLD_YAML = REPO_ROOT / "volnix/blueprints/official/supply_chain_disruption.yaml"
AGENTS_YAML = REPO_ROOT / "volnix/blueprints/official/agents_supply_chain.yaml"


@pytest.fixture(scope="module")
def world_def() -> dict:
    """Load the supply chain world YAML as a dict."""
    with WORLD_YAML.open() as f:
        data = yaml.safe_load(f)
    assert "world" in data, "Top-level 'world' key missing"
    return data["world"]


@pytest.fixture(scope="module")
def agents_def() -> dict:
    """Load the supply chain agents YAML as a dict."""
    with AGENTS_YAML.open() as f:
        data = yaml.safe_load(f)
    assert "agents" in data, "Top-level 'agents' key missing"
    return data


# ---------------------------------------------------------------------------
# Services — single notion instance + comms
# ---------------------------------------------------------------------------


def test_services_single_notion_plus_comms(world_def):
    """We use ONE notion instance (with visibility_rule data separation),
    not multiple — the three-instance pattern was rejected in the P5 gate.
    """
    services = world_def.get("services", {})
    assert "notion" in services
    assert services["notion"] == "verified/notion"

    # Must NOT have any notion_* variants (leftover from the earlier draft)
    notion_variants = [s for s in services if s.startswith("notion_") and s != "notion"]
    assert notion_variants == [], (
        f"Found extra notion service instances {notion_variants}. "
        f"The P5-approved pattern is ONE notion service with visibility_rule "
        f"entities for data separation, not multiple service instances."
    )

    # Expected auxiliary comms services
    for svc in ("twitter", "gmail", "slack"):
        assert svc in services, f"Missing required service: {svc}"


# ---------------------------------------------------------------------------
# Reality + behavior
# ---------------------------------------------------------------------------


def test_behavior_is_dynamic(world_def):
    """The supply chain scenario relies on the animator being active."""
    assert world_def.get("behavior") == "dynamic"


def test_reality_preset_messy_with_overrides(world_def):
    """Messy preset + volatility/urgency overrides drive the animator."""
    reality = world_def.get("reality", {})
    assert reality.get("preset") == "messy"

    complexity = reality.get("complexity", {})
    assert complexity.get("volatility", 0) >= 70, (
        "Volatility should be high (>=70) to drive dynamic world events"
    )
    assert complexity.get("urgency", 0) >= 75, (
        "Urgency should be high (>=75) to drive time pressure"
    )


# ---------------------------------------------------------------------------
# Animator — at_time scheduled events, no triggers
# ---------------------------------------------------------------------------


def test_animator_declared(world_def):
    """The world.animator block exists and is configured."""
    animator = world_def.get("animator")
    assert animator is not None, "Missing world.animator block"
    assert animator.get("creativity") == "high"
    assert animator.get("event_frequency") == "frequent"
    assert animator.get("creativity_budget_per_tick", 0) >= 2


def test_animator_scheduled_events_use_at_time_not_triggers(world_def):
    """Scheduled events use the at_time format (P2), not broken triggers.

    The P5 review found that trigger-based events are non-functional
    (ConditionEvaluator blocks function calls) for anything but trivial
    literal expressions. The canonical pattern is at_time for
    deterministic beats + organic generation for the gaps.
    """
    scheduled = world_def["animator"].get("scheduled_events", [])
    assert len(scheduled) >= 4, (
        f"Expected at least 4 scheduled events (storm escalation, port "
        f"closure, news tweet, competitor inquiry). Got {len(scheduled)}."
    )

    for ev in scheduled:
        assert "at_time" in ev, (
            f"Scheduled event missing 'at_time' key — triggers are "
            f"disallowed in this blueprint. Event: {ev}"
        )
        assert "trigger" not in ev, (
            f"Trigger-based events are non-functional for state queries. "
            f"Use at_time instead. Event: {ev}"
        )
        # Each must have actor_id, service_id, action
        assert ev.get("actor_id"), f"Missing actor_id: {ev}"
        assert ev.get("service_id"), f"Missing service_id: {ev}"
        assert ev.get("action"), f"Missing action: {ev}"


def test_animator_scheduled_events_progression(world_def):
    """The scheduled events form a storm-escalation narrative.

    Expected beats (wall-clock offsets from animator start):
    - T+60s: storm escalates to Tropical Storm
    - T+120s: storm becomes Category 1 typhoon
    - T+125s: Haiphong port closes
    - T+130s: Reuters breaking news
    - T+200s: competing buyer inquiry for the supplier
    """
    scheduled = world_def["animator"].get("scheduled_events", [])
    at_times = [ev["at_time"] for ev in scheduled]

    # Must have the key beats (exact offsets may shift in tuning; these
    # are the minimum-viable narrative markers)
    assert any("60s" in t for t in at_times), "Missing T+60s beat"
    assert any("120s" in t for t in at_times), "Missing T+120s beat"
    assert any("125s" in t for t in at_times), "Missing T+125s beat"
    assert any("130s" in t for t in at_times), "Missing T+130s beat"
    assert any("200s" in t for t in at_times), "Missing T+200s beat"


def test_animator_state_snapshot_excludes_game_internals(world_def):
    """Game-internal entity types must be excluded from the animator snapshot.

    Ensures the organic LLM animator doesn't see private game state
    (``negotiation_target_terms``, ``negotiation_proposal``,
    ``negotiation_deal``, ``game_player_brief``) which would leak
    player intent into the organic events. Also excludes
    ``visibility_rule`` to avoid teaching the LLM about the
    permission model.
    """
    exclude = world_def["animator"].get("state_snapshot_exclude", [])
    for required_exclude in (
        "negotiation_target_terms",
        "negotiation_proposal",
        "negotiation_deal",
        "game_player_brief",
        "visibility_rule",
    ):
        assert required_exclude in exclude, (
            f"Missing {required_exclude} from state_snapshot_exclude. "
            f"Animator would leak game-internal state to the organic LLM."
        )


# ---------------------------------------------------------------------------
# Negotiation type_config — generic schema from Phase P1
# ---------------------------------------------------------------------------


def test_negotiation_fields_declared(world_def):
    """game.type_config.negotiation_fields declares the domain schema."""
    game = world_def.get("game", {})
    type_config = game.get("type_config", {})
    fields = type_config.get("negotiation_fields", [])

    assert len(fields) == 6, f"Expected 6 fields, got {len(fields)}: {fields}"

    field_names = {f["name"] for f in fields}
    expected = {
        "unit_price",
        "quantity_units",
        "delivery_lead_days",
        "payment_terms_days",
        "freight_mode",
        "late_penalty_pct",
    }
    assert field_names == expected, f"Field name mismatch. Expected {expected}, got {field_names}"


def test_negotiation_fields_have_correct_types(world_def):
    """Each declared field has the correct JSON Schema primitive type."""
    fields = world_def["game"]["type_config"]["negotiation_fields"]
    type_by_name = {f["name"]: f["type"] for f in fields}

    assert type_by_name["unit_price"] == "number"
    assert type_by_name["quantity_units"] == "integer"
    assert type_by_name["delivery_lead_days"] == "integer"
    assert type_by_name["payment_terms_days"] == "integer"
    assert type_by_name["freight_mode"] == "string"
    assert type_by_name["late_penalty_pct"] == "number"


def test_freight_mode_has_enum(world_def):
    """freight_mode is a string enum with the three shipping modes."""
    fields = world_def["game"]["type_config"]["negotiation_fields"]
    freight = next(f for f in fields if f["name"] == "freight_mode")
    assert freight.get("enum") == ["sea", "air", "rail"]


def test_game_flow_and_scoring_mode(world_def):
    """Event-driven flow with behavioral scoring mode."""
    game = world_def.get("game", {})
    assert game.get("enabled") is True
    assert game.get("mode") == "negotiation"
    assert game.get("scoring_mode") == "behavioral"

    flow = game.get("flow", {})
    assert flow.get("type") == "event_driven"
    assert flow.get("max_events", 0) > 0
    assert flow.get("first_mover") == "nimbus_buyer"
    assert flow.get("activation_mode") == "serial"


def test_game_entities_declare_deal_and_briefs(world_def):
    """game.entities declares the deal + per-player briefs."""
    game = world_def.get("game", {})
    entities = game.get("entities", {})

    deals = entities.get("deals", [])
    assert len(deals) == 1
    deal = deals[0]
    assert deal["id"] == "deal-pwr7a-2026q2"
    assert set(deal["parties"]) == {"nimbus_buyer", "haiphong_supplier"}

    briefs = entities.get("player_briefs", [])
    assert len(briefs) == 2
    brief_roles = {b["actor_role"] for b in briefs}
    assert brief_roles == {"nimbus_buyer", "haiphong_supplier"}
    for brief in briefs:
        assert brief["deal_id"] == "deal-pwr7a-2026q2"
        assert brief.get("brief_content"), f"Brief for {brief['actor_role']} must have content"


def test_game_behavioral_mode_has_no_target_terms(world_def):
    """Behavioral mode must NOT declare target_terms (MF3 invariant)."""
    game = world_def.get("game", {})
    entities = game.get("entities", {})
    target_terms = entities.get("target_terms", [])
    assert target_terms == [], (
        "Behavioral scoring mode must not declare target_terms. "
        "Those fields are competitive-mode-only and would be silently "
        "dropped at materialization."
    )


# ---------------------------------------------------------------------------
# Seeds — visibility rules + owner_role pattern
# ---------------------------------------------------------------------------


def test_seeds_include_visibility_rules_for_both_agents(world_def):
    """The visibility_rule seeds are the mechanism enforcing data separation.

    Without them, both agents would see everything (the permission
    engine's ``_query_with_visibility`` returns all entities when no
    rules are defined for the actor role — backward compat behavior).
    This test is the critical regression guard: if a blueprint author
    removes these seeds the data isolation silently breaks.
    """
    seeds = world_def.get("seeds", [])
    seeds_text = "\n".join(str(s) for s in seeds)

    # Both actor roles must appear in the visibility rules
    assert "nimbus_buyer" in seeds_text
    assert "haiphong_supplier" in seeds_text

    # Explicit visibility_rule mention
    assert "visibility_rule" in seeds_text, (
        "Seeds must create visibility_rule entities to enforce data "
        "separation. Without these, the buyer and supplier see all data."
    )

    # owner_role field must be mentioned (it's the filter the rules use)
    assert "owner_role" in seeds_text, (
        "Seeds must set an owner_role field on each private entity so "
        "the visibility rules can filter by it."
    )


def test_seeds_declare_public_buyer_and_supplier_scopes(world_def):
    """Seeds describe three data scopes: public, nimbus_buyer, haiphong_supplier."""
    seeds_text = "\n".join(str(s) for s in world_def.get("seeds", []))
    assert 'owner_role "public"' in seeds_text or "owner_role: public" in seeds_text
    assert 'owner_role "nimbus_buyer"' in seeds_text or "owner_role: nimbus_buyer" in seeds_text
    assert (
        'owner_role "haiphong_supplier"' in seeds_text
        or "owner_role: haiphong_supplier" in seeds_text
    )


def test_seeds_do_not_duplicate_game_entities(world_def):
    """Game entities live in ``game.entities``, not in ``seeds``.

    Cycle B moved game entity materialization from LLM-interpreted
    seeds into structured blueprint declarations. The world compiler
    materializes deals, player_briefs, and (competitive only)
    target_terms directly from ``game.entities`` in B.8.
    """
    seeds_text = "\n".join(str(s) for s in world_def.get("seeds", []))
    # Seeds should NOT declare any of these game entities — they're
    # materialized from game.entities instead
    assert "negotiation_deal" not in seeds_text
    assert "negotiation_target" not in seeds_text
    assert "negotiation_scorecard" not in seeds_text


# ---------------------------------------------------------------------------
# Agents blueprint — roles, permissions, model
# ---------------------------------------------------------------------------


def test_agents_declares_buyer_and_supplier(agents_def):
    agents = agents_def["agents"]
    roles = {a["role"] for a in agents}
    assert roles == {"nimbus_buyer", "haiphong_supplier"}


def test_agents_use_gemini_3_flash_preview(agents_def):
    """Both agents use gemini-3-flash-preview (latest Gemini Flash).

    Rationale: for the demo audience, using the latest model matters more
    than stability — people only pay attention to state-of-the-art. The
    multi-turn loop fix (prior PR 8a5cb43) addressed the tool-call
    dropping behavior we saw in earlier runs. Preview-model rate-limit
    flakiness is accepted as a trade-off.
    """
    for agent in agents_def["agents"]:
        model = agent["llm"]["model"]
        assert model == "gemini-3-flash-preview", (
            f"Agent {agent['role']} uses {model}, expected "
            f"gemini-3-flash-preview (the latest Gemini Flash — "
            f"the scenario is a public-facing demo)."
        )
        assert agent["llm"]["provider"] == "gemini"


def test_agents_have_scoped_permissions(agents_def):
    """Each agent has read:[slack,notion,...] and write:[slack,game].

    Data separation is achieved via visibility_rule seeds, not by
    scoping notion permissions. Both agents have ``read: [notion]``.
    """
    agents_by_role = {a["role"]: a for a in agents_def["agents"]}

    # Buyer
    buyer = agents_by_role["nimbus_buyer"]
    buyer_read = set(buyer["permissions"]["read"])
    buyer_write = set(buyer["permissions"]["write"])
    assert "slack" in buyer_read
    assert "notion" in buyer_read
    assert "twitter" in buyer_read
    assert "gmail" in buyer_read
    assert "slack" in buyer_write
    assert "game" in buyer_write

    # Supplier
    supplier = agents_by_role["haiphong_supplier"]
    supplier_read = set(supplier["permissions"]["read"])
    supplier_write = set(supplier["permissions"]["write"])
    assert "slack" in supplier_read
    assert "notion" in supplier_read
    assert "twitter" in supplier_read
    # Supplier does NOT have gmail (only the buyer has RFQ threads)
    assert "gmail" not in supplier_read
    assert "slack" in supplier_write
    assert "game" in supplier_write


def test_agent_personas_are_query_driven(agents_def):
    """Personas must instruct agents to QUERY for thresholds, not hardcode.

    The whole point of the scenario is evaluating agents reading the
    world. Hardcoded numbers in the persona text would let the agent
    anchor to them and skip queries.
    """
    for agent in agents_def["agents"]:
        personality = agent.get("personality", "")
        # Must mention that queries are required on every activation
        assert "query" in personality.lower()
        assert "every turn" in personality.lower() or "every activation" in personality.lower()
        # Must tell the agent NOT to hardcode
        assert "not hardcode" in personality.lower() or "do not hardcode" in personality.lower()
