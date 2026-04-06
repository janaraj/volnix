"""Counterfactual differ -- compares multiple simulation runs."""

from __future__ import annotations

from typing import Any

from volnix.core import StateEngineProtocol


class CounterfactualDiffer:
    """Compares multiple simulation runs to highlight differences.

    Accepts pre-computed report dicts (scorecards, event logs, entity states)
    and produces a structured side-by-side comparison.
    """

    def __init__(self, scorecard_computer: Any = None) -> None:
        self._scorecard_computer = scorecard_computer

    async def compare(self, run_ids: list[str], state: StateEngineProtocol) -> dict[str, Any]:
        """Compare multiple runs and return a structured diff.

        For now, compares two report dicts rather than querying separate runs.
        Each run_id maps to pre-computed data in the state engine.
        """
        if len(run_ids) < 2:
            return {"error": "Need at least 2 runs to compare", "runs": run_ids}

        # Gather timelines for each run
        timelines: list[list[Any]] = []
        scorecards: list[dict[str, Any]] = []

        for run_id in run_ids:
            # Get timeline for the run (use full timeline as runs share state engine)
            timeline = await state.get_timeline()
            timelines.append(timeline)

            # Compute scorecard if we have a scorecard computer
            if self._scorecard_computer:
                sc = await self._scorecard_computer.compute(timeline, [])
                scorecards.append(sc)
            else:
                scorecards.append({})

        result: dict[str, Any] = {
            "runs": run_ids,
            "score_diff": self._diff_scores(scorecards),
            "event_diff": self._diff_events(timelines),
        }

        return result

    def _diff_scores(self, scorecards: list[dict[str, Any]]) -> dict[str, Any]:
        """Diff scorecard metrics across runs.

        Returns a metric-by-metric comparison showing the value in each
        run and the delta between them.
        """
        if len(scorecards) < 2:
            return {}

        diff: dict[str, Any] = {}

        # Compare collective scores
        for i, sc in enumerate(scorecards):
            collective = sc.get("collective", {})
            for metric, value in collective.items():
                if metric not in diff:
                    diff[metric] = {"values": [], "delta": 0.0}
                diff[metric]["values"].append(value)

        # Compute deltas (last - first)
        for metric, data in diff.items():
            values = data["values"]
            if (
                len(values) >= 2
                and isinstance(values[0], (int, float))
                and isinstance(values[-1], (int, float))
            ):
                data["delta"] = round(values[-1] - values[0], 1)

        return diff

    def _diff_events(self, event_logs: list[list[Any]]) -> dict[str, Any]:
        """Diff event logs across runs.

        Returns event count comparisons and type-level breakdowns.
        """
        diff: dict[str, Any] = {
            "counts": [],
            "by_type": {},
        }

        for log in event_logs:
            diff["counts"].append(len(log))

            # Count by event type
            type_counts: dict[str, int] = {}
            for event in log:
                et = event.event_type
                type_counts[et] = type_counts.get(et, 0) + 1

            for et, count in type_counts.items():
                if et not in diff["by_type"]:
                    diff["by_type"][et] = {"values": []}
                diff["by_type"][et]["values"].append(count)

        return diff

    def _diff_entity_states(self, states: list[dict[str, Any]]) -> dict[str, Any]:
        """Diff final entity states across runs.

        Returns a comparison of entity counts and field-level differences.
        """
        if len(states) < 2:
            return {}

        diff: dict[str, Any] = {
            "entity_counts": [],
            "changed_entities": [],
        }

        for state_dict in states:
            entity_count = sum(len(v) if isinstance(v, list) else 1 for v in state_dict.values())
            diff["entity_counts"].append(entity_count)

        # Find entities that differ between runs
        if len(states) >= 2:
            all_keys = set(states[0].keys()) | set(states[1].keys())
            for key in all_keys:
                v0 = states[0].get(key)
                v1 = states[1].get(key)
                if v0 != v1:
                    diff["changed_entities"].append(
                        {
                            "entity": key,
                            "run_0": v0,
                            "run_1": v1,
                        }
                    )

        return diff
