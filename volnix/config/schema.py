"""Root configuration schema for Volnix.

This module imports config models from their owning subsystem modules
and assembles them into the root VolnixConfig. Each subsystem owns
its config definition (SRP). No duplicate definitions.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Import from subsystem config files (each module owns its definition)
from volnix.persistence.config import PersistenceConfig
from volnix.bus.config import BusConfig
from volnix.ledger.config import LedgerConfig
from volnix.pipeline.config import PipelineConfig
from volnix.llm.config import LLMConfig
from volnix.gateway.config import GatewayConfig
from volnix.reality.config import RealityConfig, SeedConfig
from volnix.runs.config import RunConfig
from volnix.actors.config import ActorConfig, SlotManagerConfig
from volnix.templates.config import TemplateConfig
from volnix.engines.state.config import StateConfig
from volnix.engines.policy.config import PolicyConfig
from volnix.engines.permission.config import PermissionConfig
from volnix.engines.budget.config import BudgetConfig
from volnix.engines.responder.config import ResponderConfig
from volnix.engines.animator.config import AnimatorConfig
from volnix.engines.adapter.config import AdapterConfig
from volnix.engines.reporter.config import ReporterConfig
from volnix.engines.feedback.config import FeedbackConfig
from volnix.engines.agency.config import AgencyConfig
from volnix.engines.world_compiler.config import WorldCompilerConfig
from volnix.worlds.config import WorldsConfig
from volnix.simulation.config import SimulationRunnerConfig
from volnix.middleware.config import MiddlewareConfig
from volnix.webhook.config import WebhookConfig
from volnix.validation.config import ValidationConfig


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


class VolnixConfig(BaseModel):
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
    agents: SlotManagerConfig = Field(default_factory=SlotManagerConfig)
    templates: TemplateConfig = Field(default_factory=TemplateConfig)
    world_compiler: WorldCompilerConfig = Field(default_factory=WorldCompilerConfig)
    agency: AgencyConfig = Field(default_factory=AgencyConfig)
    profiles: ProfileConfig = Field(default_factory=ProfileConfig)
    simulation_runner: SimulationRunnerConfig = Field(default_factory=SimulationRunnerConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    middleware: MiddlewareConfig = Field(default_factory=MiddlewareConfig)
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
    worlds: WorldsConfig = Field(default_factory=WorldsConfig)
