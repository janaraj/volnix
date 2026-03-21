"""Data types for the LLM provider module.

Defines request, response, usage, and provider-info models used across
all LLM providers and the routing layer.
"""

from __future__ import annotations

from pydantic import BaseModel


class LLMUsage(BaseModel, frozen=True):
    """Token usage and cost for a single LLM call.

    Attributes:
        prompt_tokens: Number of tokens in the prompt.
        completion_tokens: Number of tokens in the completion.
        total_tokens: Total tokens consumed.
        cost_usd: Estimated cost in US dollars.
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0


class LLMRequest(BaseModel):
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


class LLMResponse(BaseModel, frozen=True):
    """Response returned from an LLM provider.

    Attributes:
        content: The raw text content of the response.
        structured_output: Parsed structured output if an output schema was used.
        usage: Token usage and cost information.
        model: The model that generated the response.
        provider: The provider that served the request.
        latency_ms: Wall-clock latency in milliseconds.
    """

    content: str = ""
    structured_output: dict | None = None
    usage: LLMUsage = LLMUsage()
    model: str = ""
    provider: str = ""
    latency_ms: float = 0.0


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
