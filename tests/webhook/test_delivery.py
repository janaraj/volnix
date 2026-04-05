"""Tests for WebhookDelivery — HTTP POST with retry."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from volnix.webhook.delivery import WebhookDelivery


async def test_successful_delivery():
    """Successful POST returns success result."""
    delivery = WebhookDelivery(
        max_retries=0, backoff_base=0.01, timeout=2.0
    )
    # Mock httpx to return 200
    mock_response = AsyncMock()
    mock_response.status_code = 200

    with patch("volnix.webhook.delivery.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        result = await delivery.send(
            "http://agent:3000/hook",
            {"event": "test"},
        )

    assert result.success is True
    assert result.attempts == 1
    assert result.status_code == 200


async def test_4xx_no_retry():
    """4xx responses don't retry."""
    delivery = WebhookDelivery(
        max_retries=3, backoff_base=0.01, timeout=2.0
    )
    mock_response = AsyncMock()
    mock_response.status_code = 404

    with patch("volnix.webhook.delivery.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        result = await delivery.send(
            "http://agent:3000/hook", {"event": "test"}
        )

    assert result.success is False
    assert result.attempts == 1  # No retry on 4xx
    assert result.status_code == 404


async def test_connection_error_retries():
    """Connection errors retry up to max_retries."""
    import httpx

    delivery = WebhookDelivery(
        max_retries=2, backoff_base=0.01, timeout=1.0
    )

    with patch("volnix.webhook.delivery.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        result = await delivery.send(
            "http://agent:3000/hook", {"event": "test"}
        )

    assert result.success is False
    assert result.attempts == 3  # 1 initial + 2 retries
    assert "Connection error" in result.error


async def test_hmac_signature():
    """Secret adds X-Volnix-Signature header."""
    delivery = WebhookDelivery(
        max_retries=0, backoff_base=0.01, timeout=2.0
    )
    mock_response = AsyncMock()
    mock_response.status_code = 200

    captured_headers = {}

    async def capture_post(url, json, headers):
        captured_headers.update(headers)
        return mock_response

    with patch("volnix.webhook.delivery.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = capture_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        await delivery.send(
            "http://agent:3000/hook",
            {"event": "test"},
            secret="my_secret_key",
        )

    assert "X-Volnix-Signature" in captured_headers
    assert len(captured_headers["X-Volnix-Signature"]) == 64  # SHA256 hex


async def test_max_retries_exhausted():
    """After max retries, returns failure."""
    import httpx

    delivery = WebhookDelivery(
        max_retries=1, backoff_base=0.01, timeout=1.0
    )

    with patch("volnix.webhook.delivery.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.TimeoutException("timeout")
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        result = await delivery.send(
            "http://agent:3000/hook", {"event": "test"}
        )

    assert result.success is False
    assert result.attempts == 2
    assert "Timeout" in result.error
