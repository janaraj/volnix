"""Tests for WebhookManager — bus subscriber orchestrator."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch


async def test_start_subscribes_to_bus(webhook_manager, mock_bus):
    """start() subscribes to wildcard on the bus."""
    await webhook_manager.start(mock_bus)
    mock_bus.subscribe.assert_awaited_once_with(
        "*", webhook_manager._on_event
    )


async def test_start_disabled_does_nothing(mock_bus):
    """When disabled, start() doesn't subscribe."""
    from terrarium.webhook.config import WebhookConfig
    from terrarium.webhook.manager import WebhookManager

    config = WebhookConfig(enabled=False)
    manager = WebhookManager(config)
    await manager.start(mock_bus)
    mock_bus.subscribe.assert_not_awaited()


async def test_event_delivered_to_matching_webhook(
    webhook_manager, mock_bus, sample_event
):
    """Matching world event is delivered to registered webhook."""
    await webhook_manager.start(mock_bus)
    webhook_manager.register(
        url="http://agent.example.com:3000/hook",
        events=["world.email_*"],
        service="email",
    )

    with patch.object(
        webhook_manager._delivery,
        "send",
        new_callable=AsyncMock,
    ) as mock_send:
        from terrarium.webhook.delivery import DeliveryResult

        mock_send.return_value = DeliveryResult(
            success=True, attempts=1, status_code=200
        )
        await webhook_manager._on_event(sample_event)
        # C2: delivery is async task — give it time to complete
        await asyncio.sleep(0.05)

    mock_send.assert_awaited_once()
    assert webhook_manager.get_stats()["delivered"] == 1


async def test_no_match_skips(webhook_manager, mock_bus, sample_event):
    """Non-matching event is skipped."""
    await webhook_manager.start(mock_bus)
    webhook_manager.register(
        url="http://agent.example.com:3000/hook",
        events=["world.chat_*"],
    )

    with patch.object(
        webhook_manager._delivery, "send", new_callable=AsyncMock
    ) as mock_send:
        await webhook_manager._on_event(sample_event)
        await asyncio.sleep(0.05)

    mock_send.assert_not_awaited()
    assert webhook_manager.get_stats()["skipped"] == 1


async def test_stop_unsubscribes(webhook_manager, mock_bus):
    """stop() unsubscribes from bus."""
    await webhook_manager.start(mock_bus)
    await webhook_manager.stop()
    mock_bus.unsubscribe.assert_awaited_once()


async def test_stats_tracking(webhook_manager, mock_bus):
    """Stats include errors counter."""
    await webhook_manager.start(mock_bus)
    stats = webhook_manager.get_stats()
    assert stats["delivered"] == 0
    assert stats["failed"] == 0
    assert stats["skipped"] == 0
    assert stats["errors"] == 0
    assert stats["registered"] == 0


async def test_list_webhooks_excludes_secrets(webhook_manager, mock_bus):
    """list_webhooks() doesn't expose secrets."""
    await webhook_manager.start(mock_bus)
    webhook_manager.register(
        url="http://agent.example.com:3000/hook",
        events=["world.*"],
        secret="my_secret",
    )
    hooks = webhook_manager.list_webhooks()
    assert len(hooks) == 1
    assert "secret" not in hooks[0]


# -- H4: Internal event filtering ---


async def test_internal_event_filtered(webhook_manager, mock_bus):
    """H4: Non-world events are filtered out."""
    await webhook_manager.start(mock_bus)
    webhook_manager.register(
        url="http://agent.example.com:3000/hook",
        events=["*"],
    )

    # Create an internal event (not world.*)
    class InternalEvent:
        event_type = "engine_lifecycle.init"
        service_id = ""

    with patch.object(
        webhook_manager._delivery, "send", new_callable=AsyncMock
    ) as mock_send:
        await webhook_manager._on_event(InternalEvent())
        await asyncio.sleep(0.05)

    # Internal event should not be delivered
    mock_send.assert_not_awaited()


# -- H3: Exception handling ---


async def test_delivery_exception_tracked(
    webhook_manager, mock_bus, sample_event
):
    """H3: Exception in delivery increments errors stat."""
    await webhook_manager.start(mock_bus)
    webhook_manager.register(
        url="http://agent.example.com:3000/hook",
        events=["world.*"],
    )

    with patch.object(
        webhook_manager._delivery,
        "send",
        new_callable=AsyncMock,
        side_effect=RuntimeError("unexpected"),
    ):
        await webhook_manager._on_event(sample_event)
        await asyncio.sleep(0.1)

    assert webhook_manager.get_stats()["errors"] == 1


# -- Failure stats ---


async def test_failed_delivery_tracked(
    webhook_manager, mock_bus, sample_event
):
    """Failed delivery increments failed stat."""
    await webhook_manager.start(mock_bus)
    webhook_manager.register(
        url="http://agent.example.com:3000/hook",
        events=["world.*"],
    )

    with patch.object(
        webhook_manager._delivery,
        "send",
        new_callable=AsyncMock,
    ) as mock_send:
        from terrarium.webhook.delivery import DeliveryResult

        mock_send.return_value = DeliveryResult(
            success=False, attempts=2, error="HTTP 500"
        )
        await webhook_manager._on_event(sample_event)
        await asyncio.sleep(0.05)

    assert webhook_manager.get_stats()["failed"] == 1
