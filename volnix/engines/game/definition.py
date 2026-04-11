"""Game definition models — frozen Pydantic models for game configuration.

Parsed from the ``game:`` section of blueprint YAML.

All game config is event-driven: :class:`FlowConfig` drives wall-clock
and event-count limits, :class:`GameEntitiesConfig` declares the deals
and player briefs the orchestrator materializes into state, and
:class:`GameDefinition` is the top-level container.

Mutable runtime state lives in :class:`GameState` (held by the
orchestrator) and :class:`PlayerScore` (held per-player).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from volnix.core.types import ActorId

# ---------------------------------------------------------------------------
# New event-driven models (Cycle B canonical)
# ---------------------------------------------------------------------------

ScoringMode = Literal["behavioral", "competitive"]
FlowType = Literal["event_driven"]  # room for "tick_driven" in a future cycle
ActivationMode = Literal["serial", "parallel"]


class FlowConfig(BaseModel, frozen=True):
    """Event-driven flow configuration.

    - max_wall_clock_seconds: hard wall-clock budget for the whole game
    - max_events: hard cap on committed game tool events
    - stalemate_timeout_seconds: silence timeout (no game events)
    - activation_mode: 'serial' (turn-based: orchestrator activates next
      player on each commit) or 'parallel' (all players active concurrently
      from kickstart)
    - first_mover: role or actor_id of the player to kickstart. Required
      for activation_mode='serial'. Ignored for 'parallel'.
    - bonus_per_event: competitive-mode efficiency bonus per event saved.
      ``efficiency_bonus = max(0, (max_events - event_num) * bonus_per_event)``
    - reactivity_window_events: BehavioralScorer counts a player move as
      "reacting to an animator event" if it happens within this many
      committed events of the last animator/environment event. Tunable
      per scenario (tick-heavy worlds may need a wider window).
    - state_summary_entity_types: list of entity types the orchestrator
      queries when building the re-activation state_summary. Defaults to
      ``negotiation_deal`` (the only game-state entity the current
      negotiation game type writes). New game types (auction, debate)
      will add their own entity types here.
    """

    type: FlowType = "event_driven"
    max_wall_clock_seconds: int = 900
    max_events: int = 100
    stalemate_timeout_seconds: int = 180
    activation_mode: ActivationMode = "serial"
    first_mover: str | None = None
    bonus_per_event: float = 0.14
    reactivity_window_events: int = 5
    state_summary_entity_types: list[str] = Field(default_factory=lambda: ["negotiation_deal"])

    @field_validator(
        "max_wall_clock_seconds",
        "max_events",
        "stalemate_timeout_seconds",
        "reactivity_window_events",
    )
    @classmethod
    def _positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"must be > 0 (got {v})")
        return v


class DealDecl(BaseModel, frozen=True):
    """Blueprint-declared negotiation_deal entity shape.

    Materialized at compile time by
    ``volnix/engines/world_compiler/engine.py::_materialize_game_entities``
    directly into state via ``state_engine.create_entity``.
    """

    id: str
    title: str = ""
    parties: list[str] = Field(default_factory=list)  # list of actor_role strings
    status: Literal["open", "proposed", "countered", "accepted", "rejected"] = "open"
    terms: dict[str, Any] = Field(default_factory=dict)
    terms_template: dict[str, Any] = Field(default_factory=dict)
    consent_rule: Literal["unanimous", "majority"] = "unanimous"  # P7-ready


class PlayerBriefDecl(BaseModel, frozen=True):
    """Blueprint-declared game_player_brief.

    Materialized at compile time as BOTH:
    (a) a notion ``page`` entity with ``owner_role`` set so visibility rules
        filter it so only the owning player sees it via ``notion.pages.retrieve``;
    (b) a ``game_player_brief`` queryable entity so the orchestrator and
        behavioral scorer can find it by actor without going through notion.
    """

    actor_role: str  # matches role in agents_*.yaml
    deal_id: str
    brief_content: str  # rendered into notion page body
    mission: str = ""  # short one-liner
    prohibited_actions: list[str] = Field(default_factory=list)


class TargetTermsDecl(BaseModel, frozen=True):
    """Blueprint-declared negotiation_target_terms (competitive mode only).

    Only materialized when ``GameDefinition.scoring_mode == "competitive"``.
    Used exclusively by :class:`CompetitiveScorer` to compute deal scores
    and BATNA settlements. Never exposed to a player's LLM (no visibility
    rule; no service action retrieves it).
    """

    actor_role: str
    deal_id: str
    ideal_terms: dict[str, float] = Field(default_factory=dict)
    term_weights: dict[str, float] = Field(default_factory=dict)
    term_ranges: dict[str, list[float]] = Field(default_factory=dict)  # [lo, hi]
    batna_score: float = 0.0


class GameEntitiesConfig(BaseModel, frozen=True):
    """Structured game entities declared in the blueprint.

    Materialized at compile time by the world compiler's post-seed hook.
    """

    deals: list[DealDecl] = Field(default_factory=list)
    player_briefs: list[PlayerBriefDecl] = Field(default_factory=list)
    target_terms: list[TargetTermsDecl] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Scoring + win conditions (new WinCondition shape with type literals)
# ---------------------------------------------------------------------------


class ScoringMetric(BaseModel, frozen=True):
    """A single scoring metric definition."""

    name: str
    source: str = "state"
    entity_type: str = ""
    field: str = ""
    event_type: str = ""
    aggregation: str = "last"
    weight: float = 1.0


class ScoringConfig(BaseModel, frozen=True):
    """Scoring configuration."""

    metrics: list[ScoringMetric] = Field(default_factory=list)
    ranking: str = "descending"


class WinCondition(BaseModel, frozen=True):
    """A win/loss condition declared in the blueprint.

    Supported types (see ``volnix/engines/game/win_conditions.py``):

    - ``deal_closed``: any deal reaches status=accepted (natural win)
    - ``deal_rejected``: any deal reaches status=rejected (natural win)
    - ``stalemate_timeout``: orchestrator stalemate timer fires
    - ``wall_clock_elapsed``: orchestrator wall-clock timer fires
    - ``max_events_exceeded``: orchestrator event counter hits max_events
    - ``all_budgets_exhausted``: every game player's world_actions budget done
    - ``score_threshold``: competitive mode only; filtered out in behavioral
    - ``elimination``: per-player elimination below a metric threshold
    """

    type: str = "deal_closed"
    metric: str = ""
    threshold: float = 0.0
    below: bool = False
    type_config: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Top-level GameDefinition (event-driven)
# ---------------------------------------------------------------------------


class GameDefinition(BaseModel, frozen=True):
    """Complete game configuration from blueprint YAML.

    Event-driven fields:

    - ``flow``: :class:`FlowConfig` — event-driven flow settings
      (wall-clock budget, max events, activation mode, reactivity window)
    - ``entities``: :class:`GameEntitiesConfig` — structured entity
      declarations (deals, player briefs, optional target terms)
    - ``scoring_mode``: ``"behavioral"`` (default) or ``"competitive"``
    - ``scoring`` + ``win_conditions``: metric + termination rules
    """

    enabled: bool = False
    mode: str = "competition"
    scoring_mode: ScoringMode = "behavioral"
    type_config: dict[str, Any] = Field(default_factory=dict)

    # Event-driven fields
    flow: FlowConfig = Field(default_factory=FlowConfig)
    entities: GameEntitiesConfig = Field(default_factory=GameEntitiesConfig)

    # Scoring + win conditions
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    win_conditions: list[WinCondition] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Runtime state models (mutable)
# ---------------------------------------------------------------------------


class PlayerScore(BaseModel):
    """Mutable per-player score tracking.

    - ``metrics``: dict[str, float] — metric values (updated by scorers)
    - ``behavior_metrics``: dict[str, float] — populated by BehavioralScorer
      (query_quality, reactivity, compliance, ...) and presented in the
      GameResult when ``scoring_mode == "behavioral"``.
    - ``total_score``: weighted total (updated by CompetitiveScorer)
    - ``eliminated`` / ``eliminated_at_event``: elimination tracking
      (event counter at elimination time)
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    actor_id: ActorId
    metrics: dict[str, float] = Field(default_factory=dict)
    behavior_metrics: dict[str, float] = Field(default_factory=dict)
    total_score: float = 0.0
    eliminated: bool = False
    eliminated_at_event: int | None = None

    def get_metric(self, name: str) -> float:
        """Return the value of a named metric, defaulting to 0.0."""
        return self.metrics.get(name, 0.0)

    def update_metrics(self, new_metrics: dict[str, float], weights: dict[str, float]) -> None:
        """Update metrics and recompute the weighted total score."""
        self.metrics.update(new_metrics)
        self.total_score = sum(
            self.metrics.get(name, 0.0) * weights.get(name, 1.0) for name in self.metrics
        )


class GameState(BaseModel):
    """Mutable in-memory game lifecycle state, held by GameOrchestrator.

    - ``event_counter``: total committed game tool events
    - ``started_at``: wall clock at game start
    - ``terminated``: whether the game has ended
    - ``stalemate_deadline_tick``: monotonic deadline for stalemate timer
    """

    event_counter: int = 0
    started_at: datetime | None = None
    terminated: bool = False
    stalemate_deadline_tick: float = 0.0


class WinResult(BaseModel, frozen=True):
    """Result of a win condition evaluation."""

    winner: ActorId | None = None
    reason: str = ""
    final_standings: list[dict[str, Any]] = Field(default_factory=list)
    behavior_scores: dict[str, dict[str, float]] = Field(default_factory=dict)


class GameResult(BaseModel, frozen=True):
    """Final game result.

    Behavioral mode: ``winner`` is None, ``behavior_scores`` populated,
    ``final_standings`` empty. Competitive mode: ``winner`` set,
    ``final_standings`` ordered, ``behavior_scores`` empty.
    """

    winner: ActorId | None = None
    reason: str = ""
    total_events: int = 0
    wall_clock_seconds: float = 0.0
    final_standings: list[dict[str, Any]] = Field(default_factory=list)
    behavior_scores: dict[str, dict[str, float]] = Field(default_factory=dict)
    game_mode: str = "competition"
    scoring_mode: ScoringMode = "behavioral"
