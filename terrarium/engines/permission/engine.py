"""Permission engine implementation.

Checks actor permissions, computes visibility scopes, and enforces
authority boundaries as a pipeline step. All permission rules come
from the actor's YAML-defined permissions — no hardcoded conditions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, ClassVar

from terrarium.core import (
    ActionContext,
    ActorId,
    BaseEngine,
    EntityId,
    Event,
    PipelineStep,
    StepResult,
    StepVerdict,
    WorldMode,
)
from terrarium.core.events import PermissionDeniedEvent
from terrarium.core.types import Timestamp

logger = logging.getLogger(__name__)


def _now_timestamp() -> Timestamp:
    """Create a Timestamp for the current moment."""
    now = datetime.now(timezone.utc)
    return Timestamp(world_time=now, wall_time=now, tick=0)


class PermissionEngine(BaseEngine):
    """Checks actor permissions against the ActorRegistry.

    Also acts as the ``permission`` pipeline step.
    """

    engine_name: ClassVar[str] = "permission"
    subscriptions: ClassVar[list[str]] = []
    dependencies: ClassVar[list[str]] = ["state"]

    def __init__(self) -> None:
        super().__init__()
        self._actor_registry: Any = None
        self._world_mode: str = "governed"

    # -- PipelineStep interface ------------------------------------------------

    @property
    def step_name(self) -> str:
        """Return the pipeline step name."""
        return "permission"

    async def execute(self, ctx: ActionContext) -> StepResult:
        """Check actor permissions for this action.

        Looks up the actor from the ActorRegistry and checks:
        1. Write access to the target service
        2. Read access to the target service (for read-like actions)

        In ungoverned mode, permission violations are logged but not blocked.
        Unknown actors (not in registry) are allowed through.
        """
        actor = self._get_actor(ctx.actor_id)
        logger.debug(
            "Permission check: actor_id=%s, found=%s",
            ctx.actor_id, actor is not None,
        )
        if actor is None:
            if self._is_ungoverned() or self._actor_registry is None:
                # Ungoverned mode or no registry injected: allow unknown actors
                return StepResult(
                    step_name=self.step_name,
                    verdict=StepVerdict.ALLOW,
                    message="actor not in registry — allowed",
                )
            # Governed mode: unknown actors are denied
            event = PermissionDeniedEvent(
                event_type="permission.denied",
                timestamp=_now_timestamp(),
                actor_id=ctx.actor_id,
                action=ctx.action,
                reason=f"Unknown actor '{ctx.actor_id}' not registered",
            )
            return StepResult(
                step_name=self.step_name,
                verdict=StepVerdict.DENY,
                events=[event],
                message=f"Unknown actor '{ctx.actor_id}' not registered",
            )

        perms = actor.permissions
        if not perms:
            # No permissions defined — allow
            return StepResult(
                step_name=self.step_name,
                verdict=StepVerdict.ALLOW,
                message="no permissions defined — allowed",
            )

        service_str = str(ctx.service_id)

        # Check write access to service
        # write_access must be "all" (string) or a list of service names
        write_access = perms.get("write", [])
        if not self._has_access(write_access, service_str):
            reason = f"No write access to service '{service_str}'"
            event = PermissionDeniedEvent(
                event_type="permission.denied",
                timestamp=_now_timestamp(),
                actor_id=ctx.actor_id,
                action=ctx.action,
                reason=reason,
            )
            if self._is_ungoverned():
                return StepResult(
                    step_name=self.step_name,
                    verdict=StepVerdict.ALLOW,
                    events=[event],
                    message=f"ungoverned: {reason}",
                )
            return StepResult(
                step_name=self.step_name,
                verdict=StepVerdict.DENY,
                events=[event],
                message=reason,
            )

        # Check read access to service
        read_access = perms.get("read", [])
        if not self._has_access(read_access, service_str):
            reason = f"No read access to service '{service_str}'"
            event = PermissionDeniedEvent(
                event_type="permission.denied",
                timestamp=_now_timestamp(),
                actor_id=ctx.actor_id,
                action=ctx.action,
                reason=reason,
            )
            if self._is_ungoverned():
                return StepResult(
                    step_name=self.step_name,
                    verdict=StepVerdict.ALLOW,
                    events=[event],
                    message=f"ungoverned: {reason}",
                )
            return StepResult(
                step_name=self.step_name,
                verdict=StepVerdict.DENY,
                events=[event],
                message=reason,
            )

        # Check action-specific constraints
        actions = perms.get("actions", {})
        if ctx.action in actions:
            constraint = actions[ctx.action]
            if isinstance(constraint, dict):
                for key, limit in constraint.items():
                    field_name = key.replace("max_", "")
                    input_val = ctx.input_data.get(field_name, ctx.input_data.get(key))
                    if (
                        input_val is not None
                        and isinstance(input_val, (int, float))
                        and isinstance(limit, (int, float))
                        and input_val > limit
                    ):
                        reason = (
                            f"Action '{ctx.action}' exceeds authority: "
                            f"{field_name}={input_val} > {key}={limit}"
                        )
                        event = PermissionDeniedEvent(
                            event_type="permission.denied",
                            timestamp=_now_timestamp(),
                            actor_id=ctx.actor_id,
                            action=ctx.action,
                            reason=reason,
                        )
                        if self._is_ungoverned():
                            return StepResult(
                                step_name=self.step_name,
                                verdict=StepVerdict.ALLOW,
                                events=[event],
                                message=f"ungoverned: {reason}",
                            )
                        return StepResult(
                            step_name=self.step_name,
                            verdict=StepVerdict.DENY,
                            events=[event],
                            message=reason,
                        )

        return StepResult(step_name=self.step_name, verdict=StepVerdict.ALLOW)

    # -- BaseEngine hook -------------------------------------------------------

    async def _handle_event(self, event: Event) -> None:
        """Process inbound events."""
        logger.debug("%s: received event %s", self.engine_name, event.event_type)

    # -- Permission operations -------------------------------------------------

    async def check_permission(self, ctx: ActionContext) -> StepResult:
        """Alias for execute — check permissions for the action."""
        return await self.execute(ctx)

    async def get_visible_entities(
        self, actor_id: ActorId, entity_type: str
    ) -> list[EntityId]:
        """Return entity IDs visible to the actor (stub — Phase G)."""
        return []

    async def get_actor_permissions(self, actor_id: ActorId) -> dict[str, Any]:
        """Return the actor's permission definition."""
        actor = self._get_actor(actor_id)
        if actor is None:
            return {}
        return dict(actor.permissions)

    # -- Internal helpers ------------------------------------------------------

    def _get_actor(self, actor_id: ActorId) -> Any:
        """Look up an actor from the registry, returning None if not found."""
        if self._actor_registry is None:
            return None
        return self._actor_registry.get_or_none(actor_id)

    def _is_ungoverned(self) -> bool:
        """Check if the world is in ungoverned mode."""
        return (
            self._world_mode == WorldMode.UNGOVERNED
            or self._world_mode == "ungoverned"
        )

    @staticmethod
    def _has_access(access_config: Any, service: str) -> bool:
        """Check if access config grants access to the given service.

        access_config is one of:
        - "all" (string) → universal access
        - ["email", "chat"] (list) → service must be in list
        - anything else → no access (deny)
        """
        if access_config == "all":
            return True
        if isinstance(access_config, list):
            return service in access_config
        return False
