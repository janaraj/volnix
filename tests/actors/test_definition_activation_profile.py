"""Tests for the Layer-1 ``activation_profile`` field on ``ActorDefinition``
and ``ActorState``, plus the loader validation in ``internal_profile.py``.

Scope: compile-time contract only. Runtime dispatch (Active vs. Passive
activation) is wired in Phase 2 and tested there.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from volnix.actors.definition import ActorDefinition
from volnix.actors.internal_profile import load_internal_profile
from volnix.actors.state import ActorState
from volnix.core.types import ActorId, ActorType

# -- ActorDefinition.activation_profile ---------------------------------------


class TestActorDefinitionActivationProfile:
    def test_default_is_none(self) -> None:
        """Passive path: field defaults to None. Existing blueprints match this."""
        actor = ActorDefinition(id=ActorId("a1"), type=ActorType.HUMAN, role="customer")
        assert actor.activation_profile is None

    def test_explicit_profile_name(self) -> None:
        actor = ActorDefinition(
            id=ActorId("a2"),
            type=ActorType.HUMAN,
            role="consumer",
            activation_profile="consumer_user",
        )
        assert actor.activation_profile == "consumer_user"


# -- ActorState.activation_profile_name / npc_state ---------------------------


class TestActorStateNPCFields:
    def test_defaults(self) -> None:
        """For every existing AGENT path, the new NPC fields stay at their
        defaults so no downstream consumer of ``ActorState`` sees drift."""
        state = ActorState(actor_id=ActorId("a1"), role="analyst")
        assert state.activation_profile_name is None
        assert state.npc_state is None

    def test_set_both(self) -> None:
        state = ActorState(
            actor_id=ActorId("npc-1"),
            role="consumer",
            activation_profile_name="consumer_user",
            npc_state={"awareness": 0.2, "usage_count": 0},
        )
        assert state.activation_profile_name == "consumer_user"
        assert state.npc_state is not None
        assert state.npc_state["awareness"] == 0.2


# -- internal_profile.py eager validation -------------------------------------


class TestInternalProfileActivationProfile:
    def _write(self, path: Path, payload: dict) -> Path:
        path.write_text(yaml.safe_dump(payload))
        return path

    def test_agent_with_activation_profile_is_rejected(self, tmp_path: Path) -> None:
        """Agents in internal_profile YAML must not declare activation_profile.

        Mixing agent lifecycle (delegation/synthesis/team-channel) with
        the NPC tool loop creates a silent behavior swap — the footgun
        flagged as review M6. Reject with a clear message directing the
        author to world.yaml instead.
        """
        yaml_path = self._write(
            tmp_path / "team.yaml",
            {
                "mission": "test",
                "deliverable": "synthesis",
                "agents": [
                    {
                        "role": "observer",
                        "activation_profile": "consumer_user",
                    }
                ],
            },
        )
        with pytest.raises(ValueError, match="activation_profile is"):
            load_internal_profile(yaml_path)

    def test_absent_profile_defaults_to_none(self, tmp_path: Path) -> None:
        """Backward-compat: agent YAMLs without activation_profile still load."""
        yaml_path = self._write(
            tmp_path / "team.yaml",
            {
                "mission": "test",
                "deliverable": "synthesis",
                "agents": [
                    {"role": "analyst"},
                ],
            },
        )
        profile = load_internal_profile(yaml_path)
        assert profile.agents[0].activation_profile is None
