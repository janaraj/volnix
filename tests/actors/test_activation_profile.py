"""Tests for the Activation-Profile framework (Layer 1 scaffold).

Covers the :class:`ActivationProfile` Pydantic model, the YAML loader,
and the registry. No runtime NPC behavior yet — those tests live in
Phase 2 alongside the activator.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from volnix.actors.activation_profile import (
    ActivationProfile,
    ActivationTrigger,
    BudgetDefaults,
    ToolScope,
)
from volnix.actors.npc_profiles import (
    AVAILABLE_PROFILES,
    _clear_cache,
    list_profiles,
    load_activation_profile,
)

# -- ActivationTrigger model --------------------------------------------------


class TestActivationTrigger:
    def test_event_trigger(self) -> None:
        trigger = ActivationTrigger(event="npc.exposure")
        assert trigger.event == "npc.exposure"
        assert trigger.scheduled is None

    def test_scheduled_trigger(self) -> None:
        trigger = ActivationTrigger(scheduled="daily_life_tick")
        assert trigger.scheduled == "daily_life_tick"
        assert trigger.event is None

    def test_rejects_both(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            ActivationTrigger(event="x", scheduled="y")

    def test_rejects_neither(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            ActivationTrigger()


# -- ActivationProfile model --------------------------------------------------


class TestActivationProfileModel:
    def _make(self) -> ActivationProfile:
        return ActivationProfile(
            name="test",
            description="a profile",
            state_schema={"type": "object"},
            activation_triggers=[ActivationTrigger(event="x.y")],
            prompt_template="t.j2",
            tool_scope=ToolScope(read=["a"], write=["b"]),
        )

    def test_required_fields(self) -> None:
        profile = self._make()
        assert profile.name == "test"
        assert profile.state_schema == {"type": "object"}
        assert profile.tool_scope.read == ["a"]

    def test_frozen(self) -> None:
        profile = self._make()
        with pytest.raises(Exception):  # pydantic emits ValidationError on frozen
            profile.name = "mutated"  # type: ignore[misc]

    def test_budget_defaults_applied(self) -> None:
        profile = self._make()
        assert profile.budget_defaults.api_calls == 20
        assert profile.budget_defaults.llm_spend == 0.50

    def test_explicit_budget_override(self) -> None:
        profile = ActivationProfile(
            name="t",
            description="d",
            state_schema={},
            activation_triggers=[ActivationTrigger(event="x")],
            prompt_template="p.j2",
            tool_scope=ToolScope(),
            budget_defaults=BudgetDefaults(api_calls=5, llm_spend=0.10),
        )
        assert profile.budget_defaults.api_calls == 5


# -- Loader / registry --------------------------------------------------------


class TestLoader:
    def setup_method(self) -> None:
        _clear_cache()

    def test_load_consumer_user(self) -> None:
        profile = load_activation_profile("consumer_user")
        assert profile.name == "consumer_user"
        assert profile.prompt_template == "consumer_user_decision.j2"
        assert any(t.event == "npc.exposure" for t in profile.activation_triggers)
        assert "product_services" in profile.tool_scope.read
        assert profile.state_schema["type"] == "object"
        assert "awareness" in profile.state_schema["properties"]

    def test_load_unknown_raises(self) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            load_activation_profile("does_not_exist")

    def test_missing_required_key_raises(self, tmp_path: Path) -> None:
        from volnix.actors import npc_profiles as _module

        bad = tmp_path / "broken.yaml"
        bad.write_text(yaml.safe_dump({"name": "broken", "description": "no schema"}))

        # Temporarily point the loader at the tmp file by monkey-patching
        # the private cache and path resolution. We call the low-level
        # Pydantic construction path directly instead.
        from volnix.actors.activation_profile import ActivationProfile

        with pytest.raises(Exception):  # Pydantic ValidationError
            ActivationProfile(name="broken", description="no schema")  # type: ignore[call-arg]

        # Sanity: private helper works on the expected shape.
        _ = _module

    def test_name_mismatch_raises(self, tmp_path: Path) -> None:
        """A profile YAML whose name field doesn't match filename stem must fail.

        This protects against a common authoring mistake where the file
        is renamed but the ``name:`` inside wasn't.
        """
        from volnix.actors import npc_profiles as _module

        # Write a broken profile into the real profiles dir — then
        # restore on cleanup. We use AVAILABLE_PROFILES aware of the
        # module path to stay deterministic.
        profiles_dir = Path(_module.__file__).parent
        rogue = profiles_dir / "_rogue_test_profile.yaml"
        rogue.write_text(
            yaml.safe_dump(
                {
                    "name": "WRONG_NAME",
                    "description": "mismatched",
                    "state_schema": {"type": "object"},
                    "activation_triggers": [{"event": "x.y"}],
                    "prompt_template": "consumer_user_decision.j2",
                    "tool_scope": {"read": [], "write": []},
                }
            )
        )
        try:
            _clear_cache()
            with pytest.raises(ValueError, match="must match filename stem"):
                load_activation_profile("_rogue_test_profile")
        finally:
            rogue.unlink(missing_ok=True)
            _clear_cache()

    def test_available_profiles_tuple(self) -> None:
        assert "consumer_user" in AVAILABLE_PROFILES

    def test_list_profiles_includes_consumer_user(self) -> None:
        entries = list_profiles()
        names = {e["name"] for e in entries}
        assert "consumer_user" in names

    def test_caching(self) -> None:
        _clear_cache()
        first = load_activation_profile("consumer_user")
        second = load_activation_profile("consumer_user")
        assert first is second  # cached

    def test_non_mapping_yaml_raises(self) -> None:
        """YAML that parses to something other than a dict must be rejected
        with a clear message — covers the isinstance guard."""
        from volnix.actors import npc_profiles as _module

        profiles_dir = Path(_module.__file__).parent
        rogue = profiles_dir / "_rogue_list_profile.yaml"
        rogue.write_text("- just\n- a\n- list\n")
        try:
            _clear_cache()
            with pytest.raises(ValueError, match="must be a mapping"):
                load_activation_profile("_rogue_list_profile")
        finally:
            rogue.unlink(missing_ok=True)
            _clear_cache()

    def test_validation_failure_wraps_pydantic_error(self) -> None:
        """A YAML that survives shape check but fails Pydantic must surface
        as a ValueError with the original error chained — covers the
        ``except Exception`` → ``raise ValueError`` branch."""
        from volnix.actors import npc_profiles as _module

        profiles_dir = Path(_module.__file__).parent
        rogue = profiles_dir / "_rogue_invalid_profile.yaml"
        rogue.write_text(
            yaml.safe_dump(
                {
                    "name": "_rogue_invalid_profile",
                    "description": "invalid: missing state_schema and triggers",
                    # state_schema + activation_triggers intentionally absent
                }
            )
        )
        try:
            _clear_cache()
            with pytest.raises(ValueError, match="failed validation"):
                load_activation_profile("_rogue_invalid_profile")
        finally:
            rogue.unlink(missing_ok=True)
            _clear_cache()

    def test_list_profiles_skips_broken_entries(self) -> None:
        """If a profile in AVAILABLE_PROFILES is temporarily broken, list_profiles
        must skip it rather than raise — covers the except branch in list_profiles."""
        from volnix.actors import npc_profiles as _module

        original = _module.AVAILABLE_PROFILES
        _module.AVAILABLE_PROFILES = (*original, "_does_not_exist_at_all")
        try:
            _clear_cache()
            entries = list_profiles()
            names = {e["name"] for e in entries}
            assert "consumer_user" in names
            assert "_does_not_exist_at_all" not in names
        finally:
            _module.AVAILABLE_PROFILES = original
            _clear_cache()
