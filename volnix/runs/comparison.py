"""Cross-run comparison utilities.

The :class:`RunComparator` provides methods for comparing scores,
events, and entity states across multiple evaluation runs.
"""

from __future__ import annotations

from typing import Any

from volnix.core.types import RunId
from volnix.runs.artifacts import ArtifactStore


class RunComparator:
    """Compares metrics and state across multiple evaluation runs."""

    def __init__(self, artifact_store: ArtifactStore) -> None:
        self._artifact_store = artifact_store

    async def compare(self, run_ids: list[RunId]) -> dict[str, Any]:
        """Produce a comprehensive comparison across the given runs.

        Args:
            run_ids: The runs to compare.

        Returns:
            A comparison dict with scores, events, and state sections.
        """
        scores = await self.compare_scores(run_ids)
        events = await self.compare_events(run_ids)
        entity_states = await self.compare_entity_states(run_ids)

        # Build labels from metadata
        labels: dict[str, str] = {}
        for run_id in run_ids:
            metadata = await self._artifact_store.load_artifact(run_id, "metadata")
            if metadata and isinstance(metadata, dict):
                labels[str(run_id)] = metadata.get("tag", str(run_id))
            else:
                labels[str(run_id)] = str(run_id)

        # Compute divergence points and include full run metadata
        divergence_points = await self.compute_divergence_points(run_ids)
        runs_metadata: list[dict[str, Any]] = []
        for rid in run_ids:
            meta = await self._artifact_store.load_artifact(rid, "metadata")
            if meta:
                runs_metadata.append(meta)

        return {
            "run_ids": [str(r) for r in run_ids],
            "labels": labels,
            "scores": scores,
            "events": events,
            "entity_states": entity_states,
            "divergence_points": divergence_points,
            "runs": runs_metadata,
        }

    async def compare_scores(self, run_ids: list[RunId]) -> dict[str, Any]:
        """Compare scorecard metrics across runs.

        Args:
            run_ids: The runs to compare.

        Returns:
            A dict mapping metric names to per-run values and deltas.
        """
        # Load all scorecards, extracting collective metrics
        scorecards: dict[str, dict[str, Any]] = {}
        for run_id in run_ids:
            card = await self._artifact_store.load_artifact(run_id, "scorecard")
            if isinstance(card, dict):
                # Scorecard format: {"per_actor": {...}, "collective": {...}}
                # Extract the collective metrics for comparison
                collective = card.get("collective")
                if isinstance(collective, dict):
                    scorecards[str(run_id)] = collective
                else:
                    # Fall back to top-level keys if no collective section
                    scorecards[str(run_id)] = card
            else:
                scorecards[str(run_id)] = {}

        # Collect all metric names across all runs
        all_metrics: set[str] = set()
        for card in scorecards.values():
            all_metrics.update(card.keys())

        # Build metric-by-metric comparison with deltas
        metrics: dict[str, dict[str, Any]] = {}
        for metric in sorted(all_metrics):
            values: dict[str, Any] = {}
            for run_id in run_ids:
                values[str(run_id)] = scorecards[str(run_id)].get(metric)
            metrics[metric] = {"values": values}

            # Compute deltas between consecutive runs
            if len(run_ids) >= 2:
                deltas: dict[str, float | None] = {}
                run_strs = [str(r) for r in run_ids]
                for i in range(1, len(run_strs)):
                    prev_val = values[run_strs[i - 1]]
                    curr_val = values[run_strs[i]]
                    if isinstance(prev_val, (int, float)) and isinstance(curr_val, (int, float)):
                        deltas[f"{run_strs[i - 1]}→{run_strs[i]}"] = curr_val - prev_val
                    else:
                        deltas[f"{run_strs[i - 1]}→{run_strs[i]}"] = None
                metrics[metric]["deltas"] = deltas

        return {"metrics": metrics}

    async def compare_events(self, run_ids: list[RunId]) -> dict[str, Any]:
        """Compare event distributions across runs.

        Args:
            run_ids: The runs to compare.

        Returns:
            A dict with event count breakdowns per run.
        """
        per_run: dict[str, dict[str, int]] = {}
        totals: dict[str, int] = {}

        for run_id in run_ids:
            events = await self._artifact_store.load_artifact(run_id, "event_log")
            if not isinstance(events, list):
                events = []

            type_counts: dict[str, int] = {}
            for event in events:
                if isinstance(event, dict):
                    event_type = event.get("event_type", "unknown")
                else:
                    event_type = "unknown"
                type_counts[event_type] = type_counts.get(event_type, 0) + 1

            per_run[str(run_id)] = type_counts
            totals[str(run_id)] = len(events)

        # Collect all event types
        all_types: set[str] = set()
        for counts in per_run.values():
            all_types.update(counts.keys())

        # Build the breakdown by event type
        by_type: dict[str, dict[str, int]] = {}
        for event_type in sorted(all_types):
            by_type[event_type] = {str(r): per_run[str(r)].get(event_type, 0) for r in run_ids}

        return {
            "totals": totals,
            "by_type": by_type,
        }

    async def compare_entity_states(self, run_ids: list[RunId]) -> dict[str, Any]:
        """Compare final entity states across runs.

        Args:
            run_ids: The runs to compare.

        Returns:
            A dict mapping entity types to per-run state summaries.
        """
        per_run: dict[str, dict[str, int]] = {}

        for run_id in run_ids:
            report = await self._artifact_store.load_artifact(run_id, "report")
            if not isinstance(report, dict):
                report = {}

            # Extract entity counts from the report
            entities = report.get("entities", report.get("entity_states", {}))
            entity_counts: dict[str, int] = {}

            if isinstance(entities, dict):
                for entity_type, data in entities.items():
                    if isinstance(data, list):
                        entity_counts[entity_type] = len(data)
                    elif isinstance(data, dict):
                        entity_counts[entity_type] = data.get("count", len(data))
                    elif isinstance(data, int):
                        entity_counts[entity_type] = data
            elif isinstance(entities, list):
                # Flat list of entities — group by type
                for entity in entities:
                    if isinstance(entity, dict):
                        etype = entity.get("entity_type", "unknown")
                        entity_counts[etype] = entity_counts.get(etype, 0) + 1

            per_run[str(run_id)] = entity_counts

        # Collect all entity types
        all_types: set[str] = set()
        for counts in per_run.values():
            all_types.update(counts.keys())

        # Build per-type comparison
        by_type: dict[str, dict[str, int]] = {}
        for entity_type in sorted(all_types):
            by_type[entity_type] = {str(r): per_run[str(r)].get(entity_type, 0) for r in run_ids}

        return {
            "by_type": by_type,
        }

    async def compute_divergence_points(
        self,
        run_ids: list[RunId],
    ) -> list[dict[str, Any]]:
        """Find ticks where runs diverge in their event signatures.

        Compares ``(event_type, actor_id, action)`` sets at each tick.
        A divergence point is a tick where these sets differ between runs.

        Args:
            run_ids: The runs to compare.

        Returns:
            A list of divergence point dicts, each with ``tick``, ``type``,
            and ``per_run`` keys.
        """
        logs: dict[str, list[dict[str, Any]]] = {}
        for rid in run_ids:
            events = await self._artifact_store.load_artifact(rid, "event_log")
            logs[str(rid)] = events if isinstance(events, list) else []

        def _group_by_tick(events: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
            grouped: dict[int, list[dict[str, Any]]] = {}
            for e in events:
                ts = e.get("timestamp")
                tick = ts.get("tick", 0) if isinstance(ts, dict) else 0
                grouped.setdefault(tick, []).append(e)
            return grouped

        tick_groups = {rid: _group_by_tick(evts) for rid, evts in logs.items()}
        all_ticks = sorted(set().union(*(g.keys() for g in tick_groups.values())))
        rid_list = [str(r) for r in run_ids]

        points: list[dict[str, Any]] = []
        for tick in all_ticks:
            sigs: dict[str, set[tuple[str, str, str]]] = {}
            for rid in rid_list:
                events_at_tick = tick_groups.get(rid, {}).get(tick, [])
                sigs[rid] = {
                    (
                        e.get("event_type", ""),
                        e.get("actor_id", ""),
                        e.get("action", ""),
                    )
                    for e in events_at_tick
                }

            frozen_sigs = [frozenset(s) for s in sigs.values()]
            if len(frozen_sigs) >= 2 and len(set(frozen_sigs)) > 1:
                points.append(
                    {
                        "tick": tick,
                        "type": "event_set_mismatch",
                        "per_run": {
                            rid: [
                                {"event_type": s[0], "actor_id": s[1], "action": s[2]}
                                for s in sig_set
                            ]
                            for rid, sig_set in sigs.items()
                        },
                    }
                )

        return points

    def format_comparison(self, comparison: dict[str, Any]) -> str:
        """Format a comparison dict as a human-readable string.

        Args:
            comparison: The comparison result from :meth:`compare`.

        Returns:
            A formatted multi-line string.
        """
        lines: list[str] = []
        run_ids = comparison.get("run_ids", [])
        labels = comparison.get("labels", {})

        # Header
        header_parts = ["Metric"]
        for rid in run_ids:
            label = labels.get(rid, rid)
            header_parts.append(label)
        if len(run_ids) >= 2:
            header_parts.append("Delta")

        col_width = max(16, *(len(p) + 2 for p in header_parts))
        header_line = "".join(p.ljust(col_width) for p in header_parts)
        separator = "-" * len(header_line)

        lines.append("=== Run Comparison ===")
        lines.append("")

        # Scores section
        scores = comparison.get("scores", {})
        metrics = scores.get("metrics", {})
        if metrics:
            lines.append("-- Scores --")
            lines.append(header_line)
            lines.append(separator)
            for metric, data in metrics.items():
                values = data.get("values", {})
                row_parts = [metric]
                for rid in run_ids:
                    val = values.get(rid)
                    row_parts.append(_format_value(val))
                deltas = data.get("deltas", {})
                if deltas:
                    # Show the last delta
                    delta_vals = list(deltas.values())
                    last_delta = delta_vals[-1] if delta_vals else None
                    if last_delta is not None:
                        sign = "+" if last_delta > 0 else ""
                        row_parts.append(f"{sign}{last_delta:.2f}")
                    else:
                        row_parts.append("-")
                lines.append("".join(p.ljust(col_width) for p in row_parts))
            lines.append("")

        # Events section
        events = comparison.get("events", {})
        totals = events.get("totals", {})
        by_type = events.get("by_type", {})
        if totals:
            lines.append("-- Events --")
            total_row = ["Total Events"]
            for rid in run_ids:
                total_row.append(str(totals.get(rid, 0)))
            lines.append("".join(p.ljust(col_width) for p in total_row))

            if by_type:
                for event_type, counts in by_type.items():
                    row = [f"  {event_type}"]
                    for rid in run_ids:
                        row.append(str(counts.get(rid, 0)))
                    lines.append("".join(p.ljust(col_width) for p in row))
            lines.append("")

        # Entity states section
        entity_states = comparison.get("entity_states", {})
        entity_by_type = entity_states.get("by_type", {})
        if entity_by_type:
            lines.append("-- Entity States --")
            for etype, counts in entity_by_type.items():
                row = [etype]
                for rid in run_ids:
                    row.append(str(counts.get(rid, 0)))
                lines.append("".join(p.ljust(col_width) for p in row))
            lines.append("")

        # Governance metrics section (from compare_governed_ungoverned)
        gov_metrics = comparison.get("governance_metrics", {})
        if gov_metrics:
            lines.append("-- Governance Metrics --")
            for gm_key, gm_data in gov_metrics.items():
                if isinstance(gm_data, dict):
                    row = [gm_key]
                    for rid in run_ids:
                        row.append(str(gm_data.get(rid, 0)))
                    lines.append("".join(p.ljust(col_width) for p in row))
                else:
                    lines.append(f"{gm_key}: {gm_data}")
            lines.append("")

        return "\n".join(lines)

    async def compare_governed_ungoverned(
        self, governed_run_id: RunId, ungoverned_run_id: RunId
    ) -> dict[str, Any]:
        """Compare the same world run in governed vs. ungoverned mode.

        Shows exactly where governance matters: which actions were blocked,
        which approvals were required, impact on task completion and quality.
        """
        # Start with a standard comparison
        base = await self.compare([governed_run_id, ungoverned_run_id])

        # Load event logs for both runs
        gov_events = await self._artifact_store.load_artifact(governed_run_id, "event_log")
        ungov_events = await self._artifact_store.load_artifact(ungoverned_run_id, "event_log")
        if not isinstance(gov_events, list):
            gov_events = []
        if not isinstance(ungov_events, list):
            ungov_events = []

        # Extract governance-specific metrics from both runs
        gov_id = str(governed_run_id)
        ungov_id = str(ungoverned_run_id)

        gov_metrics = _extract_governance_metrics(gov_events)
        ungov_metrics = _extract_governance_metrics(ungov_events)

        governance_metrics: dict[str, dict[str, Any]] = {
            "blocked_actions": {
                gov_id: gov_metrics["blocked"],
                ungov_id: ungov_metrics["blocked"],
            },
            "approval_requests": {
                gov_id: gov_metrics["approvals"],
                ungov_id: ungov_metrics["approvals"],
            },
            "budget_exceeded": {
                gov_id: gov_metrics["budget_exceeded"],
                ungov_id: ungov_metrics["budget_exceeded"],
            },
            "unauthorized_access": {
                gov_id: gov_metrics["unauthorized"],
                ungov_id: ungov_metrics["unauthorized"],
            },
            "total_actions": {
                gov_id: gov_metrics["total_actions"],
                ungov_id: ungov_metrics["total_actions"],
            },
            "policy_hits": {
                gov_id: gov_metrics["policy_hits"],
                ungov_id: ungov_metrics["policy_hits"],
            },
        }

        base["governance_metrics"] = governance_metrics
        base["governed_run_id"] = gov_id
        base["ungoverned_run_id"] = ungov_id

        return base


def _extract_governance_metrics(events: list[Any]) -> dict[str, int]:
    """Extract governance-related counts from a list of serialized events."""
    blocked = 0
    approvals = 0
    budget_exceeded = 0
    unauthorized = 0
    total_actions = 0
    policy_hits = 0

    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = event.get("event_type", "")

        # Blocked actions: policy_block or PolicyBlock in name
        if event_type == "policy_block" or "PolicyBlock" in event_type:
            blocked += 1

        # Approval requests: policy_hold or PolicyHold in name
        if event_type == "policy_hold" or "PolicyHold" in event_type:
            approvals += 1

        # Budget exceeded: budget_exhausted or BudgetExhausted in name
        if event_type == "budget_exhausted" or "BudgetExhausted" in event_type:
            budget_exceeded += 1

        # Unauthorized access: permission_denied or PermissionDenied in name
        if event_type == "permission_denied" or "PermissionDenied" in event_type:
            unauthorized += 1

        # Total actions: starts with "world."
        if event_type.startswith("world."):
            total_actions += 1

        # Policy hits: "policy" appears anywhere in the event type
        if "policy" in event_type.lower():
            policy_hits += 1

    return {
        "blocked": blocked,
        "approvals": approvals,
        "budget_exceeded": budget_exceeded,
        "unauthorized": unauthorized,
        "total_actions": total_actions,
        "policy_hits": policy_hits,
    }


def _format_value(val: Any) -> str:
    """Format a metric value for display."""
    if val is None:
        return "-"
    if isinstance(val, float):
        return f"{val:.2f}"
    return str(val)
