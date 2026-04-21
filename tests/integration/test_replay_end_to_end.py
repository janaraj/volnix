"""Phase 4C Step 8 — end-to-end replay integration test (post-impl
audit M5).

Exercises the full stack: pre-populated ledger → Router interception
→ ReplayLLMProvider → Ledger query → reconstructed LLMResponse.
Proves that a caller can replay a recorded NPC utterance through
the public API without touching private attributes.

The unit tests in ``tests/llm/test_replay_provider.py`` mock at
the provider level; this test exercises the router seam so a
future refactor of routing semantics catches regressions at the
integration boundary.

Negative ratio: 1/2 = 50%.
"""

from __future__ import annotations

from volnix.core.types import ActivationId, ActorId, SessionId
from volnix.ledger.config import LedgerConfig
from volnix.ledger.entries import LLMUtteranceEntry
from volnix.ledger.ledger import Ledger
from volnix.llm.config import LLMConfig, LLMProviderEntry
from volnix.llm.providers.replay import ReplayLLMProvider
from volnix.llm.registry import ProviderRegistry
from volnix.llm.router import LLMRouter
from volnix.llm.types import LLMRequest
from volnix.persistence.manager import create_database


async def _seed_ledger_with_utterance(content: str) -> Ledger:
    db = await create_database(":memory:", wal_mode=False)
    ledger = Ledger(LedgerConfig(), db)
    await ledger.initialize()
    await ledger.append(
        LLMUtteranceEntry(
            actor_id=ActorId("npc-alice"),
            activation_id=ActivationId("act-recorded"),
            session_id=SessionId("sess-live-run"),
            role="system",
            content="you are alice",
            content_hash=f"sha256:{'0' * 64}",
            tick=0,
            sequence=0,
        )
    )
    await ledger.append(
        LLMUtteranceEntry(
            actor_id=ActorId("npc-alice"),
            activation_id=ActivationId("act-recorded"),
            session_id=SessionId("sess-live-run"),
            role="user",
            content="hello",
            content_hash=f"sha256:{'1' * 64}",
            tick=0,
            sequence=1,
        )
    )
    await ledger.append(
        LLMUtteranceEntry(
            actor_id=ActorId("npc-alice"),
            activation_id=ActivationId("act-recorded"),
            session_id=SessionId("sess-live-run"),
            role="assistant",
            content="hi there",
            content_hash=f"sha256:{'2' * 64}",
            tokens=4,
            tick=0,
            sequence=2,
        )
    )
    return ledger


def _router_with_replay(ledger: Ledger) -> LLMRouter:
    cfg = LLMConfig(
        providers={"mock": LLMProviderEntry(type="mock")},
        routing={},
        defaults=LLMProviderEntry(type="mock"),
    )
    router = LLMRouter(registry=ProviderRegistry(), config=cfg)
    # Use the public API — mirrors how VolnixApp wires things up.
    router.register_provider("replay", ReplayLLMProvider(ledger))
    return router


async def test_positive_replay_through_router_returns_recorded_content() -> None:
    """End-to-end: a replay request routed through LLMRouter returns
    the journaled assistant content. No live provider invocation."""
    ledger = await _seed_ledger_with_utterance("hi there")
    router = _router_with_replay(ledger)
    req = LLMRequest(
        user_content="ignored-on-replay",
        replay_mode=True,
        replay_context={
            "session_id": "sess-live-run",
            "actor_id": "npc-alice",
            "activation_id": "act-recorded",
        },
    )
    resp = await router.route(req, engine_name="agency")
    assert resp.provider == "replay"
    assert resp.content == "hi there"
    assert resp.usage.completion_tokens == 4
    assert resp.usage.cost_usd == 0.0


async def test_negative_replay_for_wrong_activation_id_surfaces_mismatch() -> None:
    """A caller asking for a different activation than what's in the
    journal must surface ``ReplayJournalMismatch`` (wrapped by the
    router as a raised exception, not as a silent empty response).
    Locks the miss-signal for cache-aware product layers."""
    import pytest

    from volnix.core.errors import ReplayJournalMismatch

    ledger = await _seed_ledger_with_utterance("hi there")
    router = _router_with_replay(ledger)
    req = LLMRequest(
        replay_mode=True,
        replay_context={
            "session_id": "sess-live-run",
            "actor_id": "npc-alice",
            "activation_id": "act-never-recorded",
        },
    )
    with pytest.raises(ReplayJournalMismatch):
        await router.route(req, engine_name="agency")
