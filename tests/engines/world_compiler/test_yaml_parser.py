"""Tests for YAMLParser — world definition + compiler settings parsing."""

import pytest
import yaml

from volnix.core.errors import YAMLParseError
from volnix.engines.world_compiler.yaml_parser import YAMLParser
from volnix.reality.dimensions import WorldConditions

# ---------------------------------------------------------------------------
# File-based parsing
# ---------------------------------------------------------------------------


class TestYAMLParserFromFile:
    """Parse YAML from files on disk."""

    @pytest.mark.asyncio
    async def test_parse_minimal_file(self, tmp_path, condition_expander):
        """Parse a minimal world YAML file."""
        world_file = tmp_path / "world.yaml"
        world_file.write_text(
            yaml.dump(
                {
                    "world": {
                        "name": "File World",
                        "description": "From file",
                        "services": {"gmail": "verified/gmail"},
                        "actors": [{"role": "agent", "type": "external", "count": 1}],
                    }
                }
            )
        )
        parser = YAMLParser(condition_expander)
        plan, specs = await parser.parse(str(world_file))

        assert plan.name == "File World"
        assert plan.source == "yaml"
        assert "gmail" in specs
        assert specs["gmail"] == "verified/gmail"

    @pytest.mark.asyncio
    async def test_parse_with_compiler_settings(self, tmp_path, condition_expander):
        """Parse world + compiler settings from separate files."""
        world_file = tmp_path / "world.yaml"
        world_file.write_text(
            yaml.dump(
                {
                    "world": {
                        "name": "Dual File",
                        "services": {"gmail": "verified/gmail"},
                        "actors": [],
                    }
                }
            )
        )
        settings_file = tmp_path / "settings.yaml"
        settings_file.write_text(
            yaml.dump(
                {
                    "compiler": {
                        "seed": 99,
                        "behavior": "static",
                        "fidelity": "strict",
                        "mode": "governed",
                        "reality": {"preset": "ideal"},
                    }
                }
            )
        )
        parser = YAMLParser(condition_expander)
        plan, specs = await parser.parse(str(world_file), str(settings_file))

        assert plan.seed == 99
        assert plan.behavior == "static"
        assert plan.fidelity == "strict"

    @pytest.mark.asyncio
    async def test_parse_missing_file_raises(self, condition_expander):
        """Parsing a non-existent file raises YAMLParseError."""
        parser = YAMLParser(condition_expander)
        with pytest.raises(YAMLParseError, match="not found"):
            await parser.parse("/nonexistent/world.yaml")

    @pytest.mark.asyncio
    async def test_parse_invalid_yaml_raises(self, tmp_path, condition_expander):
        """Parsing invalid YAML raises YAMLParseError."""
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("{{{{not: valid: yaml: {{{{")
        parser = YAMLParser(condition_expander)
        with pytest.raises(YAMLParseError, match="Invalid YAML"):
            await parser.parse(str(bad_file))


# ---------------------------------------------------------------------------
# Dict-based parsing
# ---------------------------------------------------------------------------


class TestYAMLParserFromDicts:
    """Parse from pre-loaded dicts (e.g. from NL parser output)."""

    @pytest.mark.asyncio
    async def test_parse_from_dicts(
        self, condition_expander, sample_world_def, sample_compiler_settings
    ):
        """Basic dict parsing produces correct WorldPlan fields."""
        parser = YAMLParser(condition_expander)
        plan, specs = await parser.parse_from_dicts(sample_world_def, sample_compiler_settings)

        assert plan.name == "Test World"
        assert plan.seed == 42
        assert plan.behavior == "dynamic"
        assert plan.services == {}  # empty — not resolved yet
        assert "gmail" in specs

    @pytest.mark.asyncio
    async def test_service_reference_formats(self, condition_expander):
        """All service reference formats are extracted correctly."""
        world_def = {
            "world": {
                "name": "Multi-Service",
                "services": {
                    "gmail": "verified/gmail",
                    "stripe": "profiled/stripe",
                    "jira": "jira",  # bare name
                    "web": {"provider": "verified/browser", "sites": ["example.com"]},
                },
                "actors": [],
            }
        }
        parser = YAMLParser(condition_expander)
        plan, specs = await parser.parse_from_dicts(world_def)

        assert specs["gmail"] == "verified/gmail"
        assert specs["stripe"] == "profiled/stripe"
        assert specs["jira"] == "jira"
        assert isinstance(specs["web"], dict)
        assert specs["web"]["provider"] == "verified/browser"

    @pytest.mark.asyncio
    async def test_actor_preservation(self, condition_expander):
        """Actor specs are preserved with all YAML fields intact."""
        world_def = {
            "world": {
                "name": "Actors",
                "services": {},
                "actors": [
                    {"role": "agent", "type": "external", "count": 2, "personality": "helpful"},
                    {"role": "customer", "type": "internal", "count": 50, "frustration": "high"},
                ],
            }
        }
        parser = YAMLParser(condition_expander)
        plan, _ = await parser.parse_from_dicts(world_def)

        assert len(plan.actor_specs) == 2
        assert plan.actor_specs[0]["role"] == "agent"
        assert plan.actor_specs[0]["personality"] == "helpful"
        assert plan.actor_specs[1]["frustration"] == "high"

    @pytest.mark.asyncio
    async def test_policy_parsing(self, condition_expander):
        """Policies from world def are carried through."""
        world_def = {
            "world": {
                "name": "Policies",
                "services": {},
                "actors": [],
                "policies": [
                    {"name": "No refund without approval", "enforcement": "hold"},
                ],
            }
        }
        parser = YAMLParser(condition_expander)
        plan, _ = await parser.parse_from_dicts(world_def)

        assert len(plan.policies) == 1
        assert plan.policies[0]["name"] == "No refund without approval"
        assert plan.policies[0]["enforcement"] == "hold"

    @pytest.mark.asyncio
    async def test_seed_extraction(self, condition_expander):
        """Seeds from world def are carried through."""
        world_def = {
            "world": {
                "name": "Seeds",
                "services": {},
                "actors": [],
                "seeds": ["VIP customer waiting for refund", "Agent on break"],
            }
        }
        parser = YAMLParser(condition_expander)
        plan, _ = await parser.parse_from_dicts(world_def)

        assert len(plan.seeds) == 2
        assert "VIP customer" in plan.seeds[0]

    @pytest.mark.asyncio
    async def test_reality_expansion(self, condition_expander):
        """Reality preset is expanded into WorldConditions via D1."""
        settings = {
            "compiler": {
                "reality": {"preset": "hostile"},
            }
        }
        world_def = {"world": {"name": "Hostile", "services": {}, "actors": []}}
        parser = YAMLParser(condition_expander)
        plan, _ = await parser.parse_from_dicts(world_def, settings)

        # Hostile preset should have high friction values
        assert plan.conditions.friction.hostile > 0
        # Prompt context should be populated
        assert "dimensions" in plan.reality_prompt_context

    @pytest.mark.asyncio
    async def test_defaults_when_no_settings(self, condition_expander):
        """Default compiler values used when no settings provided."""
        world_def = {"world": {"name": "Minimal", "services": {}, "actors": []}}
        parser = YAMLParser(condition_expander)
        plan, _ = await parser.parse_from_dicts(world_def)

        assert plan.seed == 42
        assert plan.behavior == "dynamic"
        assert plan.fidelity == "auto"
        assert plan.mode == "governed"
        # Default reality is messy
        assert isinstance(plan.conditions, WorldConditions)


# ---------------------------------------------------------------------------
# Fixture file integration tests
# ---------------------------------------------------------------------------


class TestYAMLParserFixtures:
    """Parse real YAML fixture files."""

    @pytest.mark.asyncio
    async def test_parse_acme_fixtures(self, condition_expander):
        """Parse the acme_support + acme_compiler fixture files end-to-end."""
        parser = YAMLParser(condition_expander)
        plan, specs = await parser.parse(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )
        assert plan.name == "Acme Support Organization"
        assert len(specs) >= 4  # email, chat, tickets, payments, web
        assert len(plan.actor_specs) >= 3  # support-agent, supervisor, customer
        assert len(plan.policies) >= 3
        assert len(plan.seeds) >= 3


# ---------------------------------------------------------------------------
# Game config validation (Cycle B.8.5 hardening — m3)
# ---------------------------------------------------------------------------


class TestGameConfigValidation:
    """Invalid game blocks raise YAMLParseError, not raw Pydantic errors."""

    @pytest.mark.asyncio
    async def test_invalid_max_events_raises_yaml_parse_error(self, condition_expander):
        parser = YAMLParser(condition_expander)
        world_def = {
            "world": {
                "name": "broken",
                "services": {},
                "actors": [],
                "game": {
                    "enabled": True,
                    "mode": "negotiation",
                    "flow": {
                        "type": "event_driven",
                        "max_events": "not-a-number",  # invalid
                    },
                    "entities": {
                        "deals": [{"id": "d1", "parties": ["a", "b"]}],
                    },
                },
            }
        }
        with pytest.raises(YAMLParseError, match="Invalid ``game`` section"):
            await parser.parse_from_dicts(world_def)

    @pytest.mark.asyncio
    async def test_unknown_scoring_mode_raises_yaml_parse_error(self, condition_expander):
        parser = YAMLParser(condition_expander)
        world_def = {
            "world": {
                "name": "broken",
                "services": {},
                "actors": [],
                "game": {
                    "enabled": True,
                    "scoring_mode": "leaderboard",  # not a valid Literal
                    "entities": {"deals": [{"id": "d1", "parties": ["a", "b"]}]},
                },
            }
        }
        with pytest.raises(YAMLParseError, match="Invalid ``game`` section"):
            await parser.parse_from_dicts(world_def)

    @pytest.mark.asyncio
    async def test_valid_game_config_parses_cleanly(self, condition_expander):
        parser = YAMLParser(condition_expander)
        world_def = {
            "world": {
                "name": "ok",
                "services": {},
                "actors": [],
                "game": {
                    "enabled": True,
                    "scoring_mode": "behavioral",
                    "flow": {
                        "type": "event_driven",
                        "max_events": 50,
                        "reactivity_window_events": 3,
                    },
                    "entities": {
                        "deals": [{"id": "d1", "parties": ["a", "b"]}],
                    },
                },
            }
        }
        plan, _ = await parser.parse_from_dicts(world_def)
        assert plan.game is not None
        assert plan.game.enabled is True
        assert plan.game.flow.reactivity_window_events == 3
        assert plan.game.flow.max_events == 50


class TestLegacyRoundKeysRejected:
    """NF8 (B-cleanup.3): legacy round-based keys raise YAMLParseError.

    Cycle B plan §3.3 mandated hard-reject on the legacy round-based
    keys (``rounds`` / ``turn_protocol`` / ``between_rounds`` /
    ``resource_reset_per_round``). The initial implementation shipped a
    soft-warn instead; B-cleanup.3 flipped it to the hard-reject per
    the plan.
    """

    @pytest.mark.asyncio
    async def test_rounds_key_raises(self, condition_expander):
        parser = YAMLParser(condition_expander)
        world_def = {
            "world": {
                "name": "legacy",
                "services": {},
                "actors": [],
                "game": {
                    "enabled": True,
                    "rounds": {"count": 8, "actions_per_turn": 3},
                    "entities": {"deals": [{"id": "d1", "parties": ["a", "b"]}]},
                },
            }
        }
        with pytest.raises(YAMLParseError, match="legacy round-based keys"):
            await parser.parse_from_dicts(world_def)

    @pytest.mark.asyncio
    async def test_turn_protocol_key_raises(self, condition_expander):
        parser = YAMLParser(condition_expander)
        world_def = {
            "world": {
                "name": "legacy",
                "services": {},
                "actors": [],
                "game": {
                    "enabled": True,
                    "turn_protocol": "round_robin",
                    "entities": {"deals": [{"id": "d1", "parties": ["a", "b"]}]},
                },
            }
        }
        with pytest.raises(YAMLParseError, match="legacy round-based keys"):
            await parser.parse_from_dicts(world_def)

    @pytest.mark.asyncio
    async def test_between_rounds_key_raises(self, condition_expander):
        parser = YAMLParser(condition_expander)
        world_def = {
            "world": {
                "name": "legacy",
                "services": {},
                "actors": [],
                "game": {
                    "enabled": True,
                    "between_rounds": {"announce_scores": True},
                    "entities": {"deals": [{"id": "d1", "parties": ["a", "b"]}]},
                },
            }
        }
        with pytest.raises(YAMLParseError, match="legacy round-based keys"):
            await parser.parse_from_dicts(world_def)

    @pytest.mark.asyncio
    async def test_resource_reset_per_round_key_raises(self, condition_expander):
        parser = YAMLParser(condition_expander)
        world_def = {
            "world": {
                "name": "legacy",
                "services": {},
                "actors": [],
                "game": {
                    "enabled": True,
                    "resource_reset_per_round": {"api_calls": 3},
                    "entities": {"deals": [{"id": "d1", "parties": ["a", "b"]}]},
                },
            }
        }
        with pytest.raises(YAMLParseError, match="legacy round-based keys"):
            await parser.parse_from_dicts(world_def)

    @pytest.mark.asyncio
    async def test_error_message_lists_all_rejected_keys(self, condition_expander):
        parser = YAMLParser(condition_expander)
        world_def = {
            "world": {
                "name": "legacy",
                "services": {},
                "actors": [],
                "game": {
                    "enabled": True,
                    "rounds": {"count": 8},
                    "turn_protocol": "round_robin",
                    "entities": {"deals": [{"id": "d1", "parties": ["a", "b"]}]},
                },
            }
        }
        with pytest.raises(YAMLParseError) as excinfo:
            await parser.parse_from_dicts(world_def)
        # Error should mention both rejected keys for actionable migration
        assert "rounds" in str(excinfo.value)
        assert "turn_protocol" in str(excinfo.value)
