"""Phase 4C Step 8 — ReplayLLMProvider + LLMRouter interception.

Locks the contract that a product replaying a prior session gets
bit-identical ``LLMResponse.content`` back from the journal, with
zero live LLM invocations. Separately: the router's replay-mode
interception MUST raise ``ReplayProviderNotFound`` when no replay
provider is registered — a silent fallthrough to a live provider
would leak cost + tokens during an intended replay.

Negative ratio: 4/6 = 66%.
"""

from __future__ import annotations

from typing import Any

import pytest

from volnix.core.errors import ReplayJournalMismatch, ReplayProviderNotFound
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


async def _make_ledger() -> Ledger:
    db = await create_database(":memory:", wal_mode=False)
    ledger = Ledger(LedgerConfig(), db)
    await ledger.initialize()
    return ledger


def _utter(
    *,
    session_id: str,
    actor_id: str,
    activation_id: str,
    role: str,
    content: str,
    tokens: int = 0,
    sequence: int = 0,
) -> LLMUtteranceEntry:
    return LLMUtteranceEntry(
        actor_id=ActorId(actor_id),
        activation_id=ActivationId(activation_id),
        session_id=SessionId(session_id),
        role=role,  # type: ignore[arg-type]
        content=content,
        content_hash=f"sha256:{'0' * 64}",
        tokens=tokens,
        tick=0,
        sequence=sequence,
    )


def _replay_request(*, session_id: str, actor_id: str, activation_id: str) -> LLMRequest:
    return LLMRequest(
        user_content="ignored",
        replay_mode=True,
        replay_context={
            "session_id": session_id,
            "actor_id": actor_id,
            "activation_id": activation_id,
        },
    )


# ─── Provider-level ──────────────────────────────────────────────


async def test_negative_replay_context_missing_raises_mismatch() -> None:
    """A replay request with no lookup key is malformed; the
    provider must refuse rather than silently returning empty
    content."""
    ledger = await _make_ledger()
    provider = ReplayLLMProvider(ledger)
    with pytest.raises(ReplayJournalMismatch):
        await provider.generate(LLMRequest(replay_mode=True, replay_context=None))


async def test_negative_no_matching_journal_entries_raises_mismatch() -> None:
    """When the lookup key has no rows in the ledger, the provider
    raises — a downstream product can treat this as a replay-cache
    miss and decide whether to fall back to a live provider."""
    ledger = await _make_ledger()
    provider = ReplayLLMProvider(ledger)
    req = _replay_request(session_id="s-1", actor_id="a-1", activation_id="act-missing")
    with pytest.raises(ReplayJournalMismatch):
        await provider.generate(req)


async def test_negative_no_assistant_role_in_journal_raises_mismatch() -> None:
    """System/user rows alone are insufficient — the replay
    response content comes from the assistant row. Absence is a
    data-integrity error, not a silent empty response."""
    ledger = await _make_ledger()
    await ledger.append(
        _utter(
            session_id="s-1",
            actor_id="a-1",
            activation_id="act-only-system",
            role="system",
            content="system prompt",
        )
    )
    provider = ReplayLLMProvider(ledger)
    req = _replay_request(session_id="s-1", actor_id="a-1", activation_id="act-only-system")
    with pytest.raises(ReplayJournalMismatch):
        await provider.generate(req)


async def test_positive_replay_reconstructs_assistant_content() -> None:
    """Happy path: pre-populated journal → replay returns the
    recorded assistant content, zero live calls."""
    ledger = await _make_ledger()
    # Populate a 3-row activation.
    await ledger.append(
        _utter(
            session_id="s-1",
            actor_id="a-1",
            activation_id="act-1",
            role="system",
            content="sys",
            sequence=0,
        )
    )
    await ledger.append(
        _utter(
            session_id="s-1",
            actor_id="a-1",
            activation_id="act-1",
            role="user",
            content="usr",
            sequence=1,
        )
    )
    await ledger.append(
        _utter(
            session_id="s-1",
            actor_id="a-1",
            activation_id="act-1",
            role="assistant",
            content="REPLAYED",
            tokens=7,
            sequence=2,
        )
    )
    provider = ReplayLLMProvider(ledger)
    resp = await provider.generate(
        _replay_request(session_id="s-1", actor_id="a-1", activation_id="act-1")
    )
    assert resp.content == "REPLAYED"
    assert resp.provider == "replay"
    assert resp.usage.completion_tokens == 7
    assert resp.usage.cost_usd == 0.0


# ─── Router interception ──────────────────────────────────────────


def _router_with(registry: ProviderRegistry) -> LLMRouter:
    # Minimal LLMConfig — defaults are fine for the interception
    # path because replay_mode short-circuits before routing resolution.
    cfg = LLMConfig(
        providers={
            "mock": LLMProviderEntry(type="mock"),
        },
        routing={},
        defaults=LLMProviderEntry(type="mock"),
    )
    return LLMRouter(registry=registry, config=cfg)


async def test_negative_router_replay_mode_with_conflicting_override_raises() -> None:
    """Post-impl audit H3: a caller that sets BOTH
    ``replay_mode=True`` AND ``provider_override="anthropic"`` has
    a bug — the router must refuse rather than silently dropping
    the override. Locks the loud-fail path."""
    ledger = await _make_ledger()
    registry = ProviderRegistry()
    registry.register("replay", ReplayLLMProvider(ledger))
    router = _router_with(registry)
    req = LLMRequest(
        replay_mode=True,
        replay_context={"session_id": "s", "actor_id": "a", "activation_id": "x"},
        provider_override="anthropic",
    )
    with pytest.raises(ReplayProviderNotFound):
        await router.route(req, engine_name="agency")


async def test_negative_router_without_replay_provider_raises_not_found() -> None:
    """Router short-circuits replay_mode — it MUST raise when the
    replay provider was never registered, not fall through to a
    live provider. Otherwise a replay run would burn tokens."""
    registry = ProviderRegistry()
    router = _router_with(registry)
    req = _replay_request(session_id="s", actor_id="a", activation_id="act")
    with pytest.raises(ReplayProviderNotFound):
        await router.route(req, engine_name="agency")


async def test_positive_router_delegates_to_replay_when_registered() -> None:
    """Happy path: with the replay provider registered via the
    public ``register_provider`` API, the router skips normal
    routing entirely and returns the reconstructed response.
    Asserts zero interaction with any other provider."""
    ledger = await _make_ledger()
    await ledger.append(
        _utter(
            session_id="s-1",
            actor_id="a-1",
            activation_id="act-1",
            role="assistant",
            content="FROM-ROUTER",
        )
    )
    registry = ProviderRegistry()

    # A recording mock to detect any fallthrough.
    class _ShouldNotFire:
        provider_name = "mock"

        async def generate(self, request: Any) -> Any:  # noqa: D401
            raise AssertionError("router fell through to live provider during replay_mode=True")

    registry.register("mock", _ShouldNotFire())  # type: ignore[arg-type]

    router = _router_with(registry)
    # Post-impl audit H4/L2: use the public API, not the private
    # ``_registry`` attribute.
    router.register_provider("replay", ReplayLLMProvider(ledger))
    req = _replay_request(session_id="s-1", actor_id="a-1", activation_id="act-1")
    resp = await router.route(req, engine_name="agency")
    assert resp.content == "FROM-ROUTER"
    assert resp.provider == "replay"
