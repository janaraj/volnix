"""Phase 4C Step 7 — UsageTracker.record_utterance tests.

Locks the ledger-append contract: ``record_utterance`` writes one
``LLMUtteranceEntry`` per call with a ``sha256:<hex>`` content
hash; returns a no-op when no ledger is injected. The caller is
responsible for the ``utterance_journal_enabled`` gate.

Negative ratio: 3/5 = 60%.
"""

from __future__ import annotations

from typing import Any

from volnix.core.types import ActivationId, ActorId, SessionId
from volnix.llm.tracker import UsageTracker


class _RecordingLedger:
    def __init__(self) -> None:
        self.entries: list[Any] = []

    async def append(self, entry: Any) -> int:
        self.entries.append(entry)
        return len(self.entries)


async def test_negative_record_utterance_without_ledger_is_noop() -> None:
    tracker = UsageTracker(ledger=None)
    await tracker.record_utterance(
        actor_id=ActorId("a"),
        activation_id=ActivationId("aid-1234abcd"),
        session_id=SessionId("s"),
        role="user",
        content="hello",
    )
    # No crash, no side effect.


async def test_negative_record_utterance_rejects_unknown_role() -> None:
    """``role`` is a Pydantic ``Literal`` on ``LLMUtteranceEntry`` —
    an unknown value fails at entry construction, bubbling out of
    ``record_utterance``. Locks the rejection path."""
    import pytest
    from pydantic import ValidationError

    tracker = UsageTracker(ledger=_RecordingLedger())
    with pytest.raises(ValidationError):
        await tracker.record_utterance(
            actor_id=ActorId("a"),
            activation_id=ActivationId("aid-xxx"),
            session_id=None,
            role="narrator",  # not in the Literal union
            content="",
        )


async def test_negative_record_utterance_empty_content_still_hashes() -> None:
    """Empty content is valid — the ``content_hash`` still
    produces a well-formed ``sha256:<hex>`` string (the hash of
    the empty string is a fixed sha256 digest). Locks that we
    don't accidentally pass empty-string content_hash to the
    entry validator, which would reject."""
    ledger = _RecordingLedger()
    tracker = UsageTracker(ledger=ledger)
    await tracker.record_utterance(
        actor_id=ActorId("a"),
        activation_id=ActivationId("aid-xxx"),
        session_id=None,
        role="system",
        content="",
    )
    assert len(ledger.entries) == 1
    assert ledger.entries[0].content_hash.startswith("sha256:")


async def test_positive_record_utterance_appends_single_entry() -> None:
    ledger = _RecordingLedger()
    tracker = UsageTracker(ledger=ledger)
    await tracker.record_utterance(
        actor_id=ActorId("a"),
        activation_id=ActivationId("aid-1234abcd"),
        session_id=SessionId("s"),
        role="user",
        content="hi",
        tokens=5,
        tick=3,
        sequence=2,
    )
    assert len(ledger.entries) == 1
    e = ledger.entries[0]
    assert e.role == "user"
    assert e.tokens == 5
    assert e.tick == 3
    assert e.sequence == 2
    assert e.session_id == SessionId("s")


async def test_positive_content_hash_matches_sha256_of_content() -> None:
    """Hash determinism: same content → same hash. Locks the
    sha256 choice for Step-8 replay-journal dedup."""
    import hashlib

    ledger = _RecordingLedger()
    tracker = UsageTracker(ledger=ledger)
    content = "replay-me"
    expected = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
    await tracker.record_utterance(
        actor_id=ActorId("a"),
        activation_id=ActivationId("aid-xxx"),
        session_id=None,
        role="assistant",
        content=content,
    )
    assert ledger.entries[0].content_hash == expected
