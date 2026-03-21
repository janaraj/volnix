"""Pydantic configuration section models for the Terrarium framework.

Every TOML configuration section maps to a frozen or mutable Pydantic model
defined here.  The root :class:`TerrariumConfig` aggregates all sections and
is the output of :class:`~terrarium.config.loader.ConfigLoader`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Individual section models
# ---------------------------------------------------------------------------


class RealityConfig(BaseModel):
    """Configuration for world reality conditions."""

    preset: str = "realistic"
    overrides: dict[str, Any] = Field(default_factory=dict)
    overlays: list[str] = Field(default_factory=list)


class FidelityConfig(BaseModel):
    """Configuration for service fidelity resolution."""

    mode: str = "auto"  # auto | strict | exploratory


class SeedConfig(BaseModel):
    """Configuration for a single seed data injection."""

    description: str = ""
    customer: dict[str, Any] | None = None
    charge: dict[str, Any] | None = None
    ticket: dict[str, Any] | None = None


class SimulationConfig(BaseModel):
    """Configuration for the simulation runtime."""

    seed: int = 42
    time_speed: float = 1.0
    mode: str = "governed"  # governed | ungoverned
    reality: RealityConfig = Field(default_factory=RealityConfig)
    fidelity: FidelityConfig = Field(default_factory=FidelityConfig)
    seeds: list[SeedConfig] = Field(default_factory=list)


class PipelineConfig(BaseModel):
    """Configuration for the governance pipeline steps and behaviour."""

    steps: list[str] = []
    max_retries: int = 0
    timeout_per_step_seconds: float = 30.0
    side_effect_max_depth: int = 10


class BusConfig(BaseModel):
    """Configuration for the event bus."""

    ...


class LedgerConfig(BaseModel):
    """Configuration for the append-only event ledger."""

    ...


class PersistenceConfig(BaseModel):
    """Configuration for state persistence."""

    ...


class StateConfig(BaseModel):
    """Configuration for the world-state engine."""

    ...


class PolicyConfig(BaseModel):
    """Configuration for the policy engine."""

    ...


class PermissionConfig(BaseModel):
    """Configuration for the permission engine."""

    ...


class BudgetConfig(BaseModel):
    """Configuration for the budget engine."""

    ...


class ResponderConfig(BaseModel):
    """Configuration for the responder engine."""

    ...


class AnimatorConfig(BaseModel):
    """Configuration for the animator engine."""

    ...


class AdapterConfig(BaseModel):
    """Configuration for the adapter layer."""

    ...


class ReporterConfig(BaseModel):
    """Configuration for the reporter engine."""

    ...


class FeedbackConfig(BaseModel):
    """Configuration for the feedback engine."""

    ...


class DashboardConfig(BaseModel):
    """Configuration for the dashboard UI."""

    ...


class GatewayConfig(BaseModel):
    """Configuration for the external gateway."""

    host: str = "127.0.0.1"
    port: int = 8080
    middleware: list[str] = []
    rate_limit_enabled: bool = False
    rate_limits: dict[str, int] = {}
    auth_enabled: bool = False


class RunConfig(BaseModel):
    """Configuration for evaluation runs."""

    ...


# ---------------------------------------------------------------------------
# LLM configuration models
# ---------------------------------------------------------------------------


class LLMProviderConfig(BaseModel):
    """Configuration for a single LLM provider."""

    type: str = ""
    base_url: str | None = None
    api_key_ref: str = ""
    default_model: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout_seconds: float = 30.0


class LLMRoutingEntry(BaseModel):
    """A single routing rule mapping an engine/use-case to a provider+model."""

    provider: str = ""
    model: str = ""
    max_tokens: int | None = None
    temperature: float | None = None


class LLMConfig(BaseModel):
    """Top-level LLM configuration with provider definitions and routing table."""

    defaults: LLMProviderConfig = LLMProviderConfig()
    providers: dict[str, LLMProviderConfig] = {}
    routing: dict[str, LLMRoutingEntry] = {}


# ---------------------------------------------------------------------------
# Root configuration
# ---------------------------------------------------------------------------


class TerrariumConfig(BaseModel):
    """Root configuration model aggregating all Terrarium subsystem sections."""

    simulation: SimulationConfig = SimulationConfig()
    pipeline: PipelineConfig = PipelineConfig()
    bus: BusConfig = BusConfig()
    ledger: LedgerConfig = LedgerConfig()
    persistence: PersistenceConfig = PersistenceConfig()
    state: StateConfig = StateConfig()
    policy: PolicyConfig = PolicyConfig()
    permission: PermissionConfig = PermissionConfig()
    budget: BudgetConfig = BudgetConfig()
    responder: ResponderConfig = ResponderConfig()
    animator: AnimatorConfig = AnimatorConfig()
    adapter: AdapterConfig = AdapterConfig()
    reporter: ReporterConfig = ReporterConfig()
    feedback: FeedbackConfig = FeedbackConfig()
    dashboard: DashboardConfig = DashboardConfig()
    gateway: GatewayConfig = GatewayConfig()
    run: RunConfig = RunConfig()
    llm: LLMConfig = LLMConfig()
