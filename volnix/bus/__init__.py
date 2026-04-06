"""Event Bus -- the nervous system of the Volnix framework.

This package provides the asynchronous event bus that connects all engines
and subsystems.  Events are published, fanned out to subscribers, persisted
to an append-only SQLite log, and can be replayed on demand.

Re-exports the primary public API surface so downstream code can do::

    from volnix.bus import EventBus, BusConfig, BusMetrics
"""

from volnix.bus.bus import EventBus
from volnix.bus.config import BusConfig
from volnix.bus.fanout import TopicFanout
from volnix.bus.middleware import (
    BusMiddleware,
    LoggingMiddleware,
    MetricsMiddleware,
    MiddlewareChain,
)
from volnix.bus.persistence import BusPersistence
from volnix.bus.replay import ReplayEngine
from volnix.bus.types import BusMetrics, Subscriber, Subscription

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
