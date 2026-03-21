"""Google native LLM provider for the Terrarium framework.

Implements the :class:`~terrarium.llm.provider.LLMProvider` interface
using the Google Generative AI (Gemini) native SDK.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.llm.provider import LLMProvider
from terrarium.llm.types import LLMRequest, LLMResponse, ProviderInfo


class GoogleNativeProvider(LLMProvider):
    """LLM provider backed by the Google Generative AI (Gemini) native API."""

    provider_name: ClassVar[str] = "google"

    def __init__(self, api_key: str, default_model: str = "gemini-pro") -> None:
        ...

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Send a request to the Google Generative AI API.

        Args:
            request: The LLM request payload.

        Returns:
            The LLM response.
        """
        ...

    async def validate_connection(self) -> bool:
        """Validate connectivity to the Google API.

        Returns:
            ``True`` if reachable with valid credentials.
        """
        ...

    async def list_models(self) -> list[str]:
        """List available Google Gemini models.

        Returns:
            A list of model identifier strings.
        """
        ...

    def get_info(self) -> ProviderInfo:
        """Return provider metadata.

        Returns:
            A :class:`ProviderInfo` describing this Google provider.
        """
        ...
