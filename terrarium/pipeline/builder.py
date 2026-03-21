"""Pipeline builder for the Terrarium framework.

Constructs a :class:`~terrarium.pipeline.dag.PipelineDAG` from
configuration and the engine registry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from terrarium.pipeline.config import PipelineConfig
    from terrarium.pipeline.dag import PipelineDAG
    from terrarium.registry.registry import EngineRegistry


def build_pipeline_from_config(config: PipelineConfig, registry: EngineRegistry) -> PipelineDAG:
    """Build a pipeline DAG from configuration and registered engines.

    Resolves each step name in *config.steps* against the engine registry,
    collecting the corresponding :class:`PipelineStep` implementations
    into an ordered :class:`PipelineDAG`.

    Args:
        config: Pipeline configuration specifying step names and behaviour.
        registry: The engine registry used to resolve step names.

    Returns:
        A fully constructed :class:`PipelineDAG`.
    """
    ...
