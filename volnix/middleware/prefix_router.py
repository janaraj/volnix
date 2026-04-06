"""Prefix router — mount service-prefixed URL aliases.

Duplicates existing pack routes under service prefixes so SDKs that
set ``base_url`` work. For example, Stripe's ``/v1/charges`` becomes
also available at ``/stripe/v1/charges``.

This runs once at startup, not per-request.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def mount_service_prefixes(
    app: Any,
    routes: list[dict[str, Any]],
    service_prefixes: dict[str, str],
    gateway: Any,
) -> int:
    """Duplicate routes under service prefixes.

    Args:
        app: FastAPI app instance.
        routes: HTTP route definitions from gateway.get_tool_manifest.
        service_prefixes: Map of service name → URL prefix.
        gateway: Gateway instance for handle_request calls.

    Returns:
        Number of prefixed routes mounted.
    """
    if not service_prefixes:
        return 0

    count = 0

    for route_def in routes:
        tool_name = route_def.get("tool_name", "")
        if not tool_name or "_" not in tool_name:
            continue

        service = tool_name.split("_")[0]
        prefix = service_prefixes.get(service)
        if not prefix:
            continue

        original_path = route_def.get("path", "")
        if not original_path:
            continue

        prefixed_path = f"{prefix}{original_path}"
        method = route_def.get("method", "POST").upper()

        # Skip if prefixed path is the same as original
        if prefixed_path == original_path:
            continue

        # Create handler closure (same pattern as _mount_pack_routes)
        def make_handler(tn: str, http_method: str):
            async def handler(request: Any):

                path_params = dict(request.path_params)
                if http_method == "GET":
                    arguments = dict(path_params)
                    arguments.update(dict(request.query_params))
                else:
                    try:
                        body = await request.json()
                        arguments = body.get("arguments", body)
                    except Exception:
                        arguments = {}
                    arguments.update(path_params)

                return await gateway.handle_request(
                    actor_id=arguments.pop("actor_id", "http-agent"),
                    tool_name=tn,
                    input_data=arguments,
                )

            return handler

        if method == "POST":
            app.post(prefixed_path)(make_handler(tool_name, "POST"))
            count += 1
        elif method == "GET":
            app.get(prefixed_path)(make_handler(tool_name, "GET"))
            count += 1

    logger.info(
        "Mounted %d service-prefixed routes from %d prefixes",
        count,
        len(service_prefixes),
    )
    return count
