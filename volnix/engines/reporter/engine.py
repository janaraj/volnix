"""Report generator engine implementation.

Produces scorecards, capability gap logs, causal traces, counterfactual
diffs, and comprehensive reports for evaluation runs.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from volnix.core import BaseEngine, Event, EventId, WorldId

logger = logging.getLogger(__name__)


class ReportGeneratorEngine(BaseEngine):
    """Report generation engine for evaluation diagnostics.

    Orchestrates sub-components (ScorecardComputer, GapAnalyzer,
    CausalTraceRenderer, CounterfactualDiffer, WorldChallengeAnalyzer,
    AgentBoundaryAnalyzer) to produce structured reports.
    """

    engine_name: ClassVar[str] = "reporter"
    subscriptions: ClassVar[list[str]] = []  # reports generated on-demand, not event-driven
    dependencies: ClassVar[list[str]] = ["state"]

    def __init__(self) -> None:
        super().__init__()
        self._ledger: Any = None
        self._scorecard: Any = None
        self._gap_analyzer: Any = None
        self._causal_renderer: Any = None
        self._differ: Any = None
        self._challenge_analyzer: Any = None
        self._boundary_analyzer: Any = None
        self._trace_builder: Any = None

    # -- BaseEngine hook -------------------------------------------------------

    async def _on_initialize(self) -> None:
        """Create sub-components for report generation."""
        from volnix.engines.reporter.agent_boundaries import AgentBoundaryAnalyzer
        from volnix.engines.reporter.capability_gaps import GapAnalyzer
        from volnix.engines.reporter.causal_trace import CausalTraceRenderer
        from volnix.engines.reporter.diff import CounterfactualDiffer
        from volnix.engines.reporter.scorecard import ScorecardComputer
        from volnix.engines.reporter.world_challenges import WorldChallengeAnalyzer

        self._scorecard = ScorecardComputer()

        from volnix.engines.reporter.decision_trace import DecisionTraceBuilder

        self._trace_builder = DecisionTraceBuilder()
        self._gap_analyzer = GapAnalyzer()
        self._causal_renderer = CausalTraceRenderer()
        self._differ = CounterfactualDiffer(scorecard_computer=self._scorecard)
        self._challenge_analyzer = WorldChallengeAnalyzer()
        self._boundary_analyzer = AgentBoundaryAnalyzer()

        from volnix.engines.reporter.governance_report import GovernanceReportGenerator

        self._governance_report = GovernanceReportGenerator(
            scorecard_computer=self._scorecard,
            gap_analyzer=self._gap_analyzer,
            challenge_analyzer=self._challenge_analyzer,
            boundary_analyzer=self._boundary_analyzer,
            conditions=self._config.get("_conditions"),
        )

        logger.info("ReportGeneratorEngine initialized with all sub-components")

    async def _handle_event(self, event: Event) -> None:
        """Handle an inbound event from the bus.

        The reporter is passive -- it does not react to individual events.
        Reports are generated on demand via the generate_* methods.
        """
        pass

    # -- Helper: get state engine and timeline ---------------------------------

    def _get_state_engine(self) -> Any:
        """Get the state engine from dependencies."""
        return self._dependencies.get("state")

    async def _get_timeline(self) -> list[dict[str, Any]]:
        """Get ALL events from bus as raw dicts (preserving subclass fields).

        Uses bus persistence directly (not ``bus.replay()``) because replay
        deserializes to base ``Event``, discarding ``WorldEvent`` fields
        like ``actor_id`` and ``response_body``.
        """
        bus = self._dependencies.get("bus")
        if bus is not None:
            persistence = getattr(bus, "_persistence", None)
            if persistence:
                return await persistence.query_raw()
        # Fallback to state engine timeline (returns typed objects)
        state = self._get_state_engine()
        if state is None:
            return []
        return await state.get_timeline()

    def _get_actors(self) -> list[dict[str, Any]]:
        """Get actor definitions from config, excluding NPCs (type=human)."""
        actor_registry = self._config.get("_actor_registry")
        if actor_registry is None:
            return []
        if hasattr(actor_registry, "list_actors"):
            actors = actor_registry.list_actors()
            return [
                {
                    "id": str(a.id),
                    "type": str(a.type),
                    "role": getattr(a, "role", ""),
                    "budget": getattr(a, "budget", None) or {},
                }
                for a in actors
                if str(a.type) != "human"
            ]
        return []

    # -- Reporter operations ---------------------------------------------------

    async def generate_scorecard(
        self,
        world_id: WorldId = None,
        actors: list[dict[str, Any]] | None = None,
        events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Generate a summary scorecard for a world.

        Args:
            world_id: Optional world identifier (unused, kept for API compat).
            actors: Explicit actor list. If ``None``, reads from registry
                and supplements with actors discovered from events.
            events: Pre-filtered event list. If ``None``, reads all from bus.
                Pass run-scoped events to avoid cross-run contamination.
        """
        if events is None:
            events = await self._get_timeline()
        if actors is None:
            # Derive actors from events only — the live registry may have
            # actors from a different run (e.g., animator NPCs from a new
            # simulation that has nothing to do with the completed run).
            internal = {
                "world_compiler",
                "animator",
                "system",
                "policy",
                "budget",
                "state",
                "permission",
                "responder",
            }
            seen: set[str] = set()
            actors = []
            for evt in events:
                aid = (
                    evt.get("actor_id") if isinstance(evt, dict) else getattr(evt, "actor_id", None)
                )
                if aid and str(aid) not in seen and str(aid) not in internal:
                    actors.append({"id": str(aid), "type": "agent", "role": str(aid)})
                    seen.add(str(aid))

        return await self._scorecard.compute(events, actors)

    async def generate_gap_log(
        self,
        world_id: WorldId = None,
    ) -> list[dict[str, Any]]:
        """Generate a log of all capability gaps encountered."""
        events = await self._get_timeline()
        return await self._gap_analyzer.analyze(events)

    async def generate_causal_trace(self, event_id: EventId) -> dict[str, Any]:
        """Generate a causal trace rooted at the given event."""
        state = self._get_state_engine()
        if state is None:
            return {"error": "State engine not available", "root_event": str(event_id)}
        return await self._causal_renderer.render(event_id, state)

    async def generate_diff(self, run_ids: list[str]) -> dict[str, Any]:
        """Generate a counterfactual diff between multiple runs."""
        state = self._get_state_engine()
        if state is None:
            return {"error": "State engine not available"}
        return await self._differ.compare(run_ids, state)

    async def generate_full_report(
        self,
        world_id: WorldId = None,
        actors: list[dict[str, Any]] | None = None,
        events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Generate a comprehensive report combining all diagnostics.

        Args:
            world_id: Optional world identifier.
            actors: Explicit actor list. If ``None``, reads from registry.
            events: Pre-filtered event list. If ``None``, reads all from bus.
        """
        if events is None:
            events = await self._get_timeline()
        scorecard = await self.generate_scorecard(world_id, actors=actors, events=events)
        gap_log = await self.generate_gap_log(world_id)
        gap_summary = await self._gap_analyzer.get_gap_summary(events)
        condition_report = await self.generate_condition_report(
            world_id,
            actors=actors,
        )
        decision_trace = await self.generate_decision_trace(
            events=events, actors=actors
        )

        return {
            "scorecard": scorecard,
            "gap_log": gap_log,
            "gap_summary": gap_summary,
            "condition_report": condition_report,
            "decision_trace": decision_trace,
        }

    async def generate_condition_report(
        self,
        world_id: WorldId = None,
        actors: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Generate two-direction observation report.

        Direction 1 (world -> agent): How the agent handled world challenges
        (threats, bad data, failures, ambiguity).

        Direction 2 (agent -> world): How the agent's own behavior tested
        world boundaries (data access, information handling, authority, probing).
        """
        events = await self._get_timeline()
        if actors is None:
            actors = self._get_actors()
        conditions = self._config.get("_conditions")

        world_to_agent: dict[str, Any] = {}
        agent_to_world: dict[str, Any] = {}

        for actor in actors:
            actor_id = actor.get("id", "")
            if not actor_id:
                continue

            challenges = await self._challenge_analyzer.analyze(events, actor_id, conditions)
            world_to_agent[actor_id] = [
                {
                    "turn": c.turn,
                    "challenge_type": c.challenge_type,
                    "description": c.description,
                    "agent_response": c.agent_response.value,
                    "details": c.details,
                }
                for c in challenges
            ]

            boundaries = await self._boundary_analyzer.analyze(events, actor_id)
            agent_to_world[actor_id] = [
                {
                    "turn": b.turn,
                    "category": b.category.value,
                    "description": b.description,
                    "severity": b.severity,
                    "passed": b.passed,
                }
                for b in boundaries
            ]

        # If no actors registered, still return structure with empty data
        if not actors:
            world_to_agent = {}
            agent_to_world = {}

        return {
            "world_to_agent": world_to_agent,
            "agent_to_world": agent_to_world,
        }

    async def generate_governance_report(
        self,
        world_id: WorldId = None,
        actors: list[dict[str, Any]] | None = None,
        events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Generate Mode 1 governance report for external agent testing.

        Packages scorecard + gaps + challenges + boundaries into one
        structured artifact.

        Args:
            world_id: Optional world identifier (unused, kept for API compat).
            actors: Explicit actor list. If ``None``, reads from registry.
            events: Pre-filtered event list. If ``None``, reads all from bus.
                Pass run-scoped events to avoid cross-run contamination.
        """
        if events is None:
            events = await self._get_timeline()
        if actors is None:
            actors = self._get_actors()
        return await self._governance_report.generate(events, actors)

    async def generate_decision_trace(
        self,
        events: list[dict[str, Any]] | None = None,
        actors: list[dict[str, Any]] | None = None,
        game_result: dict[str, Any] | None = None,
        interpreter: Any | None = None,
    ) -> dict[str, Any]:
        """Generate a structured decision trace for the run.

        Builds per-activation trace: who acted, what tools were called,
        governance decisions, committed effects, world response, information
        coverage metrics, and governance aggregate counts.

        Auto-extracts game_result from events if not provided and a
        "game.terminated" event is present.

        Args:
            events: Raw event dicts. If None, reads all from bus.
            actors: Actor list. If None, reads from registry.
            game_result: Game outcome dict. If None, extracted from events.
            interpreter: Optional DomainInterpreter for narrative strings.
        """
        if events is None:
            events = await self._get_timeline()
        if actors is None:
            actors = self._get_actors()
        state = self._get_state_engine()
        return await self._trace_builder.build(
            events=events,
            actors=actors,
            state_engine=state,
            game_result=game_result,
            interpreter=interpreter,
        )
