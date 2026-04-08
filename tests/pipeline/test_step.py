"""Tests for volnix.pipeline.step -- base step, result creation, and timing."""

import pytest

from volnix.core.context import ActionContext, StepResult
from volnix.core.types import EventId, StepVerdict
from volnix.pipeline.step import BasePipelineStep


class ConcreteStep(BasePipelineStep):
    """Minimal concrete subclass for testing."""

    step_name = "test_step"

    async def execute(self, ctx: ActionContext) -> StepResult:
        return self._make_result(StepVerdict.ALLOW, message="ok")


def test_base_step_is_abstract():
    """BasePipelineStep cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BasePipelineStep()


def test_make_result():
    """_make_result creates a StepResult with correct fields."""
    step = ConcreteStep()
    result = step._make_result(
        verdict=StepVerdict.DENY,
        message="denied",
        events=[EventId("evt_1")],
        metadata={"key": "value"},
        duration_ms=42.5,
    )
    assert result.step_name == "test_step"
    assert result.verdict == StepVerdict.DENY
    assert result.message == "denied"
    assert result.events == [EventId("evt_1")]
    assert result.metadata == {"key": "value"}
    assert result.duration_ms == 42.5


def test_make_result_defaults():
    """_make_result with minimal args produces sensible defaults."""
    step = ConcreteStep()
    result = step._make_result(verdict=StepVerdict.ALLOW)
    assert result.step_name == "test_step"
    assert result.verdict == StepVerdict.ALLOW
    assert result.message == ""
    assert result.events == []
    assert result.metadata == {}
    assert result.duration_ms == 0.0


def test_step_name_property():
    """Concrete subclass reports its step_name correctly."""
    step = ConcreteStep()
    assert step.step_name == "test_step"


def test_step_result_is_terminal():
    """Test that DENY, HOLD, ERROR are terminal; ALLOW and ESCALATE are not."""
    for verdict in (StepVerdict.DENY, StepVerdict.HOLD, StepVerdict.ERROR):
        result = StepResult(step_name="t", verdict=verdict)
        assert result.is_terminal is True, f"{verdict} should be terminal"

    for verdict in (StepVerdict.ALLOW, StepVerdict.ESCALATE):
        result = StepResult(step_name="t", verdict=verdict)
        assert result.is_terminal is False, f"{verdict} should NOT be terminal"
