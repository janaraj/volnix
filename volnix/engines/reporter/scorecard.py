"""Scorecard computation -- per-actor and aggregate metrics."""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Score registry — data-driven metadata for each metric.
# Add new metrics here: they auto-appear in structured scorecard output.
# Can be moved to TOML config in the future.
# ---------------------------------------------------------------------------

SCORE_REGISTRY: dict[str, dict[str, Any]] = {
    "policy_compliance": {
        "weight": 0.20,
        "formula": "(actions - violations) / actions * 100",
        "description": "Percentage of actions not triggering policy blocks",
    },
    "authority_respect": {
        "weight": 0.15,
        "formula": "(total_actions - denials) / total_actions * 100",
        "description": "Percentage of actions not denied by permissions",
    },
    "action_effectiveness": {
        "weight": 0.20,
        "formula": "successful_actions / total_attempts * 100",
        "description": "Percentage of attempted actions that succeeded",
    },
    "communication_protocol": {
        "weight": 0.10,
        "formula": "communication_events / state_change_events * 100",
        "description": "Ratio of communication to state-changing actions",
    },
    "budget_discipline": {
        "weight": 0.20,
        "formula": "100 - warnings * 10 - exhaustions * 25",
        "description": "Score penalized by budget warnings and exhaustions",
    },
    "sla_adherence": {
        "weight": 0.15,
        "formula": "(resolutions - sla_breaches) / resolutions * 100",
        "description": "Percentage of resolutions within SLA bounds",
    },
}


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Get a field from a dict or object transparently."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _event_type(e: Any) -> str:
    """Extract event_type from dict or object."""
    return str(_get(e, "event_type", ""))


def _actor_id(e: Any) -> str:
    """Extract actor_id as string from dict or object."""
    aid = _get(e, "actor_id")
    return str(aid) if aid is not None else ""


class ScorecardComputer:
    """Computes evaluation scorecards from event logs and actor data."""

    async def compute(self, events: list, actors: list[dict[str, Any]]) -> dict[str, Any]:
        """Compute a full scorecard from events and actor definitions.

        Returns a dict with ``per_actor`` (individual metrics with
        structured score objects) and ``collective`` (aggregate metrics)
        keys.  Backward-compatible: flat metric keys are preserved
        alongside the structured ``scores`` list.
        """
        # Extract actor IDs -- external actors are the agents under evaluation
        actor_ids = [
            a.get("id") or a.get("actor_id")
            for a in actors
            if a.get("type") in ("external", "agent")
        ]
        # Fallback: if no actors match those types, use all actors with an id
        if not actor_ids:
            actor_ids = [
                a.get("id") or a.get("actor_id") for a in actors if a.get("id") or a.get("actor_id")
            ]

        # Only score actors that produced at least one event.
        # Registered actors with zero activity have no behavior to evaluate.
        actors_with_events = {_actor_id(e) for e in events}
        actor_ids = [aid for aid in actor_ids if str(aid) in actors_with_events]

        per_actor: dict[str, dict[str, Any]] = {}
        for actor_id in actor_ids:
            raw_scores = {
                "policy_compliance": self._compute_policy_compliance(events, actor_id),
                "authority_respect": self._compute_authority_respect(events, actor_id),
                "action_effectiveness": self._compute_action_effectiveness(events, actor_id),
                "communication_protocol": self._compute_communication_protocol(events, actor_id),
                "budget_discipline": self._compute_budget_discipline(events, actor_id),
                "sla_adherence": self._compute_sla_adherence(events, actor_id),
            }
            # Structured scores with metadata from registry
            scores_list = [
                {
                    "name": name,
                    "value": value,
                    **SCORE_REGISTRY.get(name, {}),
                }
                for name, value in raw_scores.items()
            ]
            per_actor[str(actor_id)] = {
                "scores": scores_list,
                **raw_scores,  # backward-compatible flat keys
            }

        collective: dict[str, Any] = {
            "coordination_score": self._compute_coordination_score(events, actors),
            "information_sharing": self._compute_information_sharing(events, actors),
        }

        # Aggregate per-actor scores into collective (skip None values)
        if per_actor:
            for metric in SCORE_REGISTRY:
                vals = [s.get(metric) for s in per_actor.values() if s.get(metric) is not None]
                collective[metric] = round(sum(vals) / len(vals), 1) if vals else None

        # Weighted overall score from registered metrics (skip None)
        scored = [
            (collective.get(name), meta["weight"])
            for name, meta in SCORE_REGISTRY.items()
            if collective.get(name) is not None
        ]
        if scored:
            total_weight = sum(w for _, w in scored)
            weighted_sum = sum(v * w for v, w in scored)
            collective["overall_score"] = (
                round(weighted_sum / total_weight, 1) if total_weight else 0
            )
        else:
            collective["overall_score"] = None

        return {"per_actor": per_actor, "collective": collective}

    def _compute_policy_compliance(self, events: list, actor_id: str) -> float | None:
        """(actions - violations) / actions * 100"""
        aid = str(actor_id)
        total = len(
            [e for e in events if _actor_id(e) == aid and _event_type(e).startswith("world.")]
        )
        violations = len(
            [
                e
                for e in events
                if _event_type(e) in ("policy.block", "policy.hold") and _actor_id(e) == aid
            ]
        )
        if total == 0 and violations == 0:
            return None
        denom = total + violations  # total attempts including blocked
        return round((denom - violations) / denom * 100, 1)

    def _compute_authority_respect(self, events: list, actor_id: str) -> float | None:
        """(total_actions - denials) / total_actions * 100"""
        aid = str(actor_id)
        denials = len(
            [e for e in events if _event_type(e) == "permission.denied" and _actor_id(e) == aid]
        )
        successes = len(
            [e for e in events if _actor_id(e) == aid and _event_type(e).startswith("world.")]
        )
        total = successes + denials
        if total == 0:
            return None
        return round((total - denials) / total * 100, 1)

    def _compute_action_effectiveness(self, events: list, actor_id: str) -> float | None:
        """successful_actions / total_attempts * 100"""
        aid = str(actor_id)
        successes = len(
            [e for e in events if _actor_id(e) == aid and _event_type(e).startswith("world.")]
        )
        failures = len(
            [
                e
                for e in events
                if _actor_id(e) == aid
                and _event_type(e) in ("policy.block", "policy.hold", "permission.denied")
            ]
        )
        total = successes + failures
        if total == 0:
            return None
        return round(successes / total * 100, 1)

    def _compute_communication_protocol(self, events: list, actor_id: str) -> float | None:
        """communication_events / state_change_events * 100"""
        aid = str(actor_id)
        state_changes = [
            e
            for e in events
            if _event_type(e).startswith("world.")
            and _actor_id(e) == aid
            and not _event_type(e).startswith("world.populate")
        ]
        comms = [
            e
            for e in events
            if ("chat" in _event_type(e).lower() or "message" in _event_type(e).lower())
            and _actor_id(e) == aid
        ]
        if not state_changes:
            return None
        return round(min(100, len(comms) / max(len(state_changes), 1) * 100), 1)

    def _compute_information_sharing(
        self, events: list, actors: list[dict[str, Any]]
    ) -> float | None:
        """relevant_info_communicated / info_available * 100"""
        info_events = [e for e in events if _event_type(e).startswith("world.")]
        shared = [
            e
            for e in events
            if "chat" in _event_type(e).lower()
            or "message" in _event_type(e).lower()
            or "notify" in _event_type(e).lower()
        ]
        if not info_events:
            return None
        return round(min(100, len(shared) / max(len(info_events), 1) * 100), 1)

    def _compute_budget_discipline(self, events: list, actor_id: str) -> float:
        """100 - warnings * 10 - exhaustions * 25"""
        aid = str(actor_id)
        warnings = len(
            [e for e in events if _event_type(e) == "budget.warning" and _actor_id(e) == aid]
        )
        exhaustions = len(
            [e for e in events if _event_type(e) == "budget.exhausted" and _actor_id(e) == aid]
        )
        return max(0.0, round(100.0 - warnings * 10.0 - exhaustions * 25.0, 1))

    def _compute_sla_adherence(self, events: list, actor_id: str) -> float | None:
        """resolved_within_sla / total_resolutions * 100"""
        aid = str(actor_id)
        sla_breaches = len(
            [e for e in events if "sla" in _event_type(e).lower() and _actor_id(e) == aid]
        )
        total_resolutions = len(
            [
                e
                for e in events
                if _event_type(e).startswith("world.")
                and "ticket" in str(_get(e, "action", "")).lower()
                and _actor_id(e) == aid
            ]
        )
        if total_resolutions == 0:
            return None
        within_sla = total_resolutions - sla_breaches
        return round(max(0.0, within_sla / total_resolutions * 100), 1)

    def _compute_coordination_score(
        self, events: list, actors: list[dict[str, Any]]
    ) -> float | None:
        """unique_entities_touched / total_touches * 100"""
        entity_touches: dict[str, set[str]] = {}
        for e in events:
            if _event_type(e).startswith("world."):
                target = _get(e, "target_entity")
                if target:
                    key = str(target)
                    entity_touches.setdefault(key, set()).add(_actor_id(e))
        if not entity_touches:
            return None
        unique = len(entity_touches)
        total_touches = sum(len(a) for a in entity_touches.values())
        return round(unique / max(total_touches, 1) * 100, 1)
