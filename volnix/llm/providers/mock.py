"""Mock LLM provider for testing and development.

Produces deterministic responses based on a seed value, enabling
reproducible test runs without requiring any external API access.
"""

from __future__ import annotations

import hashlib
import time
from typing import ClassVar

from volnix.llm.provider import LLMProvider
from volnix.llm.types import (
    EmbeddingRequest,
    EmbeddingResponse,
    LLMRequest,
    LLMResponse,
    LLMUsage,
    ProviderInfo,
)


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

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Deterministic mock embeddings for tests.

        Each vector is derived from a SHA-256 hash of the input text,
        treating each byte as an integer in [0, 255] then mapped to
        a float in [-1, 1]. Same text → same vector, always — the
        contract the content-hash cache depends on (G14 determinism).

        Bytewise (not float-unpack) to avoid bit patterns that
        materialise as NaN/Inf — those break equality comparisons
        (NaN != NaN) and poison downstream cosine math.
        """
        start = time.monotonic()
        vectors: list[list[float]] = []
        for t in request.texts:
            digest = hashlib.sha256(t.encode("utf-8")).digest()
            # Take 8 bytes, map each to a float in [-1, 1].
            # Arbitrary width — keeps tests small while exercising
            # the vector machinery. Normalise to unit length so
            # cosine similarity has well-defined semantics.
            raw = [(b / 127.5) - 1.0 for b in digest[:8]]
            norm = sum(x * x for x in raw) ** 0.5
            if norm > 0:
                raw = [x / norm for x in raw]
            vectors.append(raw)
        latency = (time.monotonic() - start) * 1000
        # Mock usage — rough token-count estimate at 4 chars/token.
        prompt_tokens = sum(max(1, len(t) // 4) for t in request.texts)
        return EmbeddingResponse(
            vectors=vectors,
            model=request.model_override or "mock-embed-1",
            provider="mock",
            usage=LLMUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=0,
                total_tokens=prompt_tokens,
                cost_usd=0.0,
            ),
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
