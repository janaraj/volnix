"""Shared fixtures and helpers for registry tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from volnix.core.context import ActionContext, StepResult
from volnix.core.engine import BaseEngine
from volnix.core.types import StepVerdict


def make_mock_engine(
    name: str,
    deps: list[str] | None = None,
    subs: list[str] | None = None,
    step_name_val: str | None = None,
) -> BaseEngine:
    """Create a unique mock engine subclass."""
    class_attrs: dict[str, Any] = {
        "engine_name": name,
        "dependencies": deps or [],
        "subscriptions": subs or [],
    }

    async def _handle_event(self, event):
        pass

    class_attrs["_handle_event"] = _handle_event

    if step_name_val is not None:
        class_attrs["step_name"] = property(lambda self, v=step_name_val: v)

        async def execute(self, ctx: ActionContext) -> StepResult:
            return StepResult(step_name=step_name_val, verdict=StepVerdict.ALLOW)

        class_attrs["execute"] = execute

    klass = type(f"MockEngine_{name}", (BaseEngine,), class_attrs)
    return klass()


def make_mock_bus() -> AsyncMock:
    """Create a mock bus with subscribe/unsubscribe/publish."""
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.unsubscribe = AsyncMock()
    bus.publish = AsyncMock()
    return bus
