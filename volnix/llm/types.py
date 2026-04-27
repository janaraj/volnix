"""Data types for the LLM provider module.

Defines request, response, usage, and provider-info models used across
all LLM providers and the routing layer.
"""

from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ProviderType(enum.StrEnum):
    """Discriminator for the kind of LLM provider."""

    API = "api"
    ACP = "acp"
    CLI = "cli"
    MOCK = "mock"


class ToolDefinition(BaseModel, frozen=True):
    """Provider-agnostic tool definition.

    Each LLM provider converts to its native format:
    - OpenAI: ``{"type": "function", "function": {...}}``
    - Anthropic: ``{"name": ..., "input_schema": {...}}``
    - Google: ``types.FunctionDeclaration(...)``

    Tool names use the simple sanitized action name (e.g. ``search_recent``).
    A ``{service}__`` prefix is only added when two services share the same
    action name (collision avoidance).
    """

    name: str  # "search_recent"
    service: str = ""  # "twitter"
    description: str = ""  # "Search recent tweets"
    parameters: dict[str, Any] = Field(default_factory=dict)  # JSON Schema


class ToolCall(BaseModel, frozen=True):
    """Parsed tool call from an LLM response.

    Provider implementations convert their native format to this model
    so callers don't need to know which provider was used.
    """

    name: str  # "search_recent"
    arguments: dict[str, Any] = Field(default_factory=dict)  # {"query": "..."}
    id: str = ""  # Provider-assigned ID for multi-turn mapping
    provider_metadata: dict[str, Any] | None = None
    # Opaque provider-specific passthrough data (e.g., Gemini thought_signature
    # base64-encoded). Providers own their own keys — DO NOT depend on structure.


class LLMUsage(BaseModel, frozen=True):
    """Token usage and cost for a single LLM call.

    Attributes:
        prompt_tokens: Number of tokens in the prompt. None from the
            provider is coerced to 0.
        completion_tokens: Number of tokens in the completion. None from
            the provider is coerced to 0.
        total_tokens: Total tokens consumed. None from the provider is
            coerced to 0.
        cost_usd: Estimated cost in US dollars. None from the provider
            is coerced to 0.0.

    None-tolerance rationale: some providers (notably
    ``gemini-3-flash-preview``) intermittently return the token-count
    attribute set-but-null on ``usage_metadata`` rather than omitting
    it. The Google provider's ``getattr(usage_meta, "x", 0)`` default
    only fires when the attribute is *missing*, not when it's *None*,
    so the ``None`` would flow into ``LLMUsage(...)`` and pydantic v2
    would raise ValidationError on the ``int`` field. The router then
    flagged the error non-retryable and the agency loop silently lost
    the agent's turn. Observed during the P6.3 supply-chain live run.

    These validators coerce None to the zero default at the model
    boundary so no provider needs a defensive ``or 0`` patch and
    future providers inherit the behavior for free. Downstream
    consumers (budget tracker, ledger, dashboard) continue to see
    plain ``int`` — no ``int | None`` ripple.
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    # Subset of prompt_tokens served from provider-side prompt cache.
    # OpenAI: usage.prompt_tokens_details.cached_tokens
    # Gemini: usage_metadata.cached_content_token_count
    # Anthropic: usage.cache_read_input_tokens
    # Billing discount varies by vendor; cost_usd is NOT adjusted here —
    # this field is reported for observability only.
    cost_usd: float = 0.0

    @field_validator(
        "prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens", mode="before"
    )
    @classmethod
    def _coerce_none_int(cls, v: Any) -> Any:
        """Coerce None to 0 for integer token fields.

        Runs in ``mode="before"`` so pydantic never sees the raw None.
        """
        return 0 if v is None else v

    @field_validator("cost_usd", mode="before")
    @classmethod
    def _coerce_none_float(cls, v: Any) -> Any:
        """Coerce None to 0.0 for the float cost field."""
        return 0.0 if v is None else v


class LLMRequest(BaseModel, frozen=True):
    """Request payload sent to an LLM provider.

    Attributes:
        system_prompt: The system-level instruction prompt.
        user_content: The user message content.
        output_schema: Optional JSON schema for structured output.
        seed: Optional seed for deterministic generation.
        max_tokens: Maximum tokens to generate.
        temperature: Sampling temperature.
        model_override: Optional model name to override the routing default.
    """

    system_prompt: str = ""
    user_content: str = ""
    output_schema: dict | None = None
    seed: int | None = None
    max_tokens: int = 4096
    temperature: float = 0.7
    model_override: str | None = None
    provider_override: str | None = None  # Override routing provider for this request
    fresh_session: bool = False  # ACP: create isolated session for this call
    cache_system_prompt: bool = False  # Enable prompt caching for system prompt
    tools: list[ToolDefinition] | None = None  # Native tool calling definitions
    messages: list[dict[str, Any]] | None = (
        None  # Multi-turn conversation (overrides system_prompt + user_content)
    )
    tool_choice: str | None = None  # "auto" | "required" | "none" | None=provider default

    # Extended / native thinking opt-in. Currently honored by Anthropic;
    # Gemini thinking stays hardcoded off (see google.py). OpenAI ignores.
    thinking_enabled: bool = False
    thinking_budget_tokens: int = 2048  # Anthropic min is 1024 (clamped at provider)

    # PMF Plan Phase 4C Step 8 — ReplayLLMProvider interception.
    # When ``replay_mode=True``, ``LLMRouter.route`` delegates to
    # the registered ``"replay"`` provider instead of resolving
    # via engine/use-case routing. Default False preserves
    # non-replay behaviour exactly.
    replay_mode: bool = False
    # Lookup key for ReplayLLMProvider. Expected keys:
    # ``session_id``, ``actor_id``, ``activation_id``. Ignored
    # when ``replay_mode=False``.
    replay_context: dict[str, Any] | None = None


class LLMResponse(BaseModel, frozen=True):
    """Response returned from an LLM provider.

    Attributes:
        content: The raw text content of the response.
        structured_output: Parsed structured output if an output schema was used.
        usage: Token usage and cost information.
        model: The model that generated the response.
        provider: The provider that served the request.
        latency_ms: Wall-clock latency in milliseconds.
        error: Explicit error message when the request failed, or ``None`` on success.
    """

    content: str = ""
    structured_output: dict | list | None = None
    tool_calls: list[ToolCall] | None = None  # Parsed native tool calls
    usage: LLMUsage = LLMUsage()
    model: str = ""
    provider: str = ""
    latency_ms: float = 0.0
    error: str | None = None
    provider_metadata: dict[str, Any] | None = None


class LLMStreamChunk(BaseModel, frozen=True):
    """One chunk yielded by ``LLMProvider.stream_generate`` /
    ``LLMRouter.route_streaming``.

    Surfaces ``tnl/llm-router-streaming-surface.tnl``.

    Attributes:
        content_delta: Incremental content text for this chunk. May
            be empty (e.g., a chunk that carries only metadata or a
            usage update).
        usage_delta: Incremental usage from this chunk. ``None``
            when the provider doesn't report mid-stream usage; the
            FINAL chunk always carries the cumulative ``LLMUsage``
            so callers can total spend without re-aggregating.
        is_final: ``True`` only on the last chunk. Lets callers
            detect end-of-stream without relying on iterator
            exhaustion.
        provider: The provider that produced this chunk. Stamped on
            every chunk for observability.
        model: The model that produced this chunk. Stamped on every
            chunk for observability.
        error: Populated when the stream fails mid-flight. The
            error-bearing chunk is the LAST chunk yielded; the
            iterator stops after it. ``content_delta`` may be
            partial (whatever arrived before the error).
    """

    content_delta: str = ""
    usage_delta: LLMUsage | None = None
    is_final: bool = False
    provider: str = ""
    model: str = ""
    error: str | None = None
    # Opaque per-turn metadata the provider wants round-tripped on the next
    # request. Anthropic uses this to carry extended-thinking blocks
    # (``{"thinking_blocks": [{"type": "thinking", ...}, ...]}``). The agency
    # engine stashes this on the corresponding assistant message dict as
    # ``_provider_metadata`` so the same provider can read it back when
    # rebuilding history on the next turn. Other providers never read it.


class ProviderInfo(BaseModel, frozen=True):
    """Metadata about an LLM provider instance.

    Attributes:
        name: Human-readable provider name.
        type: Provider type identifier (e.g. ``"anthropic"``, ``"openai_compatible"``).
        base_url: Optional base URL for the provider API.
        available_models: List of model names available from this provider.
    """

    name: str = ""
    type: str = ""
    base_url: str | None = None
    available_models: list[str] = []


# ---------------------------------------------------------------------------
# Embeddings (PMF Plan Phase 4B Step 3.5 — G3 of the gap analysis)
# ---------------------------------------------------------------------------
#
# Separate request/response shape from chat completions — embeddings
# take a list of strings and return a list of vectors, and have no
# concept of temperature / tool calls / structured output. Reusing
# LLMRequest/LLMResponse would force bogus defaults everywhere.
#
# Usage is reported via the shared ``LLMUsage`` so the tracker + ledger
# see embedding calls alongside generation calls for unified budget
# accounting (G10 of the plan — BudgetEngine reads LLMCallEntry rows).


class EmbeddingRequest(BaseModel, frozen=True):
    """Request payload for an embedding call.

    Each input text is capped at ``_MAX_EMBED_TEXT_LEN`` characters and
    the batch is capped at ``_MAX_EMBED_BATCH`` items so a caller can't
    accidentally DoS the router or blow the provider's per-request limit.
    """

    texts: list[str] = Field(min_length=1, max_length=256)
    """Non-empty batch of texts. Each must be non-empty and bounded
    in length — validated below."""

    model_override: str | None = None
    provider_override: str | None = None

    @field_validator("texts")
    @classmethod
    def _validate_texts(cls, v: list[str]) -> list[str]:
        for t in v:
            if not t:
                raise ValueError(
                    "EmbeddingRequest.texts: every input must be a "
                    "non-empty string (empty/whitespace-only rejected)."
                )
            if len(t) > 10_000:
                raise ValueError(
                    f"EmbeddingRequest.texts: input length {len(t)} "
                    f"exceeds the 10000-char cap. Chunk before embedding."
                )
        return v


class EmbeddingResponse(BaseModel, frozen=True):
    """Response from an embedding call.

    ``vectors[i]`` is the embedding for ``request.texts[i]``. On
    transport error, ``error`` is populated and ``vectors`` is empty
    so callers can branch without a KeyError.
    """

    vectors: list[list[float]] = Field(default_factory=list)
    model: str = ""
    provider: str = ""
    usage: LLMUsage = LLMUsage()
    latency_ms: float = 0.0
    error: str | None = None

    @field_validator("vectors")
    @classmethod
    def _validate_vectors(cls, v: list[list[float]]) -> list[list[float]]:
        # Uniform non-zero dimensionality. A response with vectors
        # of mixed widths is a provider bug. A zero-dim vector
        # (e.g. ``[[]]``) is also a provider bug — downstream
        # cosine similarity would NaN-propagate. Surface both at
        # the model boundary so downstream code never sees garbage.
        # (C3 of the bug-bounty review added the zero-dim rejection.)
        if not v:
            return v
        dims = len(v[0])
        if dims == 0:
            raise ValueError(
                "EmbeddingResponse.vectors contains zero-dimension "
                "vectors. An embedding vector with no components is "
                "meaningless and would NaN-propagate through cosine "
                "similarity. Provider returned malformed data."
            )
        for i, row in enumerate(v):
            if len(row) != dims:
                raise ValueError(
                    f"EmbeddingResponse.vectors[{i}] has dim={len(row)}, "
                    f"expected {dims} (first vector's dim). Provider "
                    f"returned mismatched vector widths."
                )
        return v
