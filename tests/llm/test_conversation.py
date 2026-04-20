"""Tests for ConversationManager — multi-turn conversation management."""

import pytest

from volnix.llm.conversation import (
    ConversationManager,
    ConversationTurn,
    LLMConversationSession,
)
from volnix.llm.providers.mock import MockLLMProvider
from volnix.llm.types import LLMRequest, LLMResponse, LLMUsage


class MockRouter:
    """Mock router that delegates to a mock provider."""

    def __init__(self, provider=None):
        self._provider = provider or MockLLMProvider(seed=42)

    def get_provider_for(self, engine_name: str, use_case: str = "default"):
        return self._provider

    async def route(
        self, request: LLMRequest, engine_name: str, use_case: str = "default"
    ) -> LLMResponse:
        return await self._provider.generate(request)


def test_create_session():
    conv = ConversationManager()
    session_id = conv.create_session(system_prompt="You are helpful.")
    assert session_id.startswith("conv_")
    assert session_id in conv.list_sessions()


def test_create_session_with_metadata():
    conv = ConversationManager()
    session_id = conv.create_session(system_prompt="test", metadata={"engine": "world_compiler"})
    session = conv.get_session(session_id)
    assert session is not None
    assert session.metadata["engine"] == "world_compiler"


def test_end_session():
    conv = ConversationManager()
    session_id = conv.create_session()
    ended = conv.end_session(session_id)
    assert ended is not None
    assert session_id not in conv.list_sessions()


def test_end_nonexistent_session():
    conv = ConversationManager()
    assert conv.end_session("nonexistent") is None


def test_list_sessions():
    conv = ConversationManager()
    s1 = conv.create_session()
    conv.create_session()
    assert len(conv.list_sessions()) == 2
    conv.end_session(s1)
    assert len(conv.list_sessions()) == 1


@pytest.mark.asyncio
async def test_generate_single_turn():
    conv = ConversationManager()
    router = MockRouter()
    session_id = conv.create_session(system_prompt="You are helpful.")

    resp = await conv.generate(session_id, router, "Hello", engine_name="test")
    assert resp.content  # mock returns non-empty
    assert resp.error is None


@pytest.mark.asyncio
async def test_generate_builds_history():
    conv = ConversationManager()
    router = MockRouter()
    session_id = conv.create_session()

    await conv.generate(session_id, router, "Turn 1")
    await conv.generate(session_id, router, "Turn 2")

    history = conv.get_history(session_id)
    assert len(history) == 4  # 2 user + 2 assistant turns
    assert history[0].role == "user"
    assert history[0].content == "Turn 1"
    assert history[1].role == "assistant"
    assert history[2].role == "user"
    assert history[2].content == "Turn 2"


@pytest.mark.asyncio
async def test_generate_nonexistent_session():
    conv = ConversationManager()
    router = MockRouter()

    with pytest.raises(KeyError, match="not found"):
        await conv.generate("bad_id", router, "Hello")


@pytest.mark.asyncio
async def test_generate_error_not_recorded_in_history():
    """If provider returns error, assistant turn is not added to history."""

    class FailingProvider(MockLLMProvider):
        async def generate(self, request: LLMRequest) -> LLMResponse:
            return LLMResponse(content="", usage=LLMUsage(), error="fail")

    conv = ConversationManager()
    router = MockRouter(provider=FailingProvider())
    session_id = conv.create_session()

    resp = await conv.generate(session_id, router, "Hello")
    assert resp.error == "fail"

    history = conv.get_history(session_id)
    assert len(history) == 1  # only user turn, no assistant
    assert history[0].role == "user"


def test_clear_history():
    conv = ConversationManager()
    session_id = conv.create_session()
    session = conv.get_session(session_id)
    session.history.append(ConversationTurn(role="user", content="test"))
    assert len(conv.get_history(session_id)) == 1

    conv.clear_history(session_id)
    assert len(conv.get_history(session_id)) == 0
    assert session_id in conv.list_sessions()  # session still alive


@pytest.mark.asyncio
async def test_multi_turn_context_included():
    """Verify that previous turns are included in the prompt."""
    captured_requests: list[LLMRequest] = []

    class CapturingProvider(MockLLMProvider):
        async def generate(self, request: LLMRequest) -> LLMResponse:
            captured_requests.append(request)
            return await super().generate(request)

    conv = ConversationManager()
    router = MockRouter(provider=CapturingProvider(seed=42))
    session_id = conv.create_session(system_prompt="Be helpful.")

    await conv.generate(session_id, router, "First message")
    await conv.generate(session_id, router, "Second message")

    # Second request should contain history
    assert len(captured_requests) == 2
    second_content = captured_requests[1].user_content
    assert "First message" in second_content
    assert "Second message" in second_content


@pytest.mark.asyncio
async def test_session_dataclass():
    session = LLMConversationSession(session_id="test", system_prompt="prompt")
    assert session.session_id == "test"
    assert session.system_prompt == "prompt"
    assert session.history == []
    assert session.provider_state == {}


# ─── Context Retention Tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_context_grows_each_turn():
    """Each turn includes ALL previous turns, not just the last one."""
    captured: list[LLMRequest] = []

    class CapturingProvider(MockLLMProvider):
        async def generate(self, request: LLMRequest) -> LLMResponse:
            captured.append(request)
            return await super().generate(request)

    conv = ConversationManager()
    router = MockRouter(provider=CapturingProvider(seed=1))
    sid = conv.create_session(system_prompt="Context test")

    await conv.generate(sid, router, "Turn A")
    await conv.generate(sid, router, "Turn B")
    await conv.generate(sid, router, "Turn C")

    # Turn 1: no history, just "Turn A"
    assert "Turn A" in captured[0].user_content
    assert "Turn B" not in captured[0].user_content

    # Turn 2: contains Turn A + response + Turn B
    assert "Turn A" in captured[1].user_content
    assert "Turn B" in captured[1].user_content
    assert "Turn C" not in captured[1].user_content

    # Turn 3: contains Turn A + Turn B + Turn C (full history)
    assert "Turn A" in captured[2].user_content
    assert "Turn B" in captured[2].user_content
    assert "Turn C" in captured[2].user_content


@pytest.mark.asyncio
async def test_system_prompt_passed_every_turn():
    """System prompt is included in every turn, not just the first."""
    captured: list[LLMRequest] = []

    class CapturingProvider(MockLLMProvider):
        async def generate(self, request: LLMRequest) -> LLMResponse:
            captured.append(request)
            return await super().generate(request)

    conv = ConversationManager()
    router = MockRouter(provider=CapturingProvider(seed=1))
    sid = conv.create_session(system_prompt="You are a data generator.")

    await conv.generate(sid, router, "Generate customers")
    await conv.generate(sid, router, "Now generate charges")

    assert captured[0].system_prompt == "You are a data generator."
    assert captured[1].system_prompt == "You are a data generator."


@pytest.mark.asyncio
async def test_assistant_response_in_history():
    """The assistant's response is included in subsequent context."""
    captured: list[LLMRequest] = []

    class EchoProvider(MockLLMProvider):
        """Returns the user content as the response."""

        async def generate(self, request: LLMRequest) -> LLMResponse:
            captured.append(request)
            return LLMResponse(
                content=f"I processed: {request.user_content[:30]}",
                usage=LLMUsage(),
                model="echo",
                provider="mock",
            )

    conv = ConversationManager()
    router = MockRouter(provider=EchoProvider())
    sid = conv.create_session()

    await conv.generate(sid, router, "Hello")
    await conv.generate(sid, router, "What did you say?")

    # Second turn should see the assistant's first response in context
    assert "I processed:" in captured[1].user_content
    assert "Hello" in captured[1].user_content


@pytest.mark.asyncio
async def test_separate_sessions_have_separate_context():
    """Two sessions don't share history."""
    captured: list[LLMRequest] = []

    class CapturingProvider(MockLLMProvider):
        async def generate(self, request: LLMRequest) -> LLMResponse:
            captured.append(request)
            return await super().generate(request)

    conv = ConversationManager()
    router = MockRouter(provider=CapturingProvider(seed=1))

    sid1 = conv.create_session()
    sid2 = conv.create_session()

    await conv.generate(sid1, router, "Session 1 message")
    await conv.generate(sid2, router, "Session 2 message")
    await conv.generate(sid1, router, "Session 1 follow-up")

    # Session 1 follow-up should contain Session 1 history, NOT Session 2
    third_content = captured[2].user_content
    assert "Session 1 message" in third_content
    assert "Session 2 message" not in third_content


@pytest.mark.asyncio
async def test_cleared_history_starts_fresh():
    """After clear_history, the next turn has no context."""
    captured: list[LLMRequest] = []

    class CapturingProvider(MockLLMProvider):
        async def generate(self, request: LLMRequest) -> LLMResponse:
            captured.append(request)
            return await super().generate(request)

    conv = ConversationManager()
    router = MockRouter(provider=CapturingProvider(seed=1))
    sid = conv.create_session()

    await conv.generate(sid, router, "Before clear")
    conv.clear_history(sid)
    await conv.generate(sid, router, "After clear")

    # After clear, no history from before
    assert "Before clear" not in captured[1].user_content
    assert "After clear" in captured[1].user_content


@pytest.mark.asyncio
async def test_provider_routing_uses_correct_strategy():
    """Anthropic-named provider takes the Anthropic path (with caching context)."""
    captured: list[LLMRequest] = []

    class AnthropicMock(MockLLMProvider):
        provider_name = "anthropic"

        async def generate(self, request: LLMRequest) -> LLMResponse:
            captured.append(request)
            return await super().generate(request)

    conv = ConversationManager()
    router = MockRouter(provider=AnthropicMock(seed=1))
    sid = conv.create_session(system_prompt="Anthropic system")

    await conv.generate(sid, router, "First")
    await conv.generate(sid, router, "Second")

    # Anthropic strategy uses "Human:"/"Assistant:" format
    assert "Human:" in captured[1].user_content or "First" in captured[1].user_content


@pytest.mark.asyncio
async def test_five_turn_conversation():
    """Simulate a realistic 5-turn conversation."""
    captured: list[LLMRequest] = []
    turn_count = 0

    class NumberedProvider(MockLLMProvider):
        async def generate(self, request: LLMRequest) -> LLMResponse:
            nonlocal turn_count
            turn_count += 1
            captured.append(request)
            return LLMResponse(
                content=f"Response #{turn_count}",
                usage=LLMUsage(prompt_tokens=10 * turn_count, completion_tokens=5),
                model="test",
                provider="mock",
            )

    conv = ConversationManager()
    router = MockRouter(provider=NumberedProvider())
    sid = conv.create_session(system_prompt="Multi-turn test")

    for i in range(5):
        resp = await conv.generate(sid, router, f"Question {i + 1}")
        assert resp.content == f"Response #{i + 1}"

    # Final history should have 10 turns (5 user + 5 assistant)
    history = conv.get_history(sid)
    assert len(history) == 10

    # Last request should contain all previous turns
    last_content = captured[4].user_content
    for i in range(1, 5):
        assert f"Question {i}" in last_content
        assert f"Response #{i}" in last_content


# ─── Real API Context Retention Tests (skip if no keys) ─────────────

import os

OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
RUN_REAL = os.environ.get("VOLNIX_RUN_REAL_API_TESTS", "").lower() in ("1", "true", "yes")


ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")
GOOGLE_KEY = os.environ.get("GOOGLE_API_KEY")

skipif_no_real_openai = pytest.mark.skipif(
    not (OPENAI_KEY and RUN_REAL),
    reason="OPENAI_API_KEY + VOLNIX_RUN_REAL_API_TESTS required",
)
skipif_no_real_anthropic = pytest.mark.skipif(
    not (ANTHROPIC_KEY and RUN_REAL),
    reason="ANTHROPIC_API_KEY + VOLNIX_RUN_REAL_API_TESTS required",
)
skipif_no_real_google = pytest.mark.skipif(
    not (GOOGLE_KEY and RUN_REAL),
    reason="GOOGLE_API_KEY + VOLNIX_RUN_REAL_API_TESTS required",
)


async def _real_context_retention_test(router, engine_name: str):
    """Shared logic: tell a secret word, ask to recall it."""
    conv = ConversationManager()
    sid = conv.create_session(
        system_prompt="You have perfect memory. When asked to remember something, confirm you will. When asked to recall, respond with ONLY the exact value."
    )

    # Turn 1: tell it a secret
    resp1 = await conv.generate(
        sid,
        router,
        "Remember this code: VOLNIX42. Just confirm you remember it.",
        engine_name=engine_name,
        max_tokens=100,
    )
    assert resp1.error is None, f"Turn 1 failed: {resp1.error}"
    assert resp1.content, "Turn 1 returned empty content"

    # Turn 2: ask to recall
    resp2 = await conv.generate(
        sid,
        router,
        "What was the code I asked you to remember? Reply with just the code.",
        engine_name=engine_name,
        max_tokens=100,
    )
    assert resp2.error is None, f"Turn 2 failed: {resp2.error}"
    assert "VOLNIX42" in resp2.content.upper(), (
        f"LLM did not recall secret. Response: {resp2.content}"
    )

    # Verify history was built
    history = conv.get_history(sid)
    assert len(history) == 4  # 2 user + 2 assistant

    conv.end_session(sid)
    return resp1, resp2


@skipif_no_real_openai
@pytest.mark.asyncio
async def test_real_openai_context_retention():
    """Real OpenAI: verify multi-turn context is retained."""
    from volnix.llm.config import LLMConfig, LLMProviderEntry, LLMRoutingEntry
    from volnix.llm.providers.openai_compat import OpenAICompatibleProvider
    from volnix.llm.registry import ProviderRegistry
    from volnix.llm.router import LLMRouter

    registry = ProviderRegistry()
    registry.register(
        "openai",
        OpenAICompatibleProvider(
            api_key=OPENAI_KEY,
            base_url="https://api.openai.com/v1",
            default_model="gpt-5.4-mini",
        ),
    )
    config = LLMConfig(
        defaults=LLMProviderEntry(type="openai_compatible", default_model="gpt-5.4-mini"),
        providers={
            "openai": LLMProviderEntry(
                type="openai_compatible", base_url="https://api.openai.com/v1"
            )
        },
        routing={"test": LLMRoutingEntry(provider="openai", model="gpt-5.4-mini")},
    )
    router = LLMRouter(config=config, registry=registry)
    await _real_context_retention_test(router, "test")


@skipif_no_real_anthropic
@pytest.mark.asyncio
async def test_real_anthropic_context_retention():
    """Real Anthropic: verify multi-turn context is retained via prompt caching."""
    from volnix.llm.config import LLMConfig, LLMProviderEntry, LLMRoutingEntry
    from volnix.llm.providers.anthropic import AnthropicProvider
    from volnix.llm.registry import ProviderRegistry
    from volnix.llm.router import LLMRouter

    registry = ProviderRegistry()
    registry.register(
        "anthropic",
        AnthropicProvider(
            api_key=ANTHROPIC_KEY,
            default_model="claude-sonnet-4-6",
        ),
    )
    config = LLMConfig(
        defaults=LLMProviderEntry(type="anthropic", default_model="claude-sonnet-4-6"),
        providers={"anthropic": LLMProviderEntry(type="anthropic")},
        routing={"test": LLMRoutingEntry(provider="anthropic", model="claude-sonnet-4-6")},
    )
    router = LLMRouter(config=config, registry=registry)
    await _real_context_retention_test(router, "test")


@skipif_no_real_google
@pytest.mark.asyncio
async def test_real_google_context_retention():
    """Real Google Gemini: verify multi-turn context is retained."""
    from volnix.llm.config import LLMConfig, LLMProviderEntry, LLMRoutingEntry
    from volnix.llm.providers.google import GoogleNativeProvider
    from volnix.llm.registry import ProviderRegistry
    from volnix.llm.router import LLMRouter

    registry = ProviderRegistry()
    registry.register(
        "google",
        GoogleNativeProvider(
            api_key=GOOGLE_KEY,
            default_model="gemini-3-flash-preview",
        ),
    )
    config = LLMConfig(
        defaults=LLMProviderEntry(type="google", default_model="gemini-3-flash-preview"),
        providers={"google": LLMProviderEntry(type="google")},
        routing={"test": LLMRoutingEntry(provider="google", model="gemini-3-flash-preview")},
    )
    router = LLMRouter(config=config, registry=registry)
    await _real_context_retention_test(router, "test")
