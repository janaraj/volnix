"""MemoryEngine configuration (PMF Plan Phase 4B, Step 2).

Disabled by default: ``enabled = False`` means no MemoryEngine is
constructed and every activation follows the Phase-4A path. Every
existing blueprint, the Phase 0 regression oracle, and all pre-4B
tests must stay byte-identical while memory is disabled.

Pydantic validators reject nonsense at YAML-load time (per the
Phase 4B test-discipline gate: negative case first). Validation
applies only when ``enabled=True`` — turning memory off is a valid
state regardless of other fields, so a disabled config with garbage
knobs is accepted as "memory off."

See:
- Phase 4B plan: ``internal_docs/pmf/phase-4b-memory-engine.md``
- Approved gap-analysis corrections: ``.claude/plans/the-pdf-is-the-wiggly-matsumoto.md``
- DESIGN_PRINCIPLES.md §Test Discipline
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Module-level constants. Reused by the config validator AND by tests
# and the store layer — single source of truth for every bound so no
# numeric literal leaks into code outside this module. Exported (no
# leading underscore on the names we want external) so tests don't
# duplicate the valid-set inline and drift (N1).
VALID_CADENCE_TRIGGERS: frozenset[str] = frozenset(
    {"on_eviction", "periodic", "on_activation_complete"}
)
VALID_EMBEDDER_SCHEMES: frozenset[str] = frozenset(
    {"fts5", "sentence-transformers", "openai"}
)

# Aliases kept for any caller that still references the underscored
# names — internal-only module constants keep the underscore.
_VALID_CADENCE_TRIGGERS = VALID_CADENCE_TRIGGERS
_VALID_EMBEDDER_SCHEMES = VALID_EMBEDDER_SCHEMES


class MemoryConfig(BaseModel):
    """Memory Engine configuration. All knobs live here — per
    DESIGN_PRINCIPLES, no numeric literal in the engine body.

    Cross-field validation (``_validate`` below) rejects:
    - Unknown consolidation triggers.
    - Unknown embedder scheme.
    - Non-positive caps when enabled.
    - ``consolidation_episodic_window`` larger than
      ``max_episodic_per_actor`` (consolidation reads the window,
      so it cannot exceed the ring-buffer cap).
    - Negative ``recall_p95_budget_ms``.
    - ``schema_version`` other than 1 in 4B.
    """

    model_config = ConfigDict(frozen=True)

    # ── Master switch ─────────────────────────────────────────────
    enabled: bool = False
    """Disabled by default. Every existing blueprint must stay
    byte-identical when ``enabled=False``."""

    # ── Tier mode ─────────────────────────────────────────────────
    tier_mode: Literal["tier2_only", "mixed"] = "tier2_only"
    """``tier2_only``: Tier-1 pack fixtures ignored even if present.
    ``mixed``: Tier-1 fixtures loaded at world compile, Tier-2 layers
    on top. Useful for benchmarking Tier-2 in isolation."""

    # ── Embedder ──────────────────────────────────────────────────
    embedder: str = "fts5"
    """Format: ``<scheme>`` or ``<scheme>:<model>``. Scheme must be
    one of ``fts5``, ``sentence-transformers``, ``openai``. FTS5
    default keeps the install zero-dep and deterministic."""

    embedder_cache_enabled: bool = True
    """Controls the content-hash embedding cache. Turning it off
    forces every embed() call to recompute — useful for tests that
    verify determinism of the underlying provider."""

    # ── Size caps ─────────────────────────────────────────────────
    max_episodic_per_actor: int = Field(default=500, ge=1)
    max_semantic_per_actor: int = Field(default=100, ge=1)

    # ── Consolidation ─────────────────────────────────────────────
    consolidation_triggers: list[str] = Field(
        default_factory=lambda: ["on_eviction", "periodic"]
    )
    """Subset of ``on_eviction``, ``periodic``, ``on_activation_complete``."""

    consolidation_periodic_interval_ticks: int = Field(default=100, ge=1)
    consolidation_episodic_window: int = Field(default=50, ge=1)
    """How many most-recent episodic records the distiller reads per
    consolidation pass. Must be ``<= max_episodic_per_actor``."""

    distillation_enabled: bool = True
    distillation_llm_use_case: str = "memory_distill"
    """Routes through ``LLMRouter`` so budget + retry + provider
    selection flow through the existing stack. BudgetEngine integration
    is automatic — see G10 of the gap analysis."""

    # ── Recall defaults ───────────────────────────────────────────
    default_recall_top_k: int = Field(default=5, ge=1, le=1000)
    recall_p95_budget_ms: int = Field(default=10, ge=0)
    """Test-discipline tight bound — integration tests assert recall
    p95 actually meets this, not a lazy ``< 1s``."""

    # ── Write / exposure ──────────────────────────────────────────
    expose_remember_tool: bool = False
    """Per-profile override. When true, agents/NPCs see a ``remember``
    tool in their tool scope. Off by default — implicit distillation
    covers most cases and the tool is opt-in for agents that need
    explicit memory control (W3 hybrid write policy)."""

    # ── Hydration ─────────────────────────────────────────────────
    hydrate_on_promote: bool = False
    """Lazy-on-first-recall hydration is the default. Set true to
    warm the cache eagerly when a cohort promotes an actor — costs
    one recall round-trip per promote but avoids cold-first-activation
    latency."""

    # ── Storage ───────────────────────────────────────────────────
    storage_db_name: str = Field(
        default="volnix_memory",
        pattern=r"^[a-zA-Z0-9_]+$",
        min_length=1,
    )
    """Logical DB name passed to ``ConnectionManager.get_connection()``.

    Pattern-enforced: alphanumeric + underscore only. No file suffix
    — the manager appends ``.db`` itself. No path separators — that
    would be a traversal vector (C1 of Step 2 review).

    Wire-time resolution: ``app.py`` calls
    ``connection_manager.get_connection(cfg.memory.storage_db_name)``
    to turn this logical name into a concrete ``Database`` instance
    injected into ``SQLiteMemoryStore`` (D1 of Step 2 review; G5 of
    the Phase 4B gap analysis).
    """

    reset_on_world_start: bool = True
    """When True, memory records for the current world are cleared
    on MemoryEngine initialize. This keeps 4B's contract explicit:
    cross-run memory sharing is an opt-in feature, not an accidental
    byproduct of on-disk persistence (G15)."""

    # ── Schema ────────────────────────────────────────────────────
    schema_version: int = Field(default=1, ge=1)
    """SQLite schema version. 4B ships version 1; migrations land
    when a later phase needs them (G12)."""

    @model_validator(mode="after")
    def _validate(self) -> MemoryConfig:
        # Structural bounds (Field(ge=..., le=..., pattern=...))
        # always fire, regardless of ``enabled``. Cross-field semantic
        # validation below only fires when the engine will actually
        # be constructed — turning memory off must always succeed so
        # a pre-4B world with default-disabled memory loads cleanly.
        if not self.enabled:
            return self

        # Cadence triggers: each must be known, and duplicates are
        # rejected (C3 of Step 2 review — duplicate "on_eviction"
        # would fire consolidation twice).
        seen: set[str] = set()
        for trigger in self.consolidation_triggers:
            if trigger not in VALID_CADENCE_TRIGGERS:
                raise ValueError(
                    f"MemoryConfig.consolidation_triggers: unknown trigger "
                    f"{trigger!r}. Expected one of "
                    f"{sorted(VALID_CADENCE_TRIGGERS)}."
                )
            if trigger in seen:
                raise ValueError(
                    f"MemoryConfig.consolidation_triggers: duplicate "
                    f"trigger {trigger!r}. Each trigger may appear at "
                    f"most once."
                )
            seen.add(trigger)

        # Embedder scheme + model. Format is ``<scheme>`` or
        # ``<scheme>:<model>`` — scheme must be known, and when a
        # colon appears the suffix must be non-empty (C2 of Step 2
        # review: ``"openai:"`` is nonsense and would silently call
        # the provider with an empty model name).
        embedder_parts = self.embedder.split(":", 1)
        scheme = embedder_parts[0]
        if scheme not in VALID_EMBEDDER_SCHEMES:
            raise ValueError(
                f"MemoryConfig.embedder: unknown scheme {scheme!r}. "
                f"Expected format ``<scheme>`` or ``<scheme>:<model>`` "
                f"where scheme is one of "
                f"{sorted(VALID_EMBEDDER_SCHEMES)} (M3 of Step 2 review)."
            )
        if len(embedder_parts) == 2 and not embedder_parts[1]:
            raise ValueError(
                f"MemoryConfig.embedder: empty model suffix in "
                f"{self.embedder!r}. When the ``:`` separator is "
                f"present, the model name must be non-empty."
            )

        # Consolidation window cannot exceed the ring-buffer cap —
        # the distiller reads the window, so asking for 100 when the
        # buffer holds 50 is a config bug, not a graceful clip.
        if self.consolidation_episodic_window > self.max_episodic_per_actor:
            raise ValueError(
                f"MemoryConfig.consolidation_episodic_window "
                f"({self.consolidation_episodic_window}) must not exceed "
                f"max_episodic_per_actor ({self.max_episodic_per_actor})."
            )

        # 4B ships schema_version 1 only.
        if self.schema_version != 1:
            raise ValueError(
                f"MemoryConfig.schema_version: unsupported version "
                f"{self.schema_version}; Phase 4B ships v1 only."
            )

        return self
