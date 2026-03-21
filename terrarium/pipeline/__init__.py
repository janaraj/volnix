"""Runtime governance pipeline for the Terrarium framework.

Provides the DAG-based pipeline executor, base step class, configuration-
driven pipeline builder, and side-effect processing.

Re-exports the primary public API surface::

    from terrarium.pipeline import PipelineDAG, BasePipelineStep, build_pipeline_from_config
"""

from terrarium.pipeline.builder import build_pipeline_from_config
from terrarium.pipeline.config import PipelineConfig
from terrarium.pipeline.dag import PipelineDAG
from terrarium.pipeline.side_effects import SideEffectProcessor
from terrarium.pipeline.step import BasePipelineStep

__all__ = [
    "BasePipelineStep",
    "PipelineConfig",
    "PipelineDAG",
    "SideEffectProcessor",
    "build_pipeline_from_config",
]
