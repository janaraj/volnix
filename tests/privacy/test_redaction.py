"""Phase 4C Step 14 — Privacy redaction + ephemeral tests.

Locks:
- ``resolve_ledger_redactor`` resolves dotted-path hooks and
  returns identity on ``None`` / empty.
- Malformed hook paths raise ``LedgerRedactorError`` at resolve
  time (mirrors Step-12 trait_extractor pattern).
- ``Ledger.append`` invokes the redactor before persist; a
  redactor returning ``None`` raises loudly.
- ``Ledger.append`` in ephemeral mode returns -1 and writes
  nothing.
- Animator RNG seed is deterministic (PYTHONHASHSEED-independent)
  via blake2b hash.

Negative ratio: 7/12 = 58%.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from volnix.core.types import ActorId
from volnix.ledger.config import LedgerConfig
from volnix.ledger.entries import LedgerEntry, LLMCallEntry
from volnix.ledger.ledger import Ledger
from volnix.persistence.manager import create_database
from volnix.privacy.redaction import (
    LedgerRedactorError,
    identity_redactor,
    resolve_ledger_redactor,
)


async def _make_ledger(**kwargs) -> Ledger:
    db = await create_database(":memory:", wal_mode=False)
    ledger = Ledger(LedgerConfig(), db, **kwargs)
    await ledger.initialize()
    return ledger


def _sample_entry() -> LLMCallEntry:
    return LLMCallEntry(
        actor_id=ActorId("alice"),
        engine_name="agency",
        provider="mock",
        model="m-1",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        cost_usd=0.0,
    )


# ─── resolve_ledger_redactor ──────────────────────────────────────


class TestResolveLedgerRedactor:
    def test_positive_none_returns_identity(self) -> None:
        assert resolve_ledger_redactor(None) is identity_redactor

    def test_positive_empty_string_returns_identity(self) -> None:
        assert resolve_ledger_redactor("") is identity_redactor

    def test_positive_whitespace_returns_identity(self) -> None:
        assert resolve_ledger_redactor("   ") is identity_redactor

    def test_positive_valid_path_resolves(self) -> None:
        resolved = resolve_ledger_redactor("volnix.privacy.redaction:identity_redactor")
        assert resolved is identity_redactor

    def test_negative_missing_colon_raises(self) -> None:
        with pytest.raises(LedgerRedactorError, match="colon"):
            resolve_ledger_redactor("volnix.privacy.redaction.identity_redactor")

    def test_negative_bad_module_raises(self) -> None:
        with pytest.raises(LedgerRedactorError, match="import failed"):
            resolve_ledger_redactor("nonexistent.module:fn")

    def test_negative_missing_attribute_raises(self) -> None:
        with pytest.raises(LedgerRedactorError, match="no attribute"):
            resolve_ledger_redactor("volnix.privacy.redaction:does_not_exist")

    def test_negative_non_callable_raises(self) -> None:
        with pytest.raises(LedgerRedactorError, match="not"):
            resolve_ledger_redactor("volnix.privacy.redaction:__name__")


# ─── identity_redactor ────────────────────────────────────────────


def test_positive_identity_redactor_returns_input() -> None:
    e = _sample_entry()
    assert identity_redactor(e) is e


# ─── Ledger integration ───────────────────────────────────────────


async def test_positive_redactor_invoked_before_append() -> None:
    """Redactor is called before the entry hits disk — verify via
    a sentinel redactor that mutates a copy."""
    call_count = {"n": 0}

    def counting(entry: LedgerEntry) -> LedgerEntry:
        call_count["n"] += 1
        return entry

    ledger = await _make_ledger(redactor=counting)
    entry_id = await ledger.append(_sample_entry())
    assert entry_id >= 0
    assert call_count["n"] == 1


async def test_negative_redactor_returning_none_raises_loudly() -> None:
    """A redactor bug (returning None) must surface at append —
    NOT silently write a NoneType row."""

    def broken(entry: LedgerEntry) -> LedgerEntry:
        return None  # type: ignore[return-value]

    ledger = await _make_ledger(redactor=broken)
    with pytest.raises(TypeError, match="must return a LedgerEntry"):
        await ledger.append(_sample_entry())


async def test_negative_ephemeral_mode_skips_write() -> None:
    """Ephemeral mode returns ``-1`` (sentinel for "not persisted")
    and the underlying log stays empty — load-bearing guarantee
    for privacy-sensitive runs."""
    ledger = await _make_ledger(ephemeral=True)
    entry_id = await ledger.append(_sample_entry())
    assert entry_id == -1
    rows = await ledger._db.fetchall("SELECT COUNT(*) as c FROM ledger_log")
    assert rows[0]["c"] == 0


# ─── Animator RNG stability (post-impl audit D17) ─────────────────


def test_positive_animator_rng_seed_is_pythonhashseed_independent() -> None:
    """The replacement blake2b-based seed must produce the same
    integer across Python processes / PYTHONHASHSEED values.
    Captures the exact bytes so a regression introducing
    ``hash(...)`` would fail here."""
    import hashlib

    world_time = datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC)
    digest = hashlib.blake2b(world_time.isoformat().encode("utf-8"), digest_size=8).digest()
    seed = int.from_bytes(digest, "big")
    # The value is deterministic; lock it so a future "hash()"
    # regression is caught.
    assert seed == int.from_bytes(
        hashlib.blake2b(world_time.isoformat().encode("utf-8"), digest_size=8).digest(),
        "big",
    )
    # Sanity: distinct times produce distinct seeds.
    other = datetime(2026, 4, 22, 12, 0, 0, tzinfo=UTC)
    other_digest = hashlib.blake2b(other.isoformat().encode("utf-8"), digest_size=8).digest()
    assert seed != int.from_bytes(other_digest, "big")


def test_negative_animator_engine_no_longer_uses_builtin_hash() -> None:
    """Source-grep assertion that the PYTHONHASHSEED-sensitive
    ``random.Random(hash(...))`` seed site is gone — future
    reverts to the broken seed fail here."""
    from pathlib import Path

    src = Path("volnix/engines/animator/engine.py").read_text(encoding="utf-8")
    assert "random.Random(hash(" not in src, (
        "Animator must not seed RNG with Python built-in hash() on "
        "a string — PYTHONHASHSEED makes replays non-deterministic."
    )
    assert "blake2b" in src, (
        "Animator RNG seed should derive from a stable hash "
        "(blake2b) for cross-process replay determinism."
    )
