"""Root configuration schema for Terrarium.

This module imports config models from their owning subsystem modules
and assembles them into the root TerrariumConfig. Each subsystem owns
its config definition (SRP). No duplicate definitions.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Import from subsystem config files (each module owns its definition)
from terrarium.persistence.config import PersistenceConfig
from terrarium.bus.config import BusConfig
from terrarium.ledger.config import LedgerConfig
from terrarium.pipeline.config import PipelineConfig
from terrarium.llm.config import LLMConfig
from terrarium.gateway.config import GatewayConfig
from terrarium.reality.config import RealityConfig, SeedConfig
from terrarium.runs.config import RunConfig
from terrarium.actors.config import ActorConfig
from terrarium.templates.config import TemplateConfig
from terrarium.engines.state.config import StateConfig
from terrarium.engines.policy.config import PolicyConfig
from terrarium.engines.permission.config import PermissionConfig
from terrarium.engines.budget.config import BudgetConfig
from terrarium.engines.responder.config import ResponderConfig
from terrarium.engines.animator.config import AnimatorConfig
from terrarium.engines.adapter.config import AdapterConfig
from terrarium.engines.reporter.config import ReporterConfig
from terrarium.engines.feedback.config import FeedbackConfig
from terrarium.engines.agency.config import AgencyConfig
from terrarium.engines.world_compiler.config import WorldCompilerConfig
from terrarium.simulation.config import SimulationRunnerConfig
from terrarium.middleware.config import MiddlewareConfig
from terrarium.webhook.config import WebhookConfig
from terrarium.validation.config import ValidationConfig


class ProfileConfig(BaseModel):
    """Tier 2 service profile configuration."""
    model_config = ConfigDict(frozen=True)
    data_dir: str = "terrarium/packs/profiles"
    infer_on_missing: bool = True


class FidelityConfig(BaseModel):
    """Service fidelity resolution mode."""
    model_config = ConfigDict(frozen=True)
    mode: str = "auto"  # auto | strict | exploratory


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


class TerrariumConfig(BaseModel):
    """Root configuration — assembles all subsystem configs."""
    model_config = ConfigDict(frozen=True)
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
    templates: TemplateConfig = Field(default_factory=TemplateConfig)
    world_compiler: WorldCompilerConfig = Field(default_factory=WorldCompilerConfig)
    agency: AgencyConfig = Field(default_factory=AgencyConfig)
    profiles: ProfileConfig = Field(default_factory=ProfileConfig)
    simulation_runner: SimulationRunnerConfig = Field(default_factory=SimulationRunnerConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    middleware: MiddlewareConfig = Field(default_factory=MiddlewareConfig)
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
