"""Pipeline builder for the Terrarium framework.

Constructs a :class:`~terrarium.pipeline.dag.PipelineDAG` from
configuration and a step registry dictionary.
"""

from __future__ import annotations

from typing import Any

from terrarium.core.protocols import LedgerProtocol, PipelineStep
from terrarium.pipeline.config import PipelineConfig
from terrarium.pipeline.dag import PipelineDAG


def build_pipeline_from_config(
    config: PipelineConfig,
    registry: dict[str, PipelineStep],
    *,
    bus: Any | None = None,
    ledger: LedgerProtocol | None = None,
) -> PipelineDAG:
    """Build a pipeline DAG from configuration and a step registry.

    Resolves each step name in *config.steps* against the registry dict,
    collecting the corresponding :class:`PipelineStep` implementations
    into an ordered :class:`PipelineDAG`.

    Args:
        config: Pipeline configuration specifying step names and behaviour.
        registry: Mapping of step names to PipelineStep implementations.
        bus: Optional event bus for publishing step events.
        ledger: Optional ledger for recording step executions.

    Returns:
        A fully constructed :class:`PipelineDAG`.

    Raises:
        ValueError: If a step name in the config is not found in the registry.
    """
    steps: list[PipelineStep] = []
    for step_name in config.steps:
        if step_name not in registry:
            raise ValueError(
                f"Pipeline step '{step_name}' not found in registry. "
                f"Available steps: {sorted(registry.keys())}"
            )
        steps.append(registry[step_name])
    return PipelineDAG(steps=steps, bus=bus, ledger=ledger)
