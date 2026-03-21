"""Feedback engine implementation.

Manages service annotations, proposes fidelity tier promotions, and
checks for drift between simulated service profiles and real-world APIs.
"""

from __future__ import annotations

from typing import Any, ClassVar

from terrarium.core import BaseEngine, Event, ServiceId


class FeedbackEngine(BaseEngine):
    """Annotation, tier promotion, and external drift detection engine."""

    engine_name: ClassVar[str] = "feedback"
    subscriptions: ClassVar[list[str]] = ["capability_gap", "world", "simulation"]
    dependencies: ClassVar[list[str]] = ["state"]

    # -- BaseEngine hook -------------------------------------------------------

    async def _handle_event(self, event: Event) -> None:
        """Handle an inbound event from the bus."""
        ...

    # -- Feedback operations ---------------------------------------------------

    async def add_annotation(
        self, service_id: ServiceId, text: str, author: str
    ) -> None:
        """Attach an annotation to a service."""
        ...

    async def get_annotations(
        self, service_id: ServiceId
    ) -> list[dict[str, Any]]:
        """Retrieve all annotations for a service."""
        ...

    async def propose_promotion(
        self, service_id: ServiceId, evidence: dict[str, Any]
    ) -> None:
        """Propose a fidelity tier promotion for a service."""
        ...

    async def check_external_drift(
        self, service_id: ServiceId
    ) -> dict[str, Any] | None:
        """Check whether the real-world API has drifted from the profile.

        Returns:
            A drift report dict, or ``None`` if no drift detected.
        """
        ...
