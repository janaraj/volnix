"""Base engine abstract class for the Terrarium framework.

Every engine in Terrarium (state, policy, budget, animator, etc.) inherits
from :class:`BaseEngine`, which provides a uniform lifecycle (initialize,
start, stop), health-check plumbing, event bus integration, and a hook-based
extension pattern that concrete engines override.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from terrarium.core.events import Event


class BaseEngine(ABC):
    """Abstract base class for all Terrarium engines.

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

    # ------------------------------------------------------------------
    # Public lifecycle API
    # ------------------------------------------------------------------

    async def initialize(self, config: dict[str, Any], bus: Any) -> None:
        """Inject configuration and event bus, then run engine-specific setup.

        Args:
            config: Engine-specific configuration dictionary.
            bus: The shared event bus instance.
        """
        ...

    async def start(self) -> None:
        """Start the engine, subscribing to events and enabling processing."""
        ...

    async def stop(self) -> None:
        """Gracefully stop the engine and release resources."""
        ...

    async def health_check(self) -> dict[str, Any]:
        """Return a health-check payload for this engine.

        Returns:
            A dict with at least ``{"healthy": bool, "engine": str}``.
        """
        ...

    # ------------------------------------------------------------------
    # Extension hooks (override in subclasses)
    # ------------------------------------------------------------------

    async def _on_initialize(self) -> None:
        """Hook called once after config and bus are injected.

        Override to perform engine-specific setup such as loading schemas,
        connecting to backing stores, etc.
        """
        ...

    async def _on_start(self) -> None:
        """Hook called when the engine transitions to the *started* state.

        Override to begin background tasks, register subscriptions, etc.
        """
        ...

    async def _on_stop(self) -> None:
        """Hook called when the engine is being stopped.

        Override to cancel background tasks and flush buffers.
        """
        ...

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
        ...

    async def _dispatch_event(self, event: Event) -> None:
        """Internal dispatcher that routes an inbound event to :meth:`_handle_event`.

        Handles error wrapping and metrics collection around the concrete
        handler.

        Args:
            event: The event to dispatch.
        """
        ...

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
        ...
