"""Abstract base class for LLM providers.

All concrete providers (Anthropic, OpenAI-compatible, Google, ACP, CLI, mock)
implement this interface so that the router and registry can treat them
uniformly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import ClassVar

from volnix.llm.types import (
    EmbeddingRequest,
    EmbeddingResponse,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
    ProviderInfo,
)


class LLMProvider(ABC):
    """Abstract base class that all LLM providers must implement."""

    provider_name: ClassVar[str] = ""

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Send a request to the LLM and return the response.

        Args:
            request: The LLM request payload.

        Returns:
            The LLM response including content, usage, and latency.
        """
        ...

    async def stream_generate(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
        """Stream the LLM response chunk-by-chunk
        (``tnl/llm-router-streaming-surface.tnl``).

        Default implementation: delegates to :meth:`generate`,
        wraps the resulting ``LLMResponse`` into a single
        ``LLMStreamChunk`` with ``is_final=True``, and yields
        exactly that one chunk. Providers that support native
        SDK streaming override this method to yield true
        per-token chunks.

        On exception during the underlying ``generate(...)`` call,
        yields ONE ``LLMStreamChunk`` with ``error`` populated,
        ``is_final=True``, ``content_delta=""``, then stops.
        Callers MUST inspect the last chunk's ``error`` field
        rather than relying on exception propagation.
        """
        try:
            response = await self.generate(request)
        except Exception as exc:  # noqa: BLE001 — caller contract: error in chunk
            yield LLMStreamChunk(
                content_delta="",
                usage_delta=None,
                is_final=True,
                provider=self.provider_name,
                model=request.model_override or "",
                error=f"{type(exc).__name__}: {exc}",
            )
            return
        yield LLMStreamChunk(
            content_delta=response.content,
            usage_delta=response.usage,
            is_final=True,
            provider=response.provider,
            model=response.model,
            error=response.error,
        )

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Produce embeddings for the input texts.

        Default raises ``NotImplementedError``. Providers that support
        embeddings (OpenAI-compatible, mock, and any future ones)
        override this method. Providers without an embeddings API
        (e.g., some CLI subprocess wrappers, ACP providers) leave the
        default in place — the router surfaces the
        ``NotImplementedError`` as a clean config error.

        Added for PMF Plan Phase 4B Step 3.5 (G3 of the gap analysis).
        """
        raise NotImplementedError(
            f"Provider {self.provider_name!r} does not support embeddings. "
            f"Configure ``[llm.routing.<engine>_<embed_use_case>]`` to "
            f"route to a provider that does (e.g. openai, mock)."
        )

    async def validate_connection(self) -> bool:
        """Check that the provider is reachable and credentials are valid.

        Returns:
            ``True`` if the connection is healthy, ``False`` otherwise.
        """
        return True

    async def list_models(self) -> list[str]:
        """List the models available from this provider.

        Returns:
            A list of model identifier strings.
        """
        return []

    def get_info(self) -> ProviderInfo:
        """Return metadata about this provider instance.

        Returns:
            A :class:`ProviderInfo` with provider details.
        """
        return ProviderInfo(name=self.provider_name, type=self.provider_name)
