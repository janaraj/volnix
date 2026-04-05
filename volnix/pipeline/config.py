"""Pipeline-specific configuration model.

Defines the Pydantic model for pipeline configuration, specifying step
ordering, retry limits, timeouts, and side-effect depth bounds.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PipelineConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    """Configuration for the governance pipeline.

    Attributes:
        steps: Ordered list of step names to execute.
        max_retries: Maximum retries per step on transient failure.
        timeout_per_step_seconds: Per-step execution timeout in seconds.
        side_effect_max_depth: Maximum recursion depth for side-effect chains.
    """

    steps: list[str] = [
        "permission",
        "policy",
        "budget",
        "capability",
        "responder",
        "validation",
        "commit",
    ]
    max_retries: int = 0
    timeout_per_step_seconds: float = 30.0
    side_effect_max_depth: int = 10
