"""Mock LLM provider for testing and development.

Produces deterministic responses based on a seed value, enabling
reproducible test runs without requiring any external API access.
"""

from __future__ import annotations

import hashlib
import time
from typing import ClassVar

from volnix.llm.provider import LLMProvider
from volnix.llm.types import LLMRequest, LLMResponse, LLMUsage, ProviderInfo


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
        self._seed = seed
        self._responses = responses or {}

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Return a deterministic mock response.

        If *responses* contains a key matching the user content, that value
        is returned.  Otherwise a seeded deterministic response is generated.

        Args:
            request: The LLM request payload.

        Returns:
            A deterministic :class:`LLMResponse`.
        """
        start = time.monotonic()

        # Check for custom response mapping
        if request.user_content in self._responses:
            content = self._responses[request.user_content]
        else:
            # Deterministic hash-based response
            seed_val = request.seed if request.seed is not None else self._seed
            hash_input = f"{seed_val}:{request.system_prompt}:{request.user_content}"
            digest = hashlib.sha256(hash_input.encode()).hexdigest()
            content = f"Mock response [{digest[:12]}]: Processed '{request.user_content[:50]}'"

        latency = (time.monotonic() - start) * 1000

        # Estimate tokens from content length (rough: ~4 chars per token)
        prompt_tokens = max(1, (len(request.system_prompt) + len(request.user_content)) // 4)
        completion_tokens = max(1, len(content) // 4)

        usage = LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=0.0,
        )

        return LLMResponse(
            content=content,
            usage=usage,
            model=request.model_override or "mock-model-1",
            provider="mock",
            latency_ms=latency,
        )

    async def validate_connection(self) -> bool:
        """Always returns ``True`` for the mock provider.

        Returns:
            ``True``.
        """
        return True

    async def list_models(self) -> list[str]:
        """Return the list of mock model names.

        Returns:
            A list containing two mock model identifiers.
        """
        return ["mock-model-1", "mock-model-2"]

    def get_info(self) -> ProviderInfo:
        """Return mock provider metadata.

        Returns:
            A :class:`ProviderInfo` for the mock provider.
        """
        return ProviderInfo(
            name="mock",
            type="mock",
            available_models=["mock-model-1", "mock-model-2"],
        )
