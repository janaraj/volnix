"""Base engine abstract class for the Volnix framework.

Every engine in Volnix (state, policy, budget, animator, etc.) inherits
from :class:`BaseEngine`, which provides a uniform lifecycle (initialize,
start, stop), health-check plumbing, event bus integration, and a hook-based
extension pattern that concrete engines override.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, ClassVar

from volnix.core.events import EngineLifecycleEvent, Event
from volnix.core.types import Timestamp

logger = logging.getLogger(__name__)


class BaseEngine(ABC):
    """Abstract base class for all Volnix engines.

    Subclasses **must** override:

    * :pyattr:`engine_name` -- unique name used in logs and dependency graphs.
    * :meth:`_handle_event` -- process a single inbound event.

    Subclasses **may** override:

    * :meth:`_on_initialize` -- one-time setup after configuration is injected.
    * :meth:`_on_start` -- called when the engine is started.
    * :meth:`_on_stop` -- called when the engine is stopped.

    Class Attributes:
        engine_name: Canonical name of this engine (must be overridden).
        subscriptions: Event types this engine listens for.
        dependencies: Names of engines that must start before this one.

    Instance Attributes:
        _bus: Reference to the event bus (set during :meth:`initialize`).
        _config: Engine-specific configuration dict.
        _started: Whether :meth:`start` has been called.
        _healthy: Whether the engine considers itself healthy.
    """

    engine_name: ClassVar[str] = ""
    subscriptions: ClassVar[list[str]] = []
    dependencies: ClassVar[list[str]] = []

    def __init__(self) -> None:
        self._bus: Any = None
        self._config: dict[str, Any] = {}
        self._started: bool = False
        self._healthy: bool = False
        self._dependencies: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Public lifecycle API
    # ------------------------------------------------------------------

    async def initialize(self, config: dict[str, Any], bus: Any) -> None:
        """Inject configuration and event bus, then run engine-specific setup.

        Args:
            config: Engine-specific configuration dictionary.
            bus: The shared event bus instance.
        """
        self._config = config
        self._bus = bus
        self._healthy = True
        await self._on_initialize()
        await self._record_lifecycle("init")

    async def start(self) -> None:
        """Start the engine, subscribing to events and enabling processing."""
        if self._bus is not None:
            for topic in self.subscriptions:
                await self._bus.subscribe(topic, self._dispatch_event)
        self._started = True
        await self._on_start()
        await self._record_lifecycle("start")

    async def stop(self) -> None:
        """Gracefully stop the engine and release resources."""
        self._started = False
        if self._bus is not None:
            for topic in self.subscriptions:
                try:
                    await self._bus.unsubscribe(topic, self._dispatch_event)
                except Exception:
                    logger.debug(
                        "Failed to unsubscribe %s from topic %s",
                        self.engine_name,
                        topic,
                    )
        await self._on_stop()
        await self._record_lifecycle("stop")

    async def health_check(self) -> dict[str, Any]:
        """Return a health-check payload for this engine.

        Returns:
            A dict with at least ``{"healthy": bool, "engine": str}``.
        """
        return {
            "engine": self.engine_name,
            "started": self._started,
            "healthy": self._healthy,
        }

    # ------------------------------------------------------------------
    # Extension hooks (override in subclasses)
    # ------------------------------------------------------------------

    async def _on_initialize(self) -> None:
        """Hook called once after config and bus are injected.

        Override to perform engine-specific setup such as loading schemas,
        connecting to backing stores, etc.
        """
        pass

    async def _on_start(self) -> None:
        """Hook called when the engine transitions to the *started* state.

        Override to begin background tasks, register subscriptions, etc.
        """
        pass

    async def _on_stop(self) -> None:
        """Hook called when the engine is being stopped.

        Override to cancel background tasks and flush buffers.
        """
        pass

    @abstractmethod
    async def _handle_event(self, event: Event) -> None:
        """Process a single inbound event from the bus.

        This is the main extension point. Concrete engines implement their
        core logic here.

        Args:
            event: The event to handle.
        """
        ...

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def publish(self, event: Event) -> None:
        """Publish an event to the event bus.

        Args:
            event: The event to publish.
        """
        if self._bus is not None:
            await self._bus.publish(event)

    async def _record_lifecycle(self, event_type: str) -> None:
        """L2: Record EngineLifecycleEntry to ledger."""
        ledger = getattr(self, "_ledger", None)
        if ledger is None:
            return
        try:
            from volnix.ledger.entries import EngineLifecycleEntry

            entry = EngineLifecycleEntry(
                engine_name=self.engine_name,
                event_type=event_type,
            )
            await ledger.append(entry)
        except Exception:
            pass  # Best-effort — don't fail engine lifecycle

    async def _dispatch_event(self, event: Event) -> None:
        """Internal dispatcher that routes an inbound event to :meth:`_handle_event`.

        Handles error wrapping and metrics collection around the concrete
        handler.

        Args:
            event: The event to dispatch.
        """
        try:
            await self._handle_event(event)
        except Exception as exc:
            logger.exception(
                "Engine %s failed handling event %s", self.engine_name, event.event_type
            )
            await self._publish_error(exc, source_event=event)

    async def _publish_error(
        self,
        error: Exception,
        source_event: Event | None = None,
    ) -> None:
        """Publish an error event to the bus for observability.

        Args:
            error: The exception that occurred.
            source_event: The event being processed when the error happened.
        """
        error_event = EngineLifecycleEvent(
            event_type="engine.error",
            timestamp=Timestamp(
                world_time=datetime.now(UTC),
                wall_time=datetime.now(UTC),
                tick=0,
            ),
            engine_name=self.engine_name,
            status="error",
            metadata={
                "error": str(error),
                "error_type": type(error).__name__,
                "source_event_id": str(source_event.event_id) if source_event else None,
            },
        )
        if self._bus is not None:
            try:
                await self._bus.publish(error_event)
            except Exception:
                logger.error("Failed to publish error event for engine %s", self.engine_name)
