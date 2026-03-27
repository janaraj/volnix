"""Regression prevention tests for the Collaborative Communication Extension.

These tests verify STRUCTURAL CONTRACTS. If someone adds a new communication
pack, changes InteractionRecord fields, or modifies the config schema, these
tests catch the breakage early.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import get_type_hints

import pytest
import yaml

from terrarium.actors.state import ActorState, InteractionRecord, Subscription
from terrarium.engines.adapter.protocols.http_rest import COMMUNICATION_ACTIONS
from terrarium.engines.agency.config import AgencyConfig
from terrarium.engines.agency.prompt_builder import ActorPromptBuilder
from terrarium.ledger.entries import (
    ENTRY_REGISTRY,
    CollaborationNotificationEntry,
    SubscriptionMatchEntry,
)
from terrarium.simulation.world_context import WorldContextBundle


# ---------------------------------------------------------------------------
# 1. All communication packs represented in COMMUNICATION_ACTIONS
# ---------------------------------------------------------------------------


class TestAllCommunicationPacksInActionsSet:
    """COMMUNICATION_ACTIONS in http_rest.py must include tools from ALL
    communication/social packs that produce user-visible messages."""

    def test_chat_pack_actions_included(self):
        """Slack chat pack posting actions must be in COMMUNICATION_ACTIONS."""
        # These are the communication-producing actions from the Slack pack
        chat_communication_actions = {"chat.postMessage", "chat.replyToThread"}
        missing = chat_communication_actions - COMMUNICATION_ACTIONS
        assert not missing, (
            f"Chat pack communication actions missing from COMMUNICATION_ACTIONS: {missing}"
        )

    def test_email_pack_actions_included(self):
        """Gmail email_send must be in COMMUNICATION_ACTIONS."""
        email_actions = {"email_send"}
        missing = email_actions - COMMUNICATION_ACTIONS
        assert not missing, (
            f"Email pack communication actions missing from COMMUNICATION_ACTIONS: {missing}"
        )

    def test_reddit_pack_actions_included(self):
        """Reddit posting actions must be in COMMUNICATION_ACTIONS."""
        reddit_actions = {"reddit_submit", "reddit_comment"}
        missing = reddit_actions - COMMUNICATION_ACTIONS
        assert not missing, (
            f"Reddit pack communication actions missing from COMMUNICATION_ACTIONS: {missing}"
        )

    def test_twitter_pack_actions_included(self):
        """Twitter tweet/reply actions must be in COMMUNICATION_ACTIONS."""
        twitter_actions = {"twitter_create_tweet", "twitter_reply"}
        missing = twitter_actions - COMMUNICATION_ACTIONS
        assert not missing, (
            f"Twitter pack communication actions missing from COMMUNICATION_ACTIONS: {missing}"
        )


# ---------------------------------------------------------------------------
# 2. InteractionRecord fields rendered in prompt
# ---------------------------------------------------------------------------


class TestInteractionRecordFieldsRenderedInPrompt:
    """Every field on InteractionRecord that carries user-visible data must be
    consumed by the prompt builder's rendering logic."""

    def test_interaction_record_fields_rendered_in_prompt(self):
        """Check that the prompt builder references key InteractionRecord fields."""
        ctx = WorldContextBundle(
            world_description="Test",
            reality_summary="Ideal",
            behavior_mode="static",
        )
        builder = ActorPromptBuilder(ctx)

        # Build a prompt with a record that has all fields populated
        record = InteractionRecord(
            tick=5.0,
            actor_id="actor-test",
            actor_role="tester",
            action="chat.postMessage",
            summary="This is a test message",
            source="notified",
            event_id="evt-test-001",
            reply_to="evt-parent-000",
            channel="#testing",
            intended_for=["tester"],
        )

        actor = ActorState(
            actor_id="actor-viewer",
            role="viewer",
            recent_interactions=[record],
        )

        from terrarium.core.events import WorldEvent
        from terrarium.core.types import ActorId, ServiceId, Timestamp
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        event = WorldEvent(
            event_type="world.action",
            timestamp=Timestamp(world_time=now, wall_time=now, tick=1),
            actor_id=ActorId("agent-ext"),
            service_id=ServiceId("chat"),
            action="chat.postMessage",
            input_data={},
        )

        prompt = builder.build_individual_prompt(
            actor=actor,
            trigger_event=event,
            activation_reason="test",
            available_actions=[],
        )

        # Verify that the user-visible fields appear in the rendered prompt
        assert "tester" in prompt, "actor_role not rendered"
        assert "This is a test message" in prompt, "summary not rendered"
        assert "#testing" in prompt, "channel not rendered"
        assert "evt-parent-000" in prompt, "reply_to not rendered"
        assert "[notified via subscription]" in prompt, "source=notified not rendered"
        assert "tick" in prompt.lower(), "tick not rendered"


# ---------------------------------------------------------------------------
# 3. Deliverable presets all valid
# ---------------------------------------------------------------------------


class TestDeliverablePresetsAllValid:
    """Every YAML in deliverable_presets/ must parse correctly."""

    def test_deliverable_presets_all_valid(self):
        """All YAML files in deliverable_presets/ parse as valid presets."""
        presets_dir = Path(__file__).parent.parent / "terrarium" / "deliverable_presets"
        yaml_files = list(presets_dir.glob("*.yaml"))

        assert len(yaml_files) > 0, "No YAML files found in deliverable_presets/"

        required_keys = {"name", "description", "schema", "prompt_instructions"}

        for yaml_file in yaml_files:
            with open(yaml_file) as f:
                data = yaml.safe_load(f)

            assert isinstance(data, dict), (
                f"{yaml_file.name}: YAML root is not a dict"
            )

            missing = required_keys - set(data.keys())
            assert not missing, (
                f"{yaml_file.name}: Missing required keys: {missing}"
            )

            # Schema must be a dict with 'type'
            assert isinstance(data["schema"], dict), (
                f"{yaml_file.name}: 'schema' is not a dict"
            )


# ---------------------------------------------------------------------------
# 4. Subscription sensitivity levels all handled
# ---------------------------------------------------------------------------


class TestSubscriptionSensitivityLevelsAllHandled:
    """Every Literal value in Subscription.sensitivity must have handler code in notify()."""

    def test_subscription_sensitivity_levels_all_handled(self):
        """Check that the engine notify() handles every sensitivity level."""
        # Get the Literal values from the Subscription model
        hints = get_type_hints(Subscription, include_extras=True)
        # Pydantic fields with Literal -- the allowed values are "immediate", "batch", "passive"
        expected_levels = {"immediate", "batch", "passive"}

        # Read the source of notify() and check that each level is referenced
        from terrarium.engines.agency.engine import AgencyEngine
        source = inspect.getsource(AgencyEngine.notify)

        for level in expected_levels:
            assert f'"{level}"' in source or f"'{level}'" in source, (
                f"Sensitivity level '{level}' not handled in AgencyEngine.notify()"
            )


# ---------------------------------------------------------------------------
# 5. Collaboration config matches TOML
# ---------------------------------------------------------------------------


class TestCollaborationConfigMatchesToml:
    """All AgencyConfig collaboration fields must exist in terrarium.toml."""

    def test_collaboration_config_matches_toml(self):
        """Verify TOML [agency] section contains all collaboration config fields."""
        toml_path = Path(__file__).parent.parent / "terrarium.toml"
        if not toml_path.exists():
            pytest.skip("terrarium.toml not found")

        # Read the TOML file
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]

        with open(toml_path, "rb") as f:
            config = tomllib.load(f)

        agency_section = config.get("agency", {})

        # These are the collaboration-specific fields from AgencyConfig
        collaboration_fields = [
            "collaboration_mode",
            "collaboration_enabled",
            "batch_threshold_default",
            "synthesis_buffer_pct",
            "idle_stop_ticks",
            "auto_include_chat",
        ]

        missing = [f for f in collaboration_fields if f not in agency_section]
        assert not missing, (
            f"AgencyConfig collaboration fields missing from terrarium.toml [agency]: {missing}"
        )


# ---------------------------------------------------------------------------
# 6. Ledger entries registered
# ---------------------------------------------------------------------------


class TestLedgerEntriesRegistered:
    """SubscriptionMatchEntry and CollaborationNotificationEntry must be in ENTRY_REGISTRY."""

    def test_subscription_match_entry_registered(self):
        """SubscriptionMatchEntry must be in ENTRY_REGISTRY."""
        assert "subscription_match" in ENTRY_REGISTRY
        assert ENTRY_REGISTRY["subscription_match"] is SubscriptionMatchEntry

    def test_collaboration_notification_entry_registered(self):
        """CollaborationNotificationEntry must be in ENTRY_REGISTRY."""
        assert "collaboration_notification" in ENTRY_REGISTRY
        assert ENTRY_REGISTRY["collaboration_notification"] is CollaborationNotificationEntry


# ---------------------------------------------------------------------------
# 7. ActorState has collaboration fields
# ---------------------------------------------------------------------------


class TestActorStateHasCollaborationFields:
    """ActorState must have subscriptions, pending_tasks, goal_context fields."""

    def test_actor_state_has_subscriptions(self):
        """ActorState must have a 'subscriptions' field."""
        state = ActorState(actor_id="test", role="test")
        assert hasattr(state, "subscriptions")
        assert isinstance(state.subscriptions, list)

    def test_actor_state_has_pending_tasks(self):
        """ActorState must have a 'pending_tasks' field."""
        state = ActorState(actor_id="test", role="test")
        assert hasattr(state, "pending_tasks")
        assert isinstance(state.pending_tasks, list)

    def test_actor_state_has_goal_context(self):
        """ActorState must have a 'goal_context' field."""
        state = ActorState(actor_id="test", role="test")
        assert hasattr(state, "goal_context")

    def test_actor_state_has_batch_notification_count(self):
        """ActorState must have a 'batch_notification_count' field."""
        state = ActorState(actor_id="test", role="test")
        assert hasattr(state, "batch_notification_count")
        assert state.batch_notification_count == 0

    def test_actor_state_has_batch_threshold(self):
        """ActorState must have a 'batch_threshold' field."""
        state = ActorState(actor_id="test", role="test")
        assert hasattr(state, "batch_threshold")
        assert state.batch_threshold == 3
