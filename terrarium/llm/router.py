"""LLM request router for the Terrarium framework.

Routes LLM requests to the appropriate provider and model based on the
engine name and use-case, using the routing table from configuration.
"""

from __future__ import annotations

import asyncio

from terrarium.llm.config import LLMConfig, LLMRoutingEntry
from terrarium.llm.provider import LLMProvider
from terrarium.llm.registry import ProviderRegistry
from terrarium.llm.tracker import UsageTracker
from terrarium.llm.types import LLMRequest, LLMResponse


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

        provider = self._registry.get(provider_name)

        if not request.model_override:
            request = LLMRequest(
                **{**request.model_dump(), "model_override": model}
            )

        async with self._semaphore:
            response = await provider.generate(request)

        if self._tracker:
            await self._tracker.record(request, response, engine_name)

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
