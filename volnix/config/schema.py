"""Root configuration schema for Volnix.

This module imports config models from their owning subsystem modules
and assembles them into the root VolnixConfig. Each subsystem owns
its config definition (SRP). No duplicate definitions.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from volnix.actors.config import ActorConfig, SlotManagerConfig
from volnix.bus.config import BusConfig
from volnix.engines.adapter.config import AdapterConfig
from volnix.engines.agency.config import AgencyConfig
from volnix.engines.animator.config import AnimatorConfig
from volnix.engines.budget.config import BudgetConfig
from volnix.engines.feedback.config import FeedbackConfig
from volnix.engines.memory.config import MemoryConfig
from volnix.engines.permission.config import PermissionConfig
from volnix.engines.policy.config import PolicyConfig
from volnix.engines.reporter.config import ReporterConfig
from volnix.engines.responder.config import ResponderConfig
from volnix.engines.state.config import StateConfig
from volnix.engines.world_compiler.config import WorldCompilerConfig
from volnix.gateway.config import GatewayConfig
from volnix.ledger.config import LedgerConfig
from volnix.llm.config import LLMConfig
from volnix.middleware.config import MiddlewareConfig

# Import from subsystem config files (each module owns its definition)
from volnix.persistence.config import PersistenceConfig
from volnix.pipeline.config import PipelineConfig
from volnix.reality.config import RealityConfig, SeedConfig
from volnix.runs.config import RunConfig
from volnix.sessions.config import SessionsConfig


class PrivacyConfig(BaseModel):
    """Privacy knobs (PMF Plan Phase 4C Step 14).

    Attributes:
        ephemeral: When ``True``, suppresses ledger disk writes
            for the life of the process. **SCOPE LIMIT AT 0.2.0**:
            ONLY ``Ledger.append`` honours this flag today. Bus
            persistence, snapshot store, run artifacts, and the
            ``llm_debug`` flat-files all continue to write. A
            full per-sink ephemeral mode lands in a follow-up
            step; until then a privacy-sensitive consumer who
            needs zero disk writes should also set
            ``bus.persistence_enabled=False`` and disable the
            run-artifact / snapshot sinks directly.
        ledger_redactor: Dotted-path string
            (``"package.module:callable_name"``) resolving to a
            callable ``(LedgerEntry) -> LedgerEntry``. Called by
            the ledger before every ``append``. ``None`` (default)
            uses the identity redactor (no-op). Invalid paths
            raise ``LedgerRedactorError`` at resolve time.
            Contract: the redactor MUST return a fresh
            ``LedgerEntry`` (mutation of the input is undefined
            behaviour) and MUST NOT change ``entry_type`` (the
            type filter runs BEFORE the redactor — see
            :meth:`Ledger.append`).
    """

    # Post-impl audit H1: ``extra="forbid"`` catches typo'd
    # fields (``ephemaral=True``) at config-load time — matches
    # the discipline applied to ``CharacterDefinition`` (Step 11)
    # and ``PackManifest`` (Step 13).
    model_config = ConfigDict(frozen=True, extra="forbid")

    ephemeral: bool = False
    ledger_redactor: str | None = None


from volnix.simulation.config import SimulationRunnerConfig
from volnix.templates.config import TemplateConfig
from volnix.validation.config import ValidationConfig
from volnix.webhook.config import WebhookConfig
from volnix.worlds.config import WorldsConfig


class ProfileConfig(BaseModel):
    """Tier 2 service profile configuration."""

    model_config = ConfigDict(frozen=True)
    data_dir: str = "volnix/packs/profiles"
    infer_on_missing: bool = True


class FidelityConfig(BaseModel):
    """Service fidelity resolution mode."""

    model_config = ConfigDict(frozen=True)
    mode: str = "auto"  # auto | strict | exploratory


class LoggingConfig(BaseModel):
    """Application logging configuration."""

    model_config = ConfigDict(frozen=True)
    level: str = "WARNING"
    format: str = "text"
    llm_debug: bool = False


class DashboardConfig(BaseModel):
    """Web dashboard configuration."""

    model_config = ConfigDict(frozen=True)
    host: str = "127.0.0.1"
    port: int = 8200
    enabled: bool = False


class SimulationConfig(BaseModel):
    """Top-level simulation orchestration config."""

    model_config = ConfigDict(frozen=True)
    seed: int = 42
    time_speed: float = 1.0
    mode: str = "governed"  # governed | ungoverned
    behavior: str = "dynamic"  # static | reactive | dynamic
    reality: RealityConfig = Field(default_factory=RealityConfig)
    fidelity: FidelityConfig = Field(default_factory=FidelityConfig)
    seeds: list[SeedConfig] = Field(default_factory=list)


class PackSearchPath(BaseModel):
    """One additive pack search entry for a library consumer.

    PMF Plan Phase 4C Step 2. Two modes:

    - **Bundled mode** (``package_prefix=None``): the path lives under
      a directory that contains an importable ``volnix`` package —
      module names are derived via the pre-existing ``volnix.packs.*``
      namespace walk. Rare: almost no external consumer ships their
      catalog under ``volnix/``.
    - **External mode** (``package_prefix`` set): the path is the
      directory whose subdirectories hold ``pack.py`` modules that
      import as ``{package_prefix}.<subdir>.pack``. The consumer must
      have placed the PARENT of this directory on ``sys.path``
      (``ConfigBuilder.pack_search_path(..., ensure_on_syspath=True)``
      does this automatically — see that method's docstring).

    Example::

        PackSearchPath(
            path="/opt/myproduct/characters",
            package_prefix="characters",
        )
        # sys.path must contain /opt/myproduct; modules import as
        # characters.interviewer.pack, etc.
    """

    model_config = ConfigDict(frozen=True)
    path: str
    package_prefix: str | None = None


class VolnixConfig(BaseModel):
    """Root configuration — assembles all subsystem configs."""

    model_config = ConfigDict(frozen=True)

    # PMF Plan Phase 4C Step 2 — additive pack search paths for library
    # consumers embedding Volnix into their own product. Paths are
    # searched on top of the bundled ``volnix/packs/verified/``
    # directory. Entries with
    # ``package_prefix`` are routed via the external-prefix loader;
    # entries without are treated as bundled-mode (rare for consumers).
    pack_search_paths: list[PackSearchPath] = Field(default_factory=list)

    @field_validator("pack_search_paths", mode="after")
    @classmethod
    def _dedupe_pack_search_paths(cls, value: list[PackSearchPath]) -> list[PackSearchPath]:
        """Dedupe ``pack_search_paths`` on ``(path, package_prefix)``,
        preserving first-seen order. Closes the ``from_dict`` / TOML
        path gap identified in the Step-2/3 post-ship audit — the
        ``ConfigBuilder`` side dedupes at construction, but this
        validator ensures the same guarantee applies when a consumer
        reaches the schema directly (dict round-trip, TOML layering).
        """
        seen: set[tuple[str, str | None]] = set()
        deduped: list[PackSearchPath] = []
        for entry in value:
            key = (entry.path, entry.package_prefix)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(entry)
        return deduped

    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    bus: BusConfig = Field(default_factory=BusConfig)
    ledger: LedgerConfig = Field(default_factory=LedgerConfig)
    persistence: PersistenceConfig = Field(default_factory=PersistenceConfig)
    state: StateConfig = Field(default_factory=StateConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    permission: PermissionConfig = Field(default_factory=PermissionConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    responder: ResponderConfig = Field(default_factory=ResponderConfig)
    animator: AnimatorConfig = Field(default_factory=AnimatorConfig)
    adapter: AdapterConfig = Field(default_factory=AdapterConfig)
    reporter: ReporterConfig = Field(default_factory=ReporterConfig)
    feedback: FeedbackConfig = Field(default_factory=FeedbackConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    runs: RunConfig = Field(default_factory=RunConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    actors: ActorConfig = Field(default_factory=ActorConfig)
    agents: SlotManagerConfig = Field(default_factory=SlotManagerConfig)
    templates: TemplateConfig = Field(default_factory=TemplateConfig)
    world_compiler: WorldCompilerConfig = Field(default_factory=WorldCompilerConfig)
    agency: AgencyConfig = Field(default_factory=AgencyConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    profiles: ProfileConfig = Field(default_factory=ProfileConfig)
    simulation_runner: SimulationRunnerConfig = Field(default_factory=SimulationRunnerConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    middleware: MiddlewareConfig = Field(default_factory=MiddlewareConfig)
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
    worlds: WorldsConfig = Field(default_factory=WorldsConfig)
    sessions: SessionsConfig = Field(default_factory=SessionsConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)

    # PMF Plan Phase 4C Step 12 — product-side extractor hook.
    # Dotted-path string in the form ``"package.module:callable"``
    # (colon separator per Python entry-point convention). Resolved
    # via ``volnix.actors.trait_extractor.resolve_extractor_hook``
    # at extract time; ``None`` (default) uses the bundled
    # ``volnix.actors.trait_extractor.extract_behavior_traits``.
    # Invalid paths raise a descriptive error AT RESOLVE TIME, not
    # silently at extract time.
    trait_extractor_hook: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VolnixConfig:
        """Construct a ``VolnixConfig`` from a nested dict.

        Canonical programmatic constructor (PMF Plan Phase 4C Step 2).
        Runs full Pydantic validation; raises ``ValidationError`` on
        malformed input.

        The file-based ``ConfigLoader`` remains the entry point for TOML
        workflows — it performs its layered merge and then calls this
        method as the final validation pass.
        """
        return cls.model_validate(data)
