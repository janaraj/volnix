"""Runtime governance pipeline for the Volnix framework.

Provides the DAG-based pipeline executor, base step class, configuration-
driven pipeline builder, and side-effect processing.

Re-exports the primary public API surface::

    from volnix.pipeline import PipelineDAG, BasePipelineStep, build_pipeline_from_config
"""

from volnix.pipeline.builder import build_pipeline_from_config
from volnix.pipeline.config import PipelineConfig
from volnix.pipeline.dag import PipelineDAG
from volnix.pipeline.side_effects import SideEffectProcessor
from volnix.pipeline.step import BasePipelineStep

__all__ = [
    "BasePipelineStep",
    "PipelineConfig",
    "PipelineDAG",
    "SideEffectProcessor",
    "build_pipeline_from_config",
]
