"""World -> Agent observation.

Analyzes how the agent handled challenges the world presented:
threats, bad data, service failures, ambiguous situations, boundary tests.
"""
from __future__ import annotations

import enum
from typing import Any

from terrarium.core.types import ActorId, EventId


class ChallengeResponse(enum.StrEnum):
    NOTICED = "noticed"                         # Agent detected and handled correctly
    RESISTED = "resisted"                       # Agent resisted manipulation/threat
    RETRIED = "retried"                         # Agent retried after failure
    CLARIFIED = "clarified"                     # Agent asked for clarification
    ADAPTED = "adapted"                         # Agent found alternative approach
    IGNORED = "ignored"                         # Agent ignored the challenge (neutral)
    PARTIALLY_FOLLOWED = "partially_followed"   # Agent partially fell for it
    FAILED = "failed"                           # Agent failed to handle correctly


class WorldChallengeEntry:
    # (BaseModel: turn, challenge_type, description, agent_response: ChallengeResponse, details)
    ...


class WorldChallengeAnalyzer:
    def __init__(self, state: Any = None) -> None: ...

    async def analyze(
        self, events: list, actor_id: ActorId, conditions: Any
    ) -> list[WorldChallengeEntry]:
        """Analyze how an agent handled world challenges."""
        ...

    async def analyze_threat_responses(self, events: list, actor_id: ActorId) -> list[dict]: ...
    async def analyze_data_quality_responses(self, events: list, actor_id: ActorId) -> list[dict]: ...
    async def analyze_failure_responses(self, events: list, actor_id: ActorId) -> list[dict]: ...
    async def analyze_ambiguity_responses(self, events: list, actor_id: ActorId) -> list[dict]: ...
