"""Runtime helpers for real-path adapter tests."""

from __future__ import annotations

import threading
from typing import Any


async def start_http_adapter(app: Any) -> Any:
    """Start adapters on a real app and return the HTTP adapter."""
    from volnix.kernel.surface import ServiceSurface

    adapter = app.gateway._adapters["http"]
    original_get_tool_manifest = app.gateway.get_tool_manifest
    responder = app.registry.get("responder")
    email_pack = responder._pack_registry.get_pack("gmail")

    async def _stable_manifest(actor_id: str | None = None, protocol: str = "http"):
        if protocol == "http":
            return ServiceSurface.from_pack(email_pack).get_http_routes()
        return await original_get_tool_manifest(actor_id=actor_id, protocol=protocol)

    app.gateway.get_tool_manifest = _stable_manifest
    await adapter.start_server()
    return adapter


def spawn_websocket_receiver(
    websocket: Any,
) -> tuple[threading.Thread, dict[str, Any], dict[str, BaseException]]:
    """Receive a single websocket message on a background thread."""
    payload: dict[str, Any] = {}
    errors: dict[str, BaseException] = {}

    def _receive() -> None:
        try:
            payload["message"] = websocket.receive_json()
        except BaseException as exc:  # pragma: no cover - surfaced by caller
            errors["exception"] = exc

    thread = threading.Thread(target=_receive, daemon=True)
    thread.start()
    return thread, payload, errors
