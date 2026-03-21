"""LLM request router for the Terrarium framework.

Routes LLM requests to the appropriate provider and model based on the
engine name and use-case, using the routing table from configuration.
"""

from __future__ import annotations

from terrarium.llm.config import LLMConfig
from terrarium.llm.provider import LLMProvider
from terrarium.llm.registry import ProviderRegistry
from terrarium.llm.types import LLMRequest, LLMResponse


class LLMRouter:
    """Routes LLM requests to providers based on engine name and use-case."""

    def __init__(self, config: LLMConfig, registry: ProviderRegistry) -> None:
        ...

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
        ...

    def get_provider_for(self, engine_name: str, use_case: str = "default") -> LLMProvider:
        """Resolve the provider for a given engine and use-case.

        Args:
            engine_name: Name of the engine.
            use_case: The use-case category.

        Returns:
            The resolved :class:`LLMProvider` instance.
        """
        ...

    def get_model_for(self, engine_name: str, use_case: str = "default") -> str:
        """Resolve the model name for a given engine and use-case.

        Args:
            engine_name: Name of the engine.
            use_case: The use-case category.

        Returns:
            The model identifier string.
        """
        ...
