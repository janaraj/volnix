"""Tests for MemoryConfig (PMF Plan Phase 4B, Step 2).

Per test discipline (DESIGN_PRINCIPLES.md §Test Discipline):
negative cases first on every validator.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from volnix.engines.memory.config import (
    VALID_CADENCE_TRIGGERS,
    VALID_EMBEDDER_SCHEMES,
    VALID_TOKENIZER_PREFIXES,
    MemoryConfig,
)


class TestDefaultsDisabled:
    """The whole point of default-off is that pre-4B worlds validate
    without knowing memory exists. A disabled config must accept
    anything downstream of ``enabled=False`` without validator churn.
    """

    def test_default_is_disabled(self) -> None:
        cfg = MemoryConfig()
        assert cfg.enabled is False
        assert cfg.tier_mode == "tier2_only"
        assert cfg.embedder == "fts5"
        assert cfg.storage_db_name == "volnix_memory"
        assert cfg.schema_version == 1

    def test_disabled_skips_model_validator_not_field_bounds(self) -> None:
        # When disabled, the ``model_validator`` (semantic cross-field
        # checks) is skipped. Structural ``Field(ge=...)`` bounds still
        # apply — 0 or negative caps are nonsense regardless of
        # ``enabled``. This is the right split (M1 of Step 2 review).
        cfg = MemoryConfig(
            enabled=False,
            # These would all fail the model_validator if enabled=True:
            embedder="totally-made-up",
            consolidation_triggers=["never_heard_of_it"],
            consolidation_episodic_window=9999,
            max_episodic_per_actor=1,  # passes Field(ge=1)
        )
        assert cfg.enabled is False

    def test_disabled_still_enforces_field_bounds(self) -> None:
        # M1 continued: Field bounds fire regardless of ``enabled``
        # because they encode structural validity, not semantic fit.
        with pytest.raises(ValidationError):
            MemoryConfig(enabled=False, max_episodic_per_actor=0)
        with pytest.raises(ValidationError):
            MemoryConfig(enabled=False, default_recall_top_k=-1)

    def test_enabled_with_only_defaults_validates(self) -> None:
        # M2 of Step 2 review: the minimum-viable enabled config must
        # validate with no extra arguments. Every default is deliberate;
        # any future change that breaks this test is likely breaking
        # the default behavior contract.
        cfg = MemoryConfig(enabled=True)
        assert cfg.enabled is True
        assert cfg.embedder == "fts5"
        assert cfg.tier_mode == "tier2_only"
        assert cfg.consolidation_triggers == ["on_eviction", "periodic"]

    def test_frozen(self) -> None:
        cfg = MemoryConfig()
        with pytest.raises((ValidationError, AttributeError, TypeError)):
            cfg.enabled = True  # type: ignore[misc]


class TestCadenceTriggers:
    """Cadence triggers must come from the known set. A typo like
    'on_evict' silently skipping consolidation is the class of
    failure the Phase 4A review codified 'negative case first' for."""

    def test_negative_unknown_trigger_rejected_when_enabled(self) -> None:
        with pytest.raises(ValidationError, match="unknown trigger"):
            MemoryConfig(
                enabled=True,
                consolidation_triggers=["on_evict"],  # typo
            )

    def test_negative_mixed_valid_and_invalid_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown trigger"):
            MemoryConfig(
                enabled=True,
                consolidation_triggers=["on_eviction", "GARBAGE"],
            )

    @pytest.mark.parametrize(
        "triggers",
        [
            ["on_eviction"],
            ["periodic"],
            ["on_activation_complete"],
            ["on_eviction", "periodic"],
            ["on_eviction", "periodic", "on_activation_complete"],
            [],  # empty is a valid "never consolidate" state
        ],
    )
    def test_positive_valid_trigger_combinations(self, triggers: list[str]) -> None:
        cfg = MemoryConfig(enabled=True, consolidation_triggers=triggers)
        assert cfg.consolidation_triggers == triggers

    # C3 of Step 2 review: duplicates silently accepted would fire
    # consolidation twice on the same event. Validator rejects.
    def test_negative_duplicate_trigger_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate"):
            MemoryConfig(
                enabled=True,
                consolidation_triggers=["on_eviction", "on_eviction"],
            )

    def test_negative_duplicate_among_valid_values_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate"):
            MemoryConfig(
                enabled=True,
                consolidation_triggers=["on_eviction", "periodic", "on_eviction"],
            )

    # N1: tests source from the exported frozenset so a rename
    # doesn't drift. Every value in the frozenset must be individually
    # acceptable as a sole trigger.
    def test_every_exported_trigger_is_accepted_individually(self) -> None:
        for trigger in VALID_CADENCE_TRIGGERS:
            cfg = MemoryConfig(enabled=True, consolidation_triggers=[trigger])
            assert cfg.consolidation_triggers == [trigger]


class TestEmbedderScheme:
    """Embedder string is '<scheme>' or '<scheme>:<model>'. Scheme
    must be one of three known values."""

    @pytest.mark.parametrize(
        "bad_embedder",
        [
            "fts",  # close but wrong
            "FTS5",  # case mismatch
            "transformer",  # partial
            "huggingface:all-MiniLM-L6-v2",  # wrong prefix
            "",  # empty
        ],
    )
    def test_negative_unknown_scheme_rejected(self, bad_embedder: str) -> None:
        with pytest.raises(ValidationError, match="unknown scheme"):
            MemoryConfig(enabled=True, embedder=bad_embedder)

    @pytest.mark.parametrize(
        "good_embedder",
        [
            "fts5",
            "sentence-transformers",
            "sentence-transformers:all-MiniLM-L6-v2",
            "openai",
            "openai:text-embedding-3-small",
        ],
    )
    def test_positive_schemes_accepted(self, good_embedder: str) -> None:
        cfg = MemoryConfig(enabled=True, embedder=good_embedder)
        assert cfg.embedder == good_embedder

    # C2 of Step 2 review: empty model suffix after colon is nonsense
    # and would silently call providers with an empty model name.
    @pytest.mark.parametrize(
        "bad_embedder",
        ["openai:", "sentence-transformers:", "fts5:"],
    )
    def test_negative_empty_model_suffix_rejected(self, bad_embedder: str) -> None:
        with pytest.raises(ValidationError, match="empty model"):
            MemoryConfig(enabled=True, embedder=bad_embedder)

    # N1 — every exported scheme accepted as a bare scheme.
    def test_every_exported_scheme_accepted(self) -> None:
        for scheme in VALID_EMBEDDER_SCHEMES:
            cfg = MemoryConfig(enabled=True, embedder=scheme)
            assert cfg.embedder == scheme

    # M3 — error message guides the user to the ``<scheme>:<model>`` shape
    def test_error_message_shows_format(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            MemoryConfig(enabled=True, embedder="bge")
        # Error message should mention the format + all schemes.
        msg = str(excinfo.value)
        assert "<scheme>" in msg
        assert "<model>" in msg
        for scheme in VALID_EMBEDDER_SCHEMES:
            assert scheme in msg


class TestSizeCaps:
    """Caps and windows must be positive. The distiller window can
    never exceed the ring buffer — that's a silent-truncation trap
    the 4A plan codified 'fail fast' for."""

    @pytest.mark.parametrize("bad_cap", [0, -1, -100])
    def test_negative_max_episodic_zero_or_negative_rejected(self, bad_cap: int) -> None:
        with pytest.raises(ValidationError):
            MemoryConfig(enabled=True, max_episodic_per_actor=bad_cap)

    @pytest.mark.parametrize("bad_cap", [0, -1, -100])
    def test_negative_max_semantic_zero_or_negative_rejected(self, bad_cap: int) -> None:
        with pytest.raises(ValidationError):
            MemoryConfig(enabled=True, max_semantic_per_actor=bad_cap)

    def test_negative_consolidation_window_exceeds_cap_rejected(self) -> None:
        # Ring buffer holds 50; distiller wants 100. Nonsense.
        with pytest.raises(ValidationError, match="consolidation_episodic_window"):
            MemoryConfig(
                enabled=True,
                max_episodic_per_actor=50,
                consolidation_episodic_window=100,
            )

    def test_positive_consolidation_window_equal_to_cap_ok(self) -> None:
        cfg = MemoryConfig(
            enabled=True,
            max_episodic_per_actor=100,
            consolidation_episodic_window=100,
        )
        assert cfg.consolidation_episodic_window == 100

    def test_negative_default_recall_top_k_bounds(self) -> None:
        with pytest.raises(ValidationError):
            MemoryConfig(enabled=True, default_recall_top_k=0)
        with pytest.raises(ValidationError):
            MemoryConfig(enabled=True, default_recall_top_k=1001)


class TestRecallBudget:
    """G14 tight-bound: recall_p95_budget_ms is a test assertion
    target. Must be non-negative."""

    @pytest.mark.parametrize("bad_budget", [-1, -100])
    def test_negative_recall_budget_rejected(self, bad_budget: int) -> None:
        with pytest.raises(ValidationError):
            MemoryConfig(enabled=True, recall_p95_budget_ms=bad_budget)

    def test_positive_zero_budget_is_valid_for_contract_testing(self) -> None:
        # zero is valid — means "recall must be effectively instant";
        # a test-time override to force tight-bound failure is useful.
        cfg = MemoryConfig(enabled=True, recall_p95_budget_ms=0)
        assert cfg.recall_p95_budget_ms == 0


class TestSchemaVersion:
    """G12: schema versioning is plumbed now so migrations are
    possible later. Only version 1 ships in 4B."""

    def test_negative_future_schema_version_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unsupported version"):
            MemoryConfig(enabled=True, schema_version=2)

    def test_negative_zero_schema_version_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MemoryConfig(schema_version=0)

    def test_positive_version_1_accepted(self) -> None:
        cfg = MemoryConfig(enabled=True, schema_version=1)
        assert cfg.schema_version == 1


class TestTierMode:
    """G-discussion: configurable choice between pure Tier-2 and
    Tier-1+Tier-2 mix. Tier mode is a Literal so typos fail fast."""

    def test_negative_unknown_tier_mode_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MemoryConfig(tier_mode="tier_3")  # type: ignore[arg-type]

    @pytest.mark.parametrize("mode", ["tier2_only", "mixed"])
    def test_positive_tier_modes(self, mode: str) -> None:
        cfg = MemoryConfig(tier_mode=mode)  # type: ignore[arg-type]
        assert cfg.tier_mode == mode


class TestTopLevelNestingInVolnixConfig:
    """G1: ``memory`` is a top-level field of ``VolnixConfig``, NOT
    nested under ``agency``. This is a regression guard — the draft
    plan made this mistake, and the architecture audit must catch
    any future regression.
    """

    def test_memory_is_sibling_of_agency_not_child(self) -> None:
        # N2 of Step 2 review: tighter regression guard via model_fields.
        # hasattr-style check passes even if memory lands at both top
        # and nested positions. model_fields inspection catches that.
        from volnix.config.schema import VolnixConfig
        from volnix.engines.agency.config import AgencyConfig

        assert "memory" in VolnixConfig.model_fields, (
            "memory must be a declared field on VolnixConfig (G1)."
        )
        assert "memory" not in AgencyConfig.model_fields, (
            "memory must NOT be declared on AgencyConfig; it is a "
            "top-level engine config, not an agency sub-concern (G1)."
        )
        # Runtime shape also checks out.
        cfg = VolnixConfig()
        assert isinstance(cfg.memory, MemoryConfig)
        assert not hasattr(cfg.agency, "memory")

    def test_default_volnix_config_disabled_memory(self) -> None:
        from volnix.config.schema import VolnixConfig

        cfg = VolnixConfig()
        assert cfg.memory.enabled is False


class TestTomlRoundTrip:
    """The ``[memory]`` block in ``volnix.toml`` must parse into
    ``MemoryConfig`` with the documented defaults. This locks in the
    contract between the config file and the schema so a silent
    field rename in either direction fails loudly here, not in an
    integration test at runtime.
    """

    def test_volnix_toml_memory_block_loads(self) -> None:
        from volnix.config.loader import ConfigLoader
        from volnix.config.schema import VolnixConfig

        cfg = ConfigLoader().load()
        assert isinstance(cfg, VolnixConfig)
        assert isinstance(cfg.memory, MemoryConfig)

        # Every field documented in volnix.toml [memory] must land
        # at its expected default.
        assert cfg.memory.enabled is False
        assert cfg.memory.tier_mode == "tier2_only"
        assert cfg.memory.embedder == "fts5"
        assert cfg.memory.embedder_cache_enabled is True
        assert cfg.memory.max_episodic_per_actor == 500
        assert cfg.memory.max_semantic_per_actor == 100
        assert cfg.memory.consolidation_triggers == ["on_eviction", "periodic"]
        assert cfg.memory.consolidation_periodic_interval_ticks == 100
        assert cfg.memory.consolidation_episodic_window == 50
        assert cfg.memory.distillation_enabled is True
        assert cfg.memory.distillation_llm_use_case == "memory_distill"
        assert cfg.memory.default_recall_top_k == 5
        assert cfg.memory.recall_p95_budget_ms == 10
        assert cfg.memory.expose_remember_tool is False
        assert cfg.memory.hydrate_on_promote is False
        assert cfg.memory.storage_db_name == "volnix_memory"
        assert cfg.memory.reset_on_world_start is True
        assert cfg.memory.schema_version == 1
        assert cfg.memory.fts_tokenizer == "porter unicode61 remove_diacritics 2"


class TestBooleanToggles:
    """Every boolean knob should flip cleanly. These tests fail loudly
    if a field rename ever silently breaks YAML/TOML deserialization."""

    @pytest.mark.parametrize(
        "field",
        [
            "embedder_cache_enabled",
            "distillation_enabled",
            "expose_remember_tool",
            "hydrate_on_promote",
            "reset_on_world_start",
        ],
    )
    @pytest.mark.parametrize("value", [True, False])
    def test_boolean_toggles_round_trip(self, field: str, value: bool) -> None:
        cfg = MemoryConfig(**{field: value})
        assert getattr(cfg, field) is value


class TestFtsTokenizer:
    """Phase 4B Step 4 — FTS5 tokenizer is configurable with a
    known-prefix allowlist. The prefix check runs regardless of
    ``enabled`` so typos are caught even in disabled configs.
    """

    @pytest.mark.parametrize(
        "bad_prefix",
        [
            "portter unicode61",  # typo in porter
            "PORTER unicode61",  # uppercase not allowed
            "transformer unicode61",  # unknown scheme
            "",  # empty
            "   ",  # whitespace only
        ],
    )
    def test_negative_unknown_prefix_rejected(self, bad_prefix: str) -> None:
        with pytest.raises(ValidationError, match="fts_tokenizer"):
            MemoryConfig(fts_tokenizer=bad_prefix)

    def test_negative_prefix_check_runs_when_disabled_too(self) -> None:
        # Tokenizer shape is structural — typos must fail even
        # with enabled=False, so CI catches bad config on a world
        # that *intends* to enable memory later.
        with pytest.raises(ValidationError):
            MemoryConfig(enabled=False, fts_tokenizer="garbage prefix")

    def test_default_includes_remove_diacritics_2(self) -> None:
        # The whole point of the default — fixes the default-
        # diacritics gap in bare ``unicode61``.
        cfg = MemoryConfig()
        assert "remove_diacritics 2" in cfg.fts_tokenizer
        assert cfg.fts_tokenizer.startswith("porter ")

    @pytest.mark.parametrize(
        "good_tokenizer",
        [
            "porter unicode61 remove_diacritics 2",
            "unicode61",
            "unicode61 remove_diacritics 2",
            "trigram",
            "ascii",
            "porter",
        ],
    )
    def test_positive_valid_tokenizers_accepted(self, good_tokenizer: str) -> None:
        cfg = MemoryConfig(fts_tokenizer=good_tokenizer)
        assert cfg.fts_tokenizer == good_tokenizer

    def test_every_exported_prefix_accepted_bare(self) -> None:
        # N1-style test — exported set is source of truth; every
        # member must be individually acceptable.
        for prefix in VALID_TOKENIZER_PREFIXES:
            cfg = MemoryConfig(fts_tokenizer=prefix)
            assert cfg.fts_tokenizer == prefix


class TestStorageDbName:
    """C1 of Step 2 review — the logical DB name must be pattern-
    validated. Empty string, path separators, special sqlite names
    are all traversal or ambiguity vectors.
    """

    def test_default_logical_name(self) -> None:
        cfg = MemoryConfig()
        assert cfg.storage_db_name == "volnix_memory"
        assert "/" not in cfg.storage_db_name
        assert "." not in cfg.storage_db_name  # logical name, no file suffix

    @pytest.mark.parametrize(
        "bad_name",
        [
            "",  # empty
            "memory/v1",  # forward slash — traversal vector
            "..",  # parent directory
            "../memory",  # explicit traversal
            "memory\\v1",  # backslash
            ":memory:",  # SQLite reserved in-memory name
            "volnix memory",  # space
            "memory.db",  # with suffix (manager adds it)
            "mem-v1",  # hyphen not in [a-zA-Z0-9_]
        ],
    )
    def test_negative_invalid_db_name_rejected(self, bad_name: str) -> None:
        with pytest.raises(ValidationError):
            MemoryConfig(storage_db_name=bad_name)

    @pytest.mark.parametrize(
        "good_name",
        ["memory", "volnix_memory", "mem_v1", "VolnixMemory42"],
    )
    def test_positive_valid_db_names_accepted(self, good_name: str) -> None:
        cfg = MemoryConfig(storage_db_name=good_name)
        assert cfg.storage_db_name == good_name
