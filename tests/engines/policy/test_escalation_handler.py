"""Tests for EscalationHandler."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from volnix.core.events import PolicyEscalateEvent
from volnix.core.types import ActorId, PolicyId, Timestamp
from volnix.engines.policy.escalation_handler import EscalationHandler


def _make_escalate_event() -> PolicyEscalateEvent:
    return PolicyEscalateEvent(
        event_type="policy.escalate",
        timestamp=Timestamp(world_time=datetime.now(UTC), wall_time=datetime.now(UTC), tick=0),
        policy_id=PolicyId("large-refund"),
        actor_id=ActorId("triage-agent-abc"),
        action="create_refund",
        target_role="supervisor",
        original_actor=ActorId("triage-agent-abc"),
    )


class TestEscalationHandler:
    @pytest.fixture()
    def mock_app(self) -> AsyncMock:
        app = AsyncMock()
        app.handle_action = AsyncMock(return_value={})
        return app

    @pytest.fixture()
    def mock_bus(self) -> AsyncMock:
        bus = AsyncMock()
        bus.subscribe = AsyncMock()
        return bus

    @pytest.fixture()
    def handler(self, mock_app: AsyncMock, mock_bus: AsyncMock) -> EscalationHandler:
        return EscalationHandler(app=mock_app, bus=mock_bus)

    async def test_subscribes_to_policy_escalate(
        self, handler: EscalationHandler, mock_bus: AsyncMock
    ) -> None:
        await handler.start()
        mock_bus.subscribe.assert_called_once_with("policy.escalate", handler._handle_escalation)

    async def test_escalation_posts_to_channel(
        self, handler: EscalationHandler, mock_app: AsyncMock
    ) -> None:
        handler._find_team_channel = AsyncMock(
            return_value={
                "service_id": "slack",
                "post_action": "chat_postMessage",
                "channel_id": "C123",
            }
        )
        event = _make_escalate_event()
        await handler._handle_escalation(event)
        mock_app.handle_action.assert_called_once()
        call_kwargs = mock_app.handle_action.call_args.kwargs
        assert call_kwargs["actor_id"] == ActorId("system-escalation")
        assert call_kwargs["action"] == "chat_postMessage"
        assert "ESCALATION" in call_kwargs["input_data"]["text"]

    async def test_no_channel_logs_warning(
        self, handler: EscalationHandler, mock_app: AsyncMock
    ) -> None:
        handler._find_team_channel = AsyncMock(return_value=None)
        event = _make_escalate_event()
        await handler._handle_escalation(event)
        mock_app.handle_action.assert_not_called()

    async def test_system_actor_used(self, handler: EscalationHandler, mock_app: AsyncMock) -> None:
        handler._find_team_channel = AsyncMock(
            return_value={
                "service_id": "slack",
                "post_action": "chat_postMessage",
                "channel_id": "C1",
            }
        )
        event = _make_escalate_event()
        await handler._handle_escalation(event)
        assert mock_app.handle_action.call_args.kwargs["actor_id"] == ActorId("system-escalation")

    async def test_notification_failure_does_not_raise(
        self, handler: EscalationHandler, mock_app: AsyncMock
    ) -> None:
        handler._find_team_channel = AsyncMock(
            return_value={
                "service_id": "slack",
                "post_action": "chat_postMessage",
                "channel_id": "C1",
            }
        )
        mock_app.handle_action.side_effect = RuntimeError("connection lost")
        event = _make_escalate_event()
        # Should not raise -- failure is logged
        await handler._handle_escalation(event)

    async def test_find_team_channel_returns_none_without_state_engine(
        self,
    ) -> None:
        handler = EscalationHandler(app=AsyncMock(), bus=AsyncMock(), state_engine=None)
        result = await handler._find_team_channel()
        assert result is None

    async def test_find_team_channel_queries_state(self) -> None:
        state = AsyncMock()
        state.query_entities = AsyncMock(
            return_value=[{"id": "C42", "service_id": "slack", "name": "general"}]
        )
        handler = EscalationHandler(app=AsyncMock(), bus=AsyncMock(), state_engine=state)
        result = await handler._find_team_channel()
        assert result is not None
        assert result["channel_id"] == "C42"
        assert result["service_id"] == "slack"
        state.query_entities.assert_called_once_with(entity_type="channel")

    async def test_start_with_no_bus(self) -> None:
        handler = EscalationHandler(app=AsyncMock(), bus=None)
        # Should not raise
        await handler.start()

    async def test_system_actor_recursion_guard(
        self, handler: EscalationHandler, mock_app: AsyncMock
    ) -> None:
        """Escalation events from system actors are ignored to prevent recursion."""
        handler._find_team_channel = AsyncMock(
            return_value={
                "service_id": "slack",
                "post_action": "chat_postMessage",
                "channel_id": "C1",
            }
        )
        event = PolicyEscalateEvent(
            event_type="policy.escalate",
            timestamp=Timestamp(world_time=datetime.now(UTC), wall_time=datetime.now(UTC), tick=0),
            policy_id=PolicyId("any-policy"),
            actor_id=ActorId("system-escalation"),  # system actor
            action="chat_postMessage",
            target_role="supervisor",
            original_actor=ActorId("system-escalation"),
        )
        await handler._handle_escalation(event)
        mock_app.handle_action.assert_not_called()

    async def test_find_channel_missing_service_id_returns_none(self) -> None:
        """Channel entity without service_id is rejected."""
        state = AsyncMock()
        state.query_entities = AsyncMock(
            return_value=[{"id": "C42", "name": "general"}]  # no service_id
        )
        handler = EscalationHandler(app=AsyncMock(), bus=AsyncMock(), state_engine=state)
        result = await handler._find_team_channel()
        assert result is None

    async def test_message_contains_event_details(
        self, handler: EscalationHandler, mock_app: AsyncMock
    ) -> None:
        handler._find_team_channel = AsyncMock(
            return_value={
                "service_id": "slack",
                "post_action": "chat_postMessage",
                "channel_id": "C1",
            }
        )
        event = _make_escalate_event()
        await handler._handle_escalation(event)
        text = mock_app.handle_action.call_args.kwargs["input_data"]["text"]
        assert "create_refund" in text
        assert "triage-agent-abc" in text
        assert "supervisor" in text
        assert "large-refund" in text
