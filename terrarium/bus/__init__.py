"""Event Bus -- the nervous system of the Terrarium framework.

This package provides the asynchronous event bus that connects all engines
and subsystems.  Events are published, fanned out to subscribers, persisted
to an append-only SQLite log, and can be replayed on demand.

Re-exports the primary public API surface so downstream code can do::

    from terrarium.bus import EventBus, BusConfig, BusMetrics
"""

from terrarium.bus.bus import EventBus
from terrarium.bus.config import BusConfig
from terrarium.bus.fanout import TopicFanout
from terrarium.bus.middleware import BusMiddleware, LoggingMiddleware, MetricsMiddleware, MiddlewareChain
from terrarium.bus.persistence import BusPersistence
from terrarium.bus.replay import ReplayEngine
from terrarium.bus.types import BusMetrics, Subscriber, Subscription

__all__ = [
    # Public API
    "BusConfig",
    "BusMetrics",
    "BusMiddleware",
    "EventBus",
    "ReplayEngine",
    "Subscriber",
    # Internal (exported for advanced use / testing)
    "BusPersistence",
    "LoggingMiddleware",
    "MetricsMiddleware",
    "MiddlewareChain",
    "Subscription",
    "TopicFanout",
]
