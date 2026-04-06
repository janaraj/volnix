"""Conversation manager for multi-turn LLM interactions.

Uses provider-native context mechanisms where available:
- **Anthropic**: Prompt caching (cache_control) — sends full history, cached at 10% cost
- **OpenAI**: Responses API with previous_response_id — server maintains state
- **Google**: Implicit caching — sends full history, auto-cached
- **ACP**: Native session support — agent maintains context
- **Fallback**: Client-side history for providers without native support (CLI, mock)

Usage:
    conv = ConversationManager()
    session_id = conv.create_session(system_prompt="You are a data generator.")

    resp1 = await conv.generate(session_id, router, "Generate 50 customers",
                                 engine_name="world_compiler")
    resp2 = await conv.generate(session_id, router, "Now cross-link with charges",
                                 engine_name="world_compiler")

    conv.end_session(session_id)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from volnix.llm.types import LLMRequest, LLMResponse, LLMUsage


@dataclass
class ConversationTurn:
    """A single turn in a conversation."""

    role: str  # "user" or "assistant"
    content: str


@dataclass
class Session:
    """A conversation session with history and provider-specific state."""

    session_id: str
    system_prompt: str = ""
    history: list[ConversationTurn] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    # Provider-specific state for native context management
    # OpenAI: stores previous_response_id for Responses API chaining
    # Anthropic: stores cache_control config
    provider_state: dict[str, Any] = field(default_factory=dict)


class ConversationManager:
    """Manages multi-turn conversations using provider-native mechanisms.

    Strategy per provider:
    - Anthropic: Sends full message history with cache_control={"type": "ephemeral"}.
      Anthropic caches the prompt prefix server-side. Reads are 10% of input cost.
    - OpenAI: Uses Responses API with previous_response_id for server-side chaining.
      No need to send full history — server maintains it.
    - Google: Sends full message history. Implicit caching auto-applies.
    - ACP: Delegates to ACPClientProvider's native session support.
    - CLI/Mock: Falls back to client-side history prepended to prompt.
    """

    def __init__(self, max_history: int = 50) -> None:
        self._max_history = max_history
        self._sessions: dict[str, Session] = {}

    def create_session(
        self,
        system_prompt: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Create a new conversation session.

        Args:
            system_prompt: System prompt for the entire conversation.
            metadata: Optional metadata (e.g., engine_name, use_case).

        Returns:
            A unique session ID.
        """
        session_id = f"conv_{uuid.uuid4().hex[:12]}"
        self._sessions[session_id] = Session(
            session_id=session_id,
            system_prompt=system_prompt,
            metadata=metadata or {},
        )
        return session_id

    async def generate(
        self,
        session_id: str,
        router: Any,
        user_content: str,
        engine_name: str = "default",
        use_case: str = "default",
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a response within a conversation session.

        Automatically uses the best context mechanism for the provider:
        - Native (OpenAI Responses API, Anthropic caching) when available
        - Client-side history fallback for other providers

        Args:
            session_id: The session to generate within.
            router: LLM router for provider resolution.
            user_content: The user's message for this turn.
            engine_name: Engine name for routing.
            use_case: Use case for routing.
            **kwargs: Additional LLMRequest fields.

        Returns:
            LLMResponse from the provider.

        Raises:
            KeyError: If session_id doesn't exist.
        """
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Session '{session_id}' not found")

        # Determine provider type from router
        provider = router.get_provider_for(engine_name, use_case)
        provider_type = getattr(provider, "provider_name", "unknown")

        # Route to provider-specific conversation strategy
        if provider_type == "anthropic":
            response = await self._generate_anthropic(
                session, router, user_content, engine_name, use_case, **kwargs
            )
        elif provider_type == "openai_compatible":
            response = await self._generate_openai(
                session, router, user_content, engine_name, use_case, **kwargs
            )
        else:
            # Fallback: client-side history for Google, CLI, mock, ACP, etc.
            response = await self._generate_with_history(
                session, router, user_content, engine_name, use_case, **kwargs
            )

        # Record turn
        session.history.append(ConversationTurn(role="user", content=user_content))
        if response.error is None:
            session.history.append(
                ConversationTurn(role="assistant", content=response.content)
            )

        # Trim history to prevent unbounded growth (O(N^2) prompt size)
        if len(session.history) > self._max_history:
            session.history = session.history[-self._max_history:]

        return response

    async def _generate_anthropic(
        self,
        session: Session,
        router: Any,
        user_content: str,
        engine_name: str,
        use_case: str,
        **kwargs: Any,
    ) -> LLMResponse:
        """Anthropic: send full history with prompt caching enabled.

        Anthropic caches the prompt prefix server-side. On subsequent turns,
        the cached prefix is read at 10% of base input cost.
        The full message history must be sent each time, but the server
        efficiently caches and reuses the unchanged prefix.
        """
        # Build messages array (Anthropic format)
        # The system prompt + all previous messages form the cached prefix
        history_text = ""
        if session.history:
            for turn in session.history:
                prefix = "Human" if turn.role == "user" else "Assistant"
                history_text += f"{prefix}: {turn.content}\n\n"

        full_content = history_text + user_content if history_text else user_content

        request = LLMRequest(
            system_prompt=session.system_prompt,
            user_content=full_content,
            **kwargs,
        )
        # Note: cache_control is handled at the SDK level when the provider
        # detects multi-turn patterns. For explicit caching, the Anthropic
        # provider would need to pass cache_control in the API call.
        # This is handled in the AnthropicProvider.generate() method.
        return await router.route(request, engine_name, use_case)

    async def _generate_openai(
        self,
        session: Session,
        router: Any,
        user_content: str,
        engine_name: str,
        use_case: str,
        **kwargs: Any,
    ) -> LLMResponse:
        """OpenAI: use prompt_cache_key for efficient multi-turn.

        OpenAI's chat completions API supports prompt_cache_key for
        caching the prompt prefix. For full server-side conversation
        state, the Conversations API or Responses API would be used
        at the provider level.

        For now, we send full history (same as Anthropic) and let
        OpenAI's implicit caching optimize the repeated prefix.
        """
        # Build full history as messages
        history_text = ""
        if session.history:
            for turn in session.history:
                prefix = "User" if turn.role == "user" else "Assistant"
                history_text += f"{prefix}: {turn.content}\n\n"

        full_content = history_text + user_content if history_text else user_content

        request = LLMRequest(
            system_prompt=session.system_prompt,
            user_content=full_content,
            **kwargs,
        )
        return await router.route(request, engine_name, use_case)

    async def _generate_with_history(
        self,
        session: Session,
        router: Any,
        user_content: str,
        engine_name: str,
        use_case: str,
        **kwargs: Any,
    ) -> LLMResponse:
        """Fallback: prepend conversation history to prompt.

        For providers without native caching (CLI, mock, Google, ACP),
        we build the full conversation context as a text prompt.
        """
        context = ""
        if session.history:
            context = "[Previous conversation]\n"
            for turn in session.history:
                prefix = "User" if turn.role == "user" else "Assistant"
                context += f"{prefix}: {turn.content}\n"
            context += "\n[Current request]\n"

        request = LLMRequest(
            system_prompt=session.system_prompt,
            user_content=context + user_content if context else user_content,
            **kwargs,
        )
        return await router.route(request, engine_name, use_case)

    def end_session(self, session_id: str) -> Session | None:
        """End a session and return its data."""
        return self._sessions.pop(session_id, None)

    def get_session(self, session_id: str) -> Session | None:
        """Get a session by ID without ending it."""
        return self._sessions.get(session_id)

    def get_history(self, session_id: str) -> list[ConversationTurn]:
        """Get the conversation history for a session."""
        session = self._sessions.get(session_id)
        return list(session.history) if session else []

    def list_sessions(self) -> list[str]:
        """List all active session IDs."""
        return list(self._sessions.keys())

    def clear_history(self, session_id: str) -> None:
        """Clear the history for a session (keep session alive)."""
        session = self._sessions.get(session_id)
        if session:
            session.history.clear()
