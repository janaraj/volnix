"""Phase 4C Step 4 — platform Session types tests.

Locks in the value-object shape that Step 5's ``SessionManager``
builds on. Because Step 4 ships types only (no wiring), the tests
target the contract a library consumer pins against: immutability,
field validation, enum strictness, round-trip via
``deserialize_entry``.

Negative-first per test discipline.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from volnix.core.session import (
    SeedStrategy,
    Session,
    SessionCheckpointKind,
    SessionId,
    SessionStatus,
    SessionType,
)
from volnix.core.types import ActivationId, ActorId, WorldId
from volnix.core.types import SessionId as SessionIdFromTypes
from volnix.ledger.entries import (
    ENTRY_REGISTRY,
    LLMUtteranceEntry,
    SessionCheckpointEntry,
    SessionEndedEntry,
    SessionStartedEntry,
    deserialize_entry,
)


def _sample_session(**overrides):
    defaults = {
        "session_id": SessionId("sess-abc123"),
        "world_id": WorldId("world-xyz"),
        "session_type": SessionType.BOUNDED,
        "seed": 42,
    }
    defaults.update(overrides)
    return Session(**defaults)


def _sample_utterance(**overrides):
    defaults = {
        "actor_id": ActorId("actor-1"),
        "activation_id": ActivationId("act-abc"),
        "role": "user",
        "content": "hello",
        "content_hash": "sha256:deadbeef",
    }
    defaults.update(overrides)
    return LLMUtteranceEntry(**defaults)


# ─── Session value object ──────────────────────────────────────────


class TestSessionValueObject:
    def test_negative_session_frozen_rejects_mutation(self) -> None:
        """Asserts ``Session`` is a frozen Pydantic model — attribute
        assignment raises ``ValidationError``. Prevents a caller from
        mutating session state in place and letting stale cached
        copies drift."""
        session = _sample_session()
        with pytest.raises(ValidationError):
            session.status = SessionStatus.COMPLETED  # type: ignore[misc]

    def test_negative_session_requires_world_id(self) -> None:
        """A Session without a world is meaningless (PMF Plan §10:
        cross-world sessions out of scope). Validator must reject."""
        with pytest.raises(ValidationError):
            Session(  # type: ignore[call-arg]
                session_id=SessionId("sess-1"),
                session_type=SessionType.BOUNDED,
                seed=1,
            )

    def test_negative_session_requires_seed(self) -> None:
        """A Session must always carry a seed — D4c: ``INHERIT``
        copies the world seed, ``FRESH`` derives, ``EXPLICIT`` records
        the caller's value. Making ``seed`` optional would reintroduce
        the determinism hole the plan explicitly closes."""
        with pytest.raises(ValidationError):
            Session(  # type: ignore[call-arg]
                session_id=SessionId("sess-1"),
                world_id=WorldId("w-1"),
                session_type=SessionType.BOUNDED,
            )

    def test_negative_default_timestamps_share_one_now_call(self) -> None:
        """Review H3 / D4i: on default construction ``created_at``
        and ``updated_at`` must be EQUAL (stamped from one shared
        ``now()`` call), not microsecond-drifted from two independent
        ``default_factory`` invocations. Catches a regression that
        would make every freshly-created session look pre-modified."""
        session = _sample_session()
        assert session.created_at == session.updated_at

    def test_positive_session_round_trip_through_json(self) -> None:
        """Serialise + reconstruct yields an equal instance. Locks the
        wire format used by ``SessionManager``'s SQLite store in Step
        5 — any change here is a schema bump, not a silent rewrite."""
        session = _sample_session(metadata={"label": "rehearse-demo"})
        restored = Session.model_validate_json(session.model_dump_json())
        assert restored == session
        assert restored is not session

    def test_positive_default_status_is_active(self) -> None:
        assert _sample_session().status == SessionStatus.ACTIVE

    def test_positive_default_seed_strategy_is_inherit(self) -> None:
        assert _sample_session().seed_strategy == SeedStrategy.INHERIT

    def test_positive_session_id_newtype_re_export_matches_types_module(
        self,
    ) -> None:
        """``SessionId`` re-exported from ``volnix.core.session`` is
        the SAME object as the one in ``volnix.core.types`` — prevents
        a consumer building two diverging NewType aliases that
        mypy/IDE treat as distinct."""
        assert SessionId is SessionIdFromTypes

    def test_positive_explicit_timestamps_preserved(self) -> None:
        """The timestamp model-validator must NOT clobber values the
        caller supplied explicitly — only fills missing ones."""
        fixed = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        session = _sample_session(created_at=fixed, updated_at=fixed)
        assert session.created_at == fixed
        assert session.updated_at == fixed

    def test_negative_source_metadata_mutation_does_not_leak(self) -> None:
        """Cleanup sweep: Session.metadata is deep-copied at
        construction so mutation of the caller's source dict
        cannot alter the frozen session."""
        source: dict = {"nested": {"k": "orig"}}
        session = _sample_session(metadata=source)
        source["nested"]["k"] = "HIJACKED"
        source["added"] = "later"
        assert session.metadata["nested"]["k"] == "orig"
        assert "added" not in session.metadata


# ─── Enum strictness ──────────────────────────────────────────────


class TestEnumStrictness:
    def test_negative_session_status_rejects_unknown_value(self) -> None:
        with pytest.raises(ValidationError):
            _sample_session(status="half-done")

    def test_negative_session_type_rejects_unknown_value(self) -> None:
        with pytest.raises(ValidationError):
            _sample_session(session_type="weekly")

    def test_negative_seed_strategy_rejects_unknown_value(self) -> None:
        with pytest.raises(ValidationError):
            _sample_session(seed_strategy="timing-attack")

    def test_positive_status_strenum_value_accepted(self) -> None:
        """Both the enum and its string value must validate — the
        enum is ``StrEnum`` so both land as the same underlying
        string. Guards against a future move to plain ``enum.Enum``
        that would break string-form deserialisation."""
        s1 = _sample_session(status=SessionStatus.PAUSED)
        s2 = _sample_session(status="paused")
        assert s1.status == s2.status == SessionStatus.PAUSED


# ─── Session events ───────────────────────────────────────────────


class TestSessionEvents:
    def test_positive_session_started_event_roundtrips(self) -> None:
        from volnix.core.events import SessionStartedEvent
        from volnix.core.types import Timestamp

        evt = SessionStartedEvent(
            timestamp=Timestamp(
                world_time=datetime.now(UTC),
                wall_time=datetime.now(UTC),
                tick=0,
            ),
            session_id=SessionId("s-1"),
            world_id=WorldId("w-1"),
            session_type="bounded",
            seed_strategy="inherit",
        )
        restored = SessionStartedEvent.model_validate_json(evt.model_dump_json())
        assert restored == evt
        assert restored.event_type == "session.started"

    def test_positive_session_ended_event_carries_status_and_reason(self) -> None:
        from volnix.core.events import SessionEndedEvent
        from volnix.core.types import Timestamp

        evt = SessionEndedEvent(
            timestamp=Timestamp(
                world_time=datetime.now(UTC),
                wall_time=datetime.now(UTC),
                tick=99,
            ),
            session_id=SessionId("s-1"),
            status="completed",
            end_tick=99,
            reason="goal_reached",
        )
        assert evt.event_type == "session.ended"
        assert evt.end_tick == 99
        assert evt.reason == "goal_reached"

    def test_positive_session_ended_event_end_tick_optional_for_abandoned(
        self,
    ) -> None:
        """Review M8 / D4k: a session abandoned from ``PAUSED``
        across a process restart may not have a meaningful tick.
        ``end_tick: int | None = None`` must accept the missing
        case without requiring the caller to invent a value."""
        from volnix.core.events import SessionEndedEvent
        from volnix.core.types import Timestamp

        evt = SessionEndedEvent(
            timestamp=Timestamp(
                world_time=datetime.now(UTC),
                wall_time=datetime.now(UTC),
                tick=0,
            ),
            session_id=SessionId("s-1"),
            status="abandoned",
            reason="process_restart_during_pause",
        )
        assert evt.end_tick is None

    def test_positive_session_resumed_event_carries_world_and_tick(self) -> None:
        """Review M5 / D4j: ``SessionResumedEvent`` carries
        ``world_id`` for bus-consumer symmetry with
        ``SessionStartedEvent`` — a subscriber filtering on
        ``world_id`` shouldn't need a state lookup for resumes."""
        from volnix.core.events import SessionResumedEvent
        from volnix.core.types import Timestamp

        evt = SessionResumedEvent(
            timestamp=Timestamp(
                world_time=datetime.now(UTC),
                wall_time=datetime.now(UTC),
                tick=17,
            ),
            session_id=SessionId("s-1"),
            world_id=WorldId("w-1"),
            resumed_at_tick=17,
        )
        assert evt.event_type == "session.resumed"
        assert evt.world_id == WorldId("w-1")
        assert evt.resumed_at_tick == 17

    def test_negative_session_resumed_event_requires_world_id(self) -> None:
        """Locks the D4j symmetry contract: missing ``world_id``
        is a construction error, NOT a silent default."""
        from volnix.core.events import SessionResumedEvent
        from volnix.core.types import Timestamp

        with pytest.raises(ValidationError):
            SessionResumedEvent(  # type: ignore[call-arg]
                timestamp=Timestamp(
                    world_time=datetime.now(UTC),
                    wall_time=datetime.now(UTC),
                    tick=0,
                ),
                session_id=SessionId("s-1"),
                resumed_at_tick=0,
            )


# ─── Ledger entries registered + round-trip through deserialize ──


class TestSessionLedgerEntries:
    def test_negative_entry_registry_size_locked_post_step_4(self) -> None:
        """Review M1: the registry MUST have exactly four more
        entries than the pre-Step-4 baseline of 29 (total 33). Bare
        key-equality does not catch a drift where a fifth entry is
        accidentally added in the same commit — this size assertion
        does."""
        assert len(ENTRY_REGISTRY) == 33

    def test_positive_all_four_new_entry_types_registered(self) -> None:
        assert ENTRY_REGISTRY["session.started"] is SessionStartedEntry
        assert ENTRY_REGISTRY["session.ended"] is SessionEndedEntry
        assert ENTRY_REGISTRY["session.checkpoint"] is SessionCheckpointEntry
        assert ENTRY_REGISTRY["llm.utterance"] is LLMUtteranceEntry

    def test_positive_session_started_entry_roundtrip(self) -> None:
        entry = SessionStartedEntry(
            session_id=SessionId("s-1"),
            world_id=WorldId("w-1"),
            session_type="bounded",
            seed_strategy="inherit",
            seed=42,
        )
        row = {"entry_type": "session.started", "payload": entry.model_dump_json()}
        restored = deserialize_entry(row)
        assert isinstance(restored, SessionStartedEntry)
        assert restored.seed == 42

    def test_positive_session_ended_entry_end_tick_optional(self) -> None:
        """Review M8 / D4k: parity with ``SessionEndedEvent`` —
        the ledger entry also accepts ``end_tick=None``."""
        entry = SessionEndedEntry(
            session_id=SessionId("s-1"),
            status="abandoned",
            reason="process_restart_during_pause",
        )
        assert entry.end_tick is None

    def test_negative_session_checkpoint_kind_rejects_unknown_value(self) -> None:
        """``kind`` is the ``SessionCheckpointKind`` ``StrEnum``
        (review H2): Pydantic rejects any string outside the three
        enum members. Locks the D4 audit-fold D-Find-6 decision:
        three kinds, one class."""
        with pytest.raises(ValidationError):
            SessionCheckpointEntry(
                session_id=SessionId("s-1"),
                kind="half-paused",
                tick=5,
            )

    def test_positive_session_checkpoint_all_three_kinds_accepted(self) -> None:
        for kind in SessionCheckpointKind:
            entry = SessionCheckpointEntry(
                session_id=SessionId("s-1"),
                kind=kind,
                tick=5,
            )
            assert entry.kind == kind


# ─── LLMUtteranceEntry skeleton (Step 4 ships schema; Step 7 writes) ─


class TestLLMUtteranceEntry:
    def test_positive_llm_utterance_entry_roundtrip(self) -> None:
        """The full-skeleton schema (D4e) must round-trip cleanly —
        Step 7 will wire the write sites but cannot wire against a
        type that doesn't already serialise correctly."""
        entry = _sample_utterance(
            session_id=SessionId("s-1"),
            content="hello",
            content_hash="sha256:deadbeef",
            tokens=2,
        )
        row = {"entry_type": "llm.utterance", "payload": entry.model_dump_json()}
        restored = deserialize_entry(row)
        assert isinstance(restored, LLMUtteranceEntry)
        assert restored.content == "hello"
        assert restored.role == "user"

    def test_positive_llm_utterance_session_id_defaults_to_none(self) -> None:
        """``session_id=None`` is the default — utterances can be
        emitted from non-session contexts during the pre-Step-5
        migration window. Replaces the pre-audit C1 fake-negative."""
        entry = _sample_utterance()
        assert entry.session_id is None

    def test_negative_llm_utterance_role_rejects_unknown_value(self) -> None:
        with pytest.raises(ValidationError):
            _sample_utterance(role="narrator")

    def test_negative_llm_utterance_content_hash_empty_rejected(self) -> None:
        """Review H1: empty ``content_hash`` is a replay-journal
        foot-gun (dedup logic would collapse all empty-hash rows).
        Must raise at construction."""
        with pytest.raises(ValidationError):
            _sample_utterance(content_hash="")

    def test_negative_llm_utterance_content_hash_missing_prefix_rejected(
        self,
    ) -> None:
        """Review H1: hash without the ``<alg>:`` prefix can't be
        rotated to a different algorithm later without a schema
        bump. Validator enforces the format."""
        with pytest.raises(ValidationError):
            _sample_utterance(content_hash="deadbeefdeadbeef")

    def test_negative_llm_utterance_content_hash_non_hex_payload_rejected(
        self,
    ) -> None:
        """Catches subtle malformed hashes (e.g., base64-encoded
        digest where hex was expected) — the regex fires."""
        with pytest.raises(ValidationError):
            _sample_utterance(content_hash="sha256:NOT-hex-ZZZZ")

    def test_negative_llm_utterance_activation_id_is_activation_id_newtype(
        self,
    ) -> None:
        """Review C2 + post-impl H1: ``activation_id`` field MUST be
        typed ``ActivationId`` (NewType over str). A revert to bare
        ``str`` has to fail this test — so we assert strict identity
        with ``ActivationId``, NOT ``ActivationId or str``. The
        previous permissive assertion was a fake-positive that
        tolerated the violation it claimed to lock down."""
        field = LLMUtteranceEntry.model_fields["activation_id"]
        assert field.annotation is ActivationId, (
            f"LLMUtteranceEntry.activation_id must be ActivationId, got {field.annotation}"
        )
