"""LLM provider module for the Volnix framework.

Provides a unified interface for multiple LLM providers (Anthropic, OpenAI-
compatible, Google, ACP, CLI, mock), request routing based on engine/use-case,
and usage tracking integrated with the event ledger.

Re-exports the primary public API surface::

    from volnix.llm import LLMRouter, LLMRequest, LLMResponse, ProviderRegistry
"""

from volnix.llm.conversation import (
    ConversationManager,
    ConversationTurn,
    LLMConversationSession,
)
from volnix.llm.provider import LLMProvider
from volnix.llm.providers.acp_client import ACPClientProvider
from volnix.llm.providers.cli_subprocess import CLISubprocessProvider
from volnix.llm.registry import ProviderRegistry
from volnix.llm.router import LLMRouter
from volnix.llm.secrets import ChainResolver, EnvVarResolver, FileResolver, SecretResolver
from volnix.llm.tracker import UsageTracker
from volnix.llm.types import (
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
    LLMUsage,
    ProviderInfo,
    ProviderType,
)

__all__ = [
    "ACPClientProvider",
    "CLISubprocessProvider",
    "ChainResolver",
    "ConversationManager",
    "ConversationTurn",
    "EnvVarResolver",
    "FileResolver",
    "LLMConversationSession",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "LLMRouter",
    "LLMStreamChunk",
    "LLMUsage",
    "ProviderInfo",
    "ProviderRegistry",
    "ProviderType",
    "SecretResolver",
    "UsageTracker",
]
