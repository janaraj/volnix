"""Phase 4C Step 3 — ledger forward-compat tests.

Locks in two promises a library consumer can pin against:

1. ``schema_version`` is present on every ledger entry (default ``1``).
   A consumer using the ledger as a time-series audit record can
   discriminate writer-era by this field without heuristics on the
   discriminator name.
2. ``UnknownLedgerEntry`` wraps rows whose ``entry_type`` is not in
   ``ENTRY_REGISTRY`` — older reader meets newer writer. The full
   payload is preserved in ``raw_payload``; no data loss, no silent
   degradation to bare ``LedgerEntry``.

Negative-first per test discipline.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from volnix.ledger.entries import (
    ENTRY_REGISTRY,
    LedgerEntry,
    PipelineStepEntry,
    UnknownLedgerEntry,
    deserialize_entry,
)

# ─── schema_version on every entry ─────────────────────────────────


class TestSchemaVersionBaseline:
    def test_negative_schema_version_zero_rejected(self) -> None:
        """``ge=1`` must reject zero — prevents a silent "unversioned"
        entry shape from sneaking through (a consumer would read
        ``0`` as "pre-schema-version" which we never want to mean
        anything)."""
        with pytest.raises(ValidationError):
            LedgerEntry(entry_type="test", schema_version=0)

    def test_negative_schema_version_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LedgerEntry(entry_type="test", schema_version=-1)

    def test_positive_schema_version_defaults_to_1_on_base(self) -> None:
        entry = LedgerEntry(entry_type="test")
        assert entry.schema_version == 1

    def test_positive_schema_version_inherited_by_every_registered_subclass(
        self,
    ) -> None:
        """Every concrete entry class in ENTRY_REGISTRY must emit
        ``schema_version=1`` at minimum. Locks the baseline: a future
        writer bumping a specific subclass to ``2`` is a deliberate,
        reviewable change — not an accident."""
        for discriminator, cls in ENTRY_REGISTRY.items():
            # Some classes need extra required fields to instantiate;
            # inspect the model field default instead of constructing.
            default = cls.model_fields["schema_version"].default
            assert default == 1, (
                f"{discriminator!r} ({cls.__name__}) has "
                f"schema_version default {default!r}, expected 1"
            )


# ─── UnknownLedgerEntry wrapper semantics ─────────────────────────


class TestUnknownLedgerEntryWrapper:
    def test_negative_unknown_entry_type_wraps_in_unknown_ledger_entry(self) -> None:
        """A row whose ``entry_type`` is not in ``ENTRY_REGISTRY`` must
        return an ``UnknownLedgerEntry`` instance — NOT a bare
        ``LedgerEntry`` (which was the pre-4C silent-degradation
        behaviour)."""
        # Probe: a known type (session.started) at schema_version=2
        # — beyond the reader's ``LATEST_SCHEMA_VERSION=1``. Step-3's
        # contract wraps this case the same way as a truly-unknown
        # entry_type (see ``TestDeserializeEntryEdgeCases``). A
        # previous iteration of this test used an unregistered
        # ``session.started`` key; Step 4 registered the key, and
        # the test now exercises the schema-version gate branch.
        payload = {
            "entry_type": "session.started",
            "schema_version": 2,
            "session_id": "sess-123",
            "world_id": "world-abc",
        }
        row = {"entry_type": "session.started", "payload": json.dumps(payload)}
        result = deserialize_entry(row)
        assert isinstance(result, UnknownLedgerEntry)
        assert type(result) is not LedgerEntry  # noqa: E721 — exact-type check

    def test_negative_unknown_type_preserves_original_discriminator(self) -> None:
        payload = {
            "entry_type": "v3.exotic_entry",
            "some_future_field": 42,
        }
        row = {"entry_type": "v3.exotic_entry", "payload": json.dumps(payload)}
        result = deserialize_entry(row)
        assert isinstance(result, UnknownLedgerEntry)
        assert result.raw_entry_type == "v3.exotic_entry"
        # The wrapper's own discriminator is the fixed sentinel.
        assert result.entry_type == "unknown"

    def test_negative_unknown_type_preserves_full_payload(self) -> None:
        payload = {
            "entry_type": "future.type",
            "custom_field_a": "alpha",
            "custom_field_b": [1, 2, 3],
            "custom_nested": {"x": True, "y": None},
        }
        row = {"entry_type": "future.type", "payload": json.dumps(payload)}
        result = deserialize_entry(row)
        assert isinstance(result, UnknownLedgerEntry)
        assert result.raw_payload == payload

    def test_negative_unknown_type_preserves_entry_id_and_timestamp(self) -> None:
        """Base-class fields (entry_id, schema_version, timestamp,
        metadata) must be lifted onto the wrapper — otherwise a
        caller iterating ``row.timestamp`` on a mixed stream would
        hit the wrapper's default-now timestamp, corrupting the
        audit timeline."""
        fixed_ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        payload = {
            "entry_type": "future.type",
            "entry_id": 42,
            "schema_version": 3,
            "timestamp": fixed_ts.isoformat(),
            "metadata": {"k": "v"},
            "future_field": "x",
        }
        row = {"entry_type": "future.type", "payload": json.dumps(payload)}
        result = deserialize_entry(row)
        assert result.entry_id == 42
        assert result.schema_version == 3
        assert result.metadata == {"k": "v"}
        # Pydantic parses ISO timestamps; compare to the second.
        assert result.timestamp - fixed_ts < timedelta(seconds=1)

    def test_negative_isinstance_ledger_entry_on_wrapper_still_true(self) -> None:
        """A consumer doing ``if isinstance(e, LedgerEntry):`` must
        still match unknown rows — the wrapper inherits from the base
        so existing ledger-iteration code continues to work."""
        row = {
            "entry_type": "future",
            "payload": json.dumps({"entry_type": "future"}),
        }
        result = deserialize_entry(row)
        assert isinstance(result, LedgerEntry)
        assert isinstance(result, UnknownLedgerEntry)

    # NOTE: the round-trip story moved to
    # ``TestDeserializeEntryEdgeCases.test_negative_wrapper_passthrough_unnests_on_read``
    # — review M1 replaced the pre-fix double-nest behaviour with
    # passthrough unwrap, so a stored-then-read wrapper preserves the
    # ORIGINAL discriminator and payload instead of compounding.


# ─── Known-type paths must still work ─────────────────────────────


class TestKnownTypesUnchanged:
    def test_positive_known_type_still_deserialises_as_itself(self) -> None:
        """The happy path for registered types must be untouched —
        no bare-LedgerEntry downgrade, no UnknownLedgerEntry wrap."""
        entry = PipelineStepEntry(
            step_name="auth",
            request_id="r-1",
            actor_id="a-1",  # type: ignore[arg-type]
            action="read",
            verdict="allow",
        )
        row = {"entry_type": "pipeline_step", "payload": entry.model_dump_json()}
        result = deserialize_entry(row)
        assert isinstance(result, PipelineStepEntry)
        assert not isinstance(result, UnknownLedgerEntry)
        assert result.step_name == "auth"
        assert result.schema_version == 1

    def test_positive_every_registered_class_is_a_ledger_entry_subtype(self) -> None:
        """Structural guard (review L4): the exact membership is
        covered by ``test_entry_registry_all_types`` in
        ``test_entries.py``. This test keeps the Step-3-specific
        invariants: every registered class is a LedgerEntry subclass
        AND is not the forward-compat wrapper."""
        for name, cls in ENTRY_REGISTRY.items():
            assert issubclass(cls, LedgerEntry), f"{name!r} not a LedgerEntry subclass"
            assert cls is not UnknownLedgerEntry, f"{name!r} must not be the forward-compat wrapper"

    def test_negative_unknown_sentinel_is_reserved_not_in_registry(self) -> None:
        """``"unknown"`` is reserved — no concrete entry class may
        register under that discriminator. A collision would create a
        wrapping loop on every read."""
        from volnix.ledger.entries import _UNKNOWN_ENTRY_TYPE_SENTINEL

        assert _UNKNOWN_ENTRY_TYPE_SENTINEL == "unknown"
        assert _UNKNOWN_ENTRY_TYPE_SENTINEL not in ENTRY_REGISTRY


# ─── deserialize_entry error + edge paths (review H1, H2, M1, M3) ──


class TestDeserializeEntryEdgeCases:
    def test_negative_missing_payload_key_raises_value_error(self) -> None:
        """Review H1: a row without ``payload`` must raise a specific
        ``ValueError`` naming the entry_type — not a bare
        ``KeyError`` that crashes an entire ``Ledger.query()`` run."""
        with pytest.raises(ValueError, match="missing 'payload'"):
            deserialize_entry({"entry_type": "pipeline_step"})

    def test_negative_null_payload_raises_value_error(self) -> None:
        """``None`` payload (e.g., NULL column) is equivalent to missing."""
        with pytest.raises(ValueError, match="missing 'payload'"):
            deserialize_entry({"entry_type": "pipeline_step", "payload": None})

    def test_negative_malformed_json_payload_raises_value_error(self) -> None:
        """Review H2: a corrupt JSON blob must raise a diagnostic
        ``ValueError`` carrying the decoder message and entry_type,
        NOT a raw ``json.JSONDecodeError``."""
        with pytest.raises(ValueError, match="malformed JSON"):
            deserialize_entry({"entry_type": "pipeline_step", "payload": "{not valid json"})

    def test_negative_payload_decoding_to_non_dict_raises(self) -> None:
        """A payload that is valid JSON but not an object (e.g., a
        bare string or number) must raise rather than crashing
        inside Pydantic validation."""
        with pytest.raises(ValueError, match="must decode to a dict"):
            deserialize_entry({"entry_type": "pipeline_step", "payload": "[1, 2, 3]"})

    def test_negative_partial_wrapper_does_not_passthrough(self) -> None:
        """Audit-fold L1: a corrupt row with ``entry_type="unknown"``
        and ``raw_entry_type`` but no ``raw_payload`` must NOT invoke
        the passthrough — otherwise a half-wrapper could smuggle an
        arbitrary discriminator past the registry. Falls through to
        the normal wrap path (``raw_entry_type`` becomes the sentinel
        ``"unknown"`` so a consumer can distinguish corruption from
        a legitimately-unknown type)."""
        corrupt_payload = {
            "entry_type": "unknown",
            "raw_entry_type": "pipeline_step",  # no raw_payload accompanying
        }
        row = {"entry_type": "unknown", "payload": json.dumps(corrupt_payload)}
        result = deserialize_entry(row)
        assert isinstance(result, UnknownLedgerEntry)
        # Critical: does NOT recover as PipelineStepEntry — the missing
        # raw_payload means we cannot trust the claimed raw_entry_type.
        assert not isinstance(result, PipelineStepEntry)
        # ``raw_entry_type`` is the sentinel, signalling "this was a
        # wrapper-looking row but we couldn't trust it".
        assert result.raw_entry_type == "unknown"

    def test_negative_wrapper_passthrough_unnests_on_read(self) -> None:
        """Review M1: reading back a stored wrapper returns a wrapper
        with the ORIGINAL ``raw_entry_type`` / ``raw_payload`` — NOT
        a wrapper nested inside a wrapper. Prevents the
        monotonically-growing ``raw_payload`` on repeated
        store-then-read cycles."""
        original_payload = {
            "entry_type": "future.exotic",
            "custom": "payload",
        }
        # First read: unknown type wraps.
        row_in = {
            "entry_type": "future.exotic",
            "payload": json.dumps(original_payload),
        }
        wrapper = deserialize_entry(row_in)
        assert isinstance(wrapper, UnknownLedgerEntry)

        # Simulate the ledger storing then re-reading the wrapper.
        row_stored = {
            "entry_type": wrapper.entry_type,  # "unknown"
            "payload": wrapper.model_dump_json(),
        }
        result = deserialize_entry(row_stored)
        assert isinstance(result, UnknownLedgerEntry)
        # Key assertion: no nesting — raw_payload still matches the
        # original, not the wrapper's own serialised shape.
        assert result.raw_entry_type == "future.exotic"
        assert result.raw_payload == original_payload
        assert "raw_payload" not in result.raw_payload

    def test_positive_wrapper_passthrough_recovers_concrete_class_if_now_known(
        self,
    ) -> None:
        """Review M1 upside: if a reader is upgraded to know a type
        that was previously unknown, reading a stored wrapper of that
        type recovers the concrete class — not a wrapper. This is
        the forward-compat contract in the forward direction: old
        writer, new reader, data survives the upgrade."""
        # Manufacture a wrapper whose raw_entry_type is a KNOWN type.
        pipeline_payload = PipelineStepEntry(
            step_name="auth",
            request_id="r-1",
            actor_id="a-1",  # type: ignore[arg-type]
            action="read",
            verdict="allow",
        ).model_dump(mode="python")
        wrapper = UnknownLedgerEntry(
            raw_entry_type="pipeline_step",
            raw_payload=pipeline_payload,
        )
        row = {
            "entry_type": wrapper.entry_type,
            "payload": wrapper.model_dump_json(),
        }
        result = deserialize_entry(row)
        assert isinstance(result, PipelineStepEntry)
        assert result.step_name == "auth"

    def test_negative_known_type_with_newer_schema_version_wraps(self) -> None:
        """Review M3: a reader encountering ``pipeline_step`` with
        ``schema_version=99`` (beyond ``LATEST_SCHEMA_VERSION``) must
        wrap in ``UnknownLedgerEntry`` rather than silently parsing
        as the current ``PipelineStepEntry`` shape (which would drop
        the newer writer's added fields). Honours the docstring
        promise."""
        future_payload = {
            "entry_type": "pipeline_step",
            "schema_version": 99,
            "step_name": "auth",
            "request_id": "r-1",
            "actor_id": "a-1",
            "action": "read",
            "verdict": "allow",
            "new_v99_field": "hopefully preserved",
        }
        row = {
            "entry_type": "pipeline_step",
            "payload": json.dumps(future_payload),
        }
        result = deserialize_entry(row)
        assert isinstance(result, UnknownLedgerEntry)
        assert result.raw_entry_type == "pipeline_step"
        assert result.raw_payload["new_v99_field"] == "hopefully preserved"
        assert result.schema_version == 99

    def test_positive_known_type_at_latest_schema_version_unchanged(self) -> None:
        """The gate at ``schema_version <= LATEST_SCHEMA_VERSION`` must
        NOT fire for entries at the reader's current version."""
        entry = PipelineStepEntry(
            step_name="auth",
            request_id="r-1",
            actor_id="a-1",  # type: ignore[arg-type]
            action="read",
            verdict="allow",
        )
        row = {
            "entry_type": "pipeline_step",
            "payload": entry.model_dump_json(),
        }
        result = deserialize_entry(row)
        assert isinstance(result, PipelineStepEntry)


# ─── UnknownLedgerEntry direct construction ────────────────────────


class TestUnknownLedgerEntryDirectConstruction:
    def test_negative_missing_raw_entry_type_rejected(self) -> None:
        """``raw_entry_type`` is required — a wrapper without it would
        be indistinguishable from a bare base entry."""
        with pytest.raises(ValidationError):
            UnknownLedgerEntry(raw_payload={})  # type: ignore[call-arg]

    def test_positive_wrapper_is_frozen(self) -> None:
        entry = UnknownLedgerEntry(raw_entry_type="future.x", raw_payload={"a": 1})
        with pytest.raises(ValidationError):
            entry.raw_entry_type = "mutated"  # type: ignore[misc]

    def test_positive_empty_raw_payload_allowed(self) -> None:
        """A minimal wrapper — writer emitted only discriminator + base
        fields — is still constructible; the scan path shouldn't
        require subclass fields in the payload."""
        entry = UnknownLedgerEntry(raw_entry_type="future.empty")
        assert entry.raw_payload == {}
        assert entry.raw_entry_type == "future.empty"


# ─── Cross-step 4 → 3 forward-compat (audit-fold M2) ────────────────


class TestCrossStep4To3Compat:
    """Verifies that Step-4's new ``session.*`` ledger entries
    interact correctly with Step-3's ``UnknownLedgerEntry`` forward-
    compat wrapping. Placed here (not in ``test_session_types.py``)
    because the behaviour under test is the Step-3 contract —
    ``SessionStartedEntry`` is just a convenient probe fixture."""

    def test_negative_session_entry_with_key_removed_wraps_not_crashes(
        self,
    ) -> None:
        """An older reader that hasn't been taught ``session.started``
        must wrap the row in ``UnknownLedgerEntry``. We simulate the
        older reader by popping the key for the test's duration."""
        from volnix.core.session import SessionId
        from volnix.core.types import WorldId
        from volnix.ledger.entries import (
            ENTRY_REGISTRY,
            SessionStartedEntry,
            UnknownLedgerEntry,
            deserialize_entry,
        )

        entry = SessionStartedEntry(
            session_id=SessionId("s-1"),
            world_id=WorldId("w-1"),
            session_type="bounded",
            seed_strategy="inherit",
            seed=42,
        )
        row = {
            "entry_type": "session.started",
            "payload": entry.model_dump_json(),
        }
        original = ENTRY_REGISTRY.pop("session.started")
        try:
            restored = deserialize_entry(row)
            assert isinstance(restored, UnknownLedgerEntry)
            assert restored.raw_entry_type == "session.started"
            assert restored.raw_payload["seed"] == 42
        finally:
            ENTRY_REGISTRY["session.started"] = original
