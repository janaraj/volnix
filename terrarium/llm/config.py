"""LLM-specific configuration models.

These models mirror the LLM section of the TOML configuration and are used
by the provider registry and router to resolve providers, models, and
per-engine routing rules.
"""

from __future__ import annotations

from pydantic import BaseModel


class LLMProviderEntry(BaseModel):
    """Configuration entry for a single LLM provider.

    Attributes:
        type: Provider type identifier (e.g. ``"anthropic"``, ``"openai_compatible"``).
        base_url: Optional base URL for the provider API endpoint.
        api_key_ref: Reference to the API key (e.g. env var name or secret path).
        default_model: The default model to use for this provider.
        max_tokens: Default maximum tokens to generate.
        temperature: Default sampling temperature.
        timeout_seconds: Request timeout in seconds.
    """

    type: str = ""
    base_url: str | None = None
    api_key_ref: str = ""
    default_model: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout_seconds: float = 30.0


class LLMRoutingEntry(BaseModel):
    """Routing rule mapping an engine/use-case to a specific provider and model.

    Attributes:
        provider: Name of the provider to route to.
        model: Model identifier to use.
        max_tokens: Optional max-token override for this route.
        temperature: Optional temperature override for this route.
    """

    provider: str = ""
    model: str = ""
    max_tokens: int | None = None
    temperature: float | None = None


class LLMConfig(BaseModel):
    """Top-level LLM configuration aggregating providers and routing rules.

    Attributes:
        defaults: Default provider configuration used as a fallback.
        providers: Named provider configurations.
        routing: Named routing entries mapping engine/use-case to provider+model.
    """

    defaults: LLMProviderEntry = LLMProviderEntry()
    providers: dict[str, LLMProviderEntry] = {}
    routing: dict[str, LLMRoutingEntry] = {}
