"""Service capture -- extract behavioral fingerprint from a completed run.

The capture step is the first stage of the promotion ladder:
  Bootstrapped → **capture** behavioral rules → curate → Tier 2

It produces a :class:`CapturedSurface` by analysing the event log
from a simulation run and grouping observations by service.
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

from volnix.core.types import RunId, ServiceId
from volnix.engines.feedback.annotations import AnnotationStore
from volnix.engines.feedback.models import (
    CapturedSurface,
    ObservedError,
    ObservedMutation,
    ObservedOperation,
)

logger = logging.getLogger(__name__)


class ServiceCapture:
    """Extracts a service's behavioral fingerprint from a completed run."""

    def __init__(
        self,
        artifact_store: Any,
        annotation_store: AnnotationStore | None = None,
    ) -> None:
        self._artifacts = artifact_store
        self._annotations = annotation_store

    async def capture(
        self, run_id: RunId | str, service_name: ServiceId | str
    ) -> CapturedSurface:
        """Extract observed behavior for *service_name* from *run_id*.

        Steps:
        1. Load event_log artifact from the run
        2. Filter events belonging to this service
        3. Group operations, mutations, errors
        4. Collect annotations tagged to this run
        5. Build CapturedSurface
        """
        name = service_name.lower()

        # 1. Load event log
        events = await self._load_events(run_id)

        # 2. Filter for this service
        service_events = [
            e for e in events
            if self._event_matches_service(e, name)
        ]

        # 3. Build observations
        operations = self._extract_operations(service_events)
        mutations = self._extract_mutations(service_events)
        errors = self._extract_errors(service_events)

        # 4. Load annotations
        annotations: list[dict[str, Any]] = []
        if self._annotations:
            run_annotations = await self._annotations.get_by_run(run_id)
            annotations = [
                a for a in run_annotations
                if a.get("service_id", "").lower() == name
            ]

        # 5. Extract behavioral rules from annotations
        behavioral_rules = [
            a["text"] for a in annotations if a.get("text")
        ]

        return CapturedSurface(
            service_name=name,
            run_id=run_id,
            captured_at=datetime.now(UTC).isoformat(),
            operations_observed=operations,
            entity_mutations=mutations,
            error_patterns=errors,
            annotations=annotations,
            behavioral_rules=behavioral_rules,
            source_profile=name,
            fidelity_source="bootstrapped",
        )

    # -- Internal helpers ------------------------------------------------------

    async def _load_events(self, run_id: str) -> list[dict[str, Any]]:
        """Load event_log artifact for a run."""
        if self._artifacts is None:
            return []
        try:
            data = await self._artifacts.load_artifact(run_id, "event_log")
            if isinstance(data, list):
                return data
            return []
        except (KeyError, FileNotFoundError, ValueError, OSError) as exc:
            logger.warning(
                "Failed to load event_log for run '%s': %s", run_id, exc
            )
            return []

    @staticmethod
    def _event_matches_service(event: Any, service_name: str) -> bool:
        """Check if an event belongs to the given service."""
        if isinstance(event, dict):
            sid = event.get("service_id", "")
            action = event.get("action", "")
        else:
            sid = str(getattr(event, "service_id", ""))
            action = str(getattr(event, "action", ""))
        return (
            sid.lower() == service_name
            or action.lower().startswith(f"{service_name}_")
        )

    @staticmethod
    def _extract_operations(events: list[Any]) -> list[ObservedOperation]:
        """Group events by action name and count calls."""
        op_counts: Counter[str] = Counter()
        op_params: defaultdict[str, set[str]] = defaultdict(set)
        op_responses: defaultdict[str, set[str]] = defaultdict(set)
        op_errors: Counter[str] = Counter()

        for event in events:
            if isinstance(event, dict):
                action = event.get("action", "")
                input_data = event.get("input_data", {})
                response = event.get("response_body", {})
                has_error = bool(event.get("error"))
            else:
                action = str(getattr(event, "action", ""))
                input_data = getattr(event, "input_data", {}) or {}
                response = getattr(event, "response_body", {}) or {}
                has_error = bool(getattr(event, "error", None))

            if not action:
                continue

            op_counts[action] += 1
            if isinstance(input_data, dict):
                op_params[action].update(input_data.keys())
            if isinstance(response, dict):
                op_responses[action].update(response.keys())
            if has_error:
                op_errors[action] += 1

        return [
            ObservedOperation(
                name=action,
                call_count=count,
                parameter_keys=sorted(op_params.get(action, set())),
                response_keys=sorted(op_responses.get(action, set())),
                error_count=op_errors.get(action, 0),
            )
            for action, count in op_counts.most_common()
        ]

    @staticmethod
    def _extract_mutations(events: list[Any]) -> list[ObservedMutation]:
        """Group entity mutations by type and operation."""
        mutation_counts: Counter[tuple[str, str]] = Counter()

        for event in events:
            if isinstance(event, dict):
                deltas = event.get("state_deltas", [])
            else:
                deltas = getattr(event, "state_deltas", []) or []

            for delta in deltas:
                if isinstance(delta, dict):
                    etype = delta.get("entity_type", "")
                    op = delta.get("operation", "")
                else:
                    etype = str(getattr(delta, "entity_type", ""))
                    op = str(getattr(delta, "operation", ""))
                if etype and op:
                    mutation_counts[(etype, op)] += 1

        return [
            ObservedMutation(entity_type=etype, operation=op, count=count)
            for (etype, op), count in mutation_counts.most_common()
        ]

    @staticmethod
    def _extract_errors(events: list[Any]) -> list[ObservedError]:
        """Group error events by type."""
        error_counts: Counter[str] = Counter()
        error_contexts: dict[str, str] = {}

        for event in events:
            if isinstance(event, dict):
                error = event.get("error", "")
                event_type = event.get("event_type", "")
            else:
                error = str(getattr(event, "error", ""))
                event_type = str(getattr(event, "event_type", ""))

            if error:
                error_type = error[:100] if len(error) > 100 else error
                error_counts[error_type] += 1
                if error_type not in error_contexts:
                    error_contexts[error_type] = event_type

        return [
            ObservedError(
                error_type=etype,
                count=count,
                context=error_contexts.get(etype, ""),
            )
            for etype, count in error_counts.most_common()
        ]
