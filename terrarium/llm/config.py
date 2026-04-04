"""LLM-specific configuration models.

These models mirror the LLM section of the TOML configuration and are used
by the provider registry and router to resolve providers, models, and
per-engine routing rules.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LLMProviderEntry(BaseModel):
    model_config = ConfigDict(frozen=True)
    """Configuration entry for a single LLM provider.

    Attributes:
        type: Provider type identifier (e.g. ``"anthropic"``, ``"openai_compatible"``).
        base_url: Optional base URL for the provider API endpoint.
        api_key_ref: Reference to the API key (e.g. env var name or secret path).
        default_model: The default model to use for this provider.
        max_tokens: Default maximum tokens to generate.
        temperature: Default sampling temperature.
        timeout_seconds: Request timeout in seconds.
        command: CLI command path (for ``"cli"`` type providers).
        args: CLI command arguments (for ``"cli"`` type providers).
        agent_url: ACP agent URL (for ``"acp"`` type providers).
        agent_name: ACP agent name (for ``"acp"`` type providers).
    """

    type: str = ""
    base_url: str | None = None
    api_key_ref: str = ""
    default_model: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout_seconds: float = 30.0
    # CLI-specific
    command: str = ""
    args: list[str] = []
    # ACP-specific (stdio JSON-RPC)
    auth_method: str = ""
    # Legacy ACP-over-HTTP fields (unused by stdio provider, kept for compat)
    agent_url: str = ""
    agent_name: str = "default"


class LLMRoutingEntry(BaseModel):
    model_config = ConfigDict(frozen=True)
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
    model_config = ConfigDict(frozen=True)
    """Top-level LLM configuration aggregating providers and routing rules.

    Attributes:
        defaults: Default provider configuration used as a fallback.
        providers: Named provider configurations.
        routing: Named routing entries mapping engine/use-case to provider+model.
    """

    defaults: LLMProviderEntry = LLMProviderEntry()
    providers: dict[str, LLMProviderEntry] = {}
    routing: dict[str, LLMRoutingEntry] = {}
    max_concurrent: int = 10
    max_retries: int = 3
    retry_backoff_base: float = 1.0
    llm_debug: bool = False
