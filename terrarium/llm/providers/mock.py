"""Mock LLM provider for testing and development.

Produces deterministic responses based on a seed value, enabling
reproducible test runs without requiring any external API access.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.llm.provider import LLMProvider
from terrarium.llm.types import LLMRequest, LLMResponse, ProviderInfo


class MockLLMProvider(LLMProvider):
    """Deterministic mock LLM provider for testing.

    Generates reproducible responses based on a seed value.  Pre-configured
    response mappings can be supplied for specific prompts.
    """

    provider_name: ClassVar[str] = "mock"

    def __init__(
        self,
        seed: int = 42,
        responses: dict[str, str] | None = None,
    ) -> None:
        ...

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Return a deterministic mock response.

        If *responses* contains a key matching the user content, that value
        is returned.  Otherwise a seeded deterministic response is generated.

        Args:
            request: The LLM request payload.

        Returns:
            A deterministic :class:`LLMResponse`.
        """
        ...

    async def validate_connection(self) -> bool:
        """Always returns ``True`` for the mock provider.

        Returns:
            ``True``.
        """
        ...

    async def list_models(self) -> list[str]:
        """Return the list of mock model names.

        Returns:
            A single-element list containing ``"mock"``.
        """
        ...

    def get_info(self) -> ProviderInfo:
        """Return mock provider metadata.

        Returns:
            A :class:`ProviderInfo` for the mock provider.
        """
        ...
