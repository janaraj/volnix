"""LLM provider module for the Terrarium framework.

Provides a unified interface for multiple LLM providers (Anthropic, OpenAI-
compatible, Google, ACP, CLI, mock), request routing based on engine/use-case,
and usage tracking integrated with the event ledger.

Re-exports the primary public API surface::

    from terrarium.llm import LLMRouter, LLMRequest, LLMResponse, ProviderRegistry
"""

from terrarium.llm.provider import LLMProvider
from terrarium.llm.providers.acp_client import ACPClientProvider
from terrarium.llm.providers.cli_subprocess import CLISubprocessProvider
from terrarium.llm.registry import ProviderRegistry
from terrarium.llm.router import LLMRouter
from terrarium.llm.secrets import ChainResolver, EnvVarResolver, FileResolver, SecretResolver
from terrarium.llm.conversation import ConversationManager, ConversationTurn, Session
from terrarium.llm.tracker import UsageTracker
from terrarium.llm.types import LLMRequest, LLMResponse, LLMUsage, ProviderInfo, ProviderType

__all__ = [
    "ACPClientProvider",
    "CLISubprocessProvider",
    "ChainResolver",
    "ConversationManager",
    "ConversationTurn",
    "EnvVarResolver",
    "FileResolver",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "LLMRouter",
    "LLMUsage",
    "ProviderInfo",
    "ProviderRegistry",
    "ProviderType",
    "SecretResolver",
    "Session",
    "UsageTracker",
]
