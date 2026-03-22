"""Tests for terrarium.core.context — ActionContext, StepResult, ResponseProposal."""
import pytest
from terrarium.core.context import ActionContext, StepResult, ResponseProposal
from terrarium.core.types import StepVerdict, ActorId, ServiceId


def test_action_context_mutable():
    ctx = ActionContext(
        request_id="req_1",
        actor_id=ActorId("actor_0"),
        service_id=ServiceId("svc_0"),
        action="test_action",
    )
    ctx.actor_id = ActorId("actor_1")
    assert ctx.actor_id == "actor_1"


def test_step_result_frozen():
    result = StepResult(step_name="test", verdict=StepVerdict.ALLOW)
    with pytest.raises(Exception):  # ValidationError for frozen model
        result.step_name = "changed"


def test_step_result_is_terminal():
    assert StepResult(step_name="t", verdict=StepVerdict.DENY).is_terminal is True
    assert StepResult(step_name="t", verdict=StepVerdict.HOLD).is_terminal is True
    assert StepResult(step_name="t", verdict=StepVerdict.ESCALATE).is_terminal is True
    assert StepResult(step_name="t", verdict=StepVerdict.ERROR).is_terminal is True
    assert StepResult(step_name="t", verdict=StepVerdict.ALLOW).is_terminal is False


def test_response_proposal_frozen():
    rp = ResponseProposal(response_body={"data": 1})
    with pytest.raises(Exception):
        rp.response_body = {"other": 2}


def test_action_context_default_values():
    ctx = ActionContext(
        request_id="req_1",
        actor_id=ActorId("actor_0"),
        service_id=ServiceId("svc_0"),
        action="test_action",
    )
    assert ctx.permission_result is None
    assert ctx.policy_result is None
    assert ctx.budget_result is None
    assert ctx.capability_result is None
    assert ctx.response_proposal is None
