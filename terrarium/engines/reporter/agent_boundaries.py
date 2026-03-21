"""Agent -> World observation.

Analyzes the agent's own behavior -- did it respect boundaries,
leak data, probe for vulnerabilities, or exhibit unintended behavior?
"""
from __future__ import annotations

import enum
from typing import Any

from terrarium.core.types import ActorId


class BoundaryCategory(enum.StrEnum):
    DATA_ACCESS = "data_access"
    INFORMATION_HANDLING = "information_handling"
    AUTHORITY = "authority"
    BOUNDARY_PROBING = "boundary_probing"
    UNINTENDED_BEHAVIOR = "unintended_behavior"


class BoundaryFinding:
    # (BaseModel: turn, category: BoundaryCategory, description, severity, passed: bool)
    ...


class AgentBoundaryAnalyzer:
    def __init__(self, state: Any = None) -> None: ...

    async def analyze(self, events: list, actor_id: ActorId) -> list[BoundaryFinding]: ...
    async def analyze_data_access(self, events: list, actor_id: ActorId) -> list[dict]: ...
    async def analyze_information_handling(self, events: list, actor_id: ActorId) -> list[dict]: ...
    async def analyze_authority(self, events: list, actor_id: ActorId) -> list[dict]: ...
    async def analyze_boundary_probing(self, events: list, actor_id: ActorId) -> list[dict]: ...
    async def analyze_unintended_behavior(self, events: list, actor_id: ActorId) -> list[dict]: ...
