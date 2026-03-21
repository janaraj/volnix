"""LLM provider module for the Terrarium framework.

Provides a unified interface for multiple LLM providers (Anthropic, OpenAI-
compatible, Google, mock), request routing based on engine/use-case, and
usage tracking integrated with the event ledger.

Re-exports the primary public API surface::

    from terrarium.llm import LLMRouter, LLMRequest, LLMResponse, ProviderRegistry
"""

from terrarium.llm.provider import LLMProvider
from terrarium.llm.registry import ProviderRegistry
from terrarium.llm.router import LLMRouter
from terrarium.llm.tracker import UsageTracker
from terrarium.llm.types import LLMRequest, LLMResponse, LLMUsage, ProviderInfo

__all__ = [
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "LLMRouter",
    "LLMUsage",
    "ProviderInfo",
    "ProviderRegistry",
    "UsageTracker",
]
