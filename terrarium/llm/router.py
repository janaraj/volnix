"""LLM request router for the Terrarium framework.

Routes LLM requests to the appropriate provider and model based on the
engine name and use-case, using the routing table from configuration.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from terrarium.llm.config import LLMConfig, LLMRoutingEntry
from terrarium.llm.provider import LLMProvider
from terrarium.llm.registry import ProviderRegistry
from terrarium.llm.tracker import UsageTracker
from terrarium.llm.types import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class LLMRouter:
    """Routes LLM requests to providers based on engine name and use-case."""

    def __init__(
        self,
        config: LLMConfig,
        registry: ProviderRegistry,
        tracker: UsageTracker | None = None,
    ) -> None:
        self._config = config
        self._registry = registry
        self._tracker = tracker
        self._semaphore = asyncio.Semaphore(
            config.max_concurrent if hasattr(config, "max_concurrent") else 10
        )

    def _resolve_routing(
        self, engine_name: str, use_case: str = "default"
    ) -> LLMRoutingEntry | None:
        """Look up the routing entry for the given engine and use-case.

        Tries ``{engine_name}_{use_case}`` first, then ``{engine_name}``.

        Args:
            engine_name: Name of the engine.
            use_case: The use-case category.

        Returns:
            The matched routing entry, or ``None`` for fallback to defaults.
        """
        routing_key = (
            f"{engine_name}_{use_case}" if use_case != "default" else engine_name
        )
        return self._config.routing.get(routing_key) or self._config.routing.get(
            engine_name
        )

    async def route(
        self,
        request: LLMRequest,
        engine_name: str,
        use_case: str = "default",
    ) -> LLMResponse:
        """Route an LLM request to the appropriate provider.

        Selects the provider and model based on the routing table, then
        delegates to the provider's ``generate`` method.

        Args:
            request: The LLM request payload.
            engine_name: Name of the engine making the request.
            use_case: The use-case category (e.g. ``"default"``, ``"structured"``).

        Returns:
            The LLM response from the selected provider.
        """
        routing = self._resolve_routing(engine_name, use_case)

        if routing:
            provider_name = routing.provider or self._config.defaults.type
            model = routing.model or self._config.defaults.default_model
            if routing.temperature is not None:
                request = LLMRequest(
                    **{**request.model_dump(), "temperature": routing.temperature}
                )
        else:
            provider_name = self._config.defaults.type
            model = self._config.defaults.default_model

        try:
            provider = self._registry.get(provider_name)
        except KeyError:
            routing_key = (
                f"{engine_name}_{use_case}" if use_case != "default" else engine_name
            )
            raise KeyError(
                f"No provider '{provider_name}' registered. "
                f"Routing: {routing_key} -> {'matched' if routing else 'fell through to defaults'}. "
                f"Check [llm.routing.{routing_key}] or [llm.defaults] in terrarium.toml."
            )

        if not request.model_override:
            request = LLMRequest(
                **{**request.model_dump(), "model_override": model}
            )

        # Use configured timeout from routing or defaults (not hardcoded)
        timeout = (
            getattr(routing, "timeout_seconds", None)
            or self._config.defaults.timeout_seconds
            or 120.0
        )

        async with self._semaphore:
            try:
                response = await asyncio.wait_for(
                    provider.generate(request),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("LLM call timed out after %ds: %s/%s", int(timeout), engine_name, use_case)
                response = LLMResponse(
                    content="",
                    provider=provider_name,
                    model=model,
                    error=f"LLM call timed out after {int(timeout)}s",
                )

        if self._tracker:
            await self._tracker.record(request, response, engine_name)

        # Debug-level: write LLM response content to file for traceability
        if logger.isEnabledFor(logging.DEBUG):
            self._write_debug_response(engine_name, use_case, request, response)

        return response

    def get_provider_for(
        self, engine_name: str, use_case: str = "default"
    ) -> LLMProvider:
        """Resolve the provider for a given engine and use-case.

        Args:
            engine_name: Name of the engine.
            use_case: The use-case category.

        Returns:
            The resolved :class:`LLMProvider` instance.
        """
        routing = self._resolve_routing(engine_name, use_case)
        provider_name = (
            routing.provider if routing and routing.provider else self._config.defaults.type
        )
        return self._registry.get(provider_name)

    def get_model_for(self, engine_name: str, use_case: str = "default") -> str:
        """Resolve the model name for a given engine and use-case.

        Args:
            engine_name: Name of the engine.
            use_case: The use-case category.

        Returns:
            The model identifier string.
        """
        routing = self._resolve_routing(engine_name, use_case)
        if routing and routing.model:
            return routing.model
        return self._config.defaults.default_model

    # ── Debug response logging ────────────────────────────────────

    _LLM_DEBUG_DIR = Path("data/llm_debug")

    def _write_debug_response(
        self,
        engine_name: str,
        use_case: str,
        request: LLMRequest,
        response: LLMResponse,
    ) -> None:
        """Write LLM response content to a debug file.

        Only called when log level is DEBUG. Files are written to
        ``data/llm_debug/`` with timestamps for easy correlation.
        """
        try:
            self._LLM_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
            filename = f"{ts}_{engine_name}_{use_case}.json"
            payload = {
                "timestamp": ts,
                "engine": engine_name,
                "use_case": use_case,
                "provider": response.provider,
                "model": response.model,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "latency_ms": response.latency_ms,
                "success": response.error is None,
                "error": response.error,
                "system_prompt": (
                    request.system_prompt[:2000] + "..."
                    if len(request.system_prompt) > 2000
                    else request.system_prompt
                ),
                "user_content": request.user_content,
                "response_content": response.content,
            }
            (self._LLM_DEBUG_DIR / filename).write_text(
                json.dumps(payload, indent=2, default=str)
            )
        except Exception:
            logger.debug("Failed to write LLM debug file", exc_info=True)
