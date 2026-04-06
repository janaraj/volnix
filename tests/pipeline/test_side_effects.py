"""Tests for volnix.pipeline.side_effects -- deferred side-effect queue."""

import pytest

from volnix.core.context import ActionContext, ResponseProposal, StepResult
from volnix.core.types import ActorId, ServiceId, SideEffect, StepVerdict
from volnix.pipeline.dag import PipelineDAG
from volnix.pipeline.side_effects import SideEffectProcessor

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


class MockStep:
    """Configurable mock pipeline step."""

    def __init__(self, name, verdict=StepVerdict.ALLOW, side_effect_fn=None):
        self._name = name
        self._verdict = verdict
        self._side_effect_fn = side_effect_fn
        self.call_count = 0

    @property
    def step_name(self):
        return self._name

    async def execute(self, ctx):
        self.call_count += 1
        if self._side_effect_fn:
            self._side_effect_fn(ctx)
        return StepResult(step_name=self._name, verdict=self._verdict)


class MockResponderStep:
    """Mock responder step that sets response_proposal with side effects."""

    def __init__(self, side_effects_to_produce=None, max_produces=None):
        self._side_effects = side_effects_to_produce or []
        self._max_produces = max_produces  # limit how many times we produce SEs
        self.call_count = 0

    @property
    def step_name(self):
        return "responder"

    async def execute(self, ctx):
        self.call_count += 1
        # Only produce side effects up to max_produces times
        if self._max_produces is None or self.call_count <= self._max_produces:
            ctx.response_proposal = ResponseProposal(
                proposed_side_effects=self._side_effects,
            )
        else:
            ctx.response_proposal = ResponseProposal()
        return StepResult(step_name="responder", verdict=StepVerdict.ALLOW)


def _make_ctx(**kwargs):
    defaults = dict(
        request_id="req_1",
        actor_id=ActorId("agent"),
        service_id=ServiceId("test"),
        action="test_action",
    )
    defaults.update(kwargs)
    return ActionContext(**defaults)


def _make_se(effect_type="notify", target_service=None, **params):
    return SideEffect(
        effect_type=effect_type,
        target_service=target_service or ServiceId("svc"),
        parameters=params,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_and_process():
    """1 SE -- 1 pipeline execution."""
    step = MockStep("a")
    dag = PipelineDAG(steps=[step])
    proc = SideEffectProcessor(dag, max_depth=10)

    parent_ctx = _make_ctx()
    se = _make_se()
    await proc.enqueue(se, parent_ctx)
    count = await proc.process_all()

    assert count == 1
    assert step.call_count == 1


@pytest.mark.asyncio
async def test_process_multiple():
    """3 SEs -- 3 executions."""
    step = MockStep("a")
    dag = PipelineDAG(steps=[step])
    proc = SideEffectProcessor(dag, max_depth=10)

    parent_ctx = _make_ctx()
    for _ in range(3):
        await proc.enqueue(_make_se(), parent_ctx)

    count = await proc.process_all()
    assert count == 3
    assert step.call_count == 3


@pytest.mark.asyncio
async def test_max_depth_enforced():
    """depth >= max_depth -- SE dropped, not processed."""
    step = MockStep("a")
    dag = PipelineDAG(steps=[step])
    proc = SideEffectProcessor(dag, max_depth=3)

    parent_ctx = _make_ctx()
    await proc.enqueue(_make_se(), parent_ctx, depth=3)
    count = await proc.process_all()

    assert count == 0
    assert step.call_count == 0


@pytest.mark.asyncio
async def test_nested_side_effects():
    """Step produces SE in response_proposal -- re-enqueued at depth+1."""
    nested_se = _make_se(effect_type="nested_notify")
    responder = MockResponderStep(side_effects_to_produce=[nested_se], max_produces=1)
    dag = PipelineDAG(steps=[responder])
    proc = SideEffectProcessor(dag, max_depth=10)

    parent_ctx = _make_ctx()
    await proc.enqueue(_make_se(), parent_ctx)
    count = await proc.process_all()

    # First SE produces 1 nested SE, nested SE produces none (max_produces=1)
    assert count == 2
    assert responder.call_count == 2


@pytest.mark.asyncio
async def test_nested_depth_limit():
    """Nested SEs stop at max_depth."""
    # Always produce a nested SE
    nested_se = _make_se(effect_type="recursive")
    responder = MockResponderStep(side_effects_to_produce=[nested_se])
    dag = PipelineDAG(steps=[responder])
    proc = SideEffectProcessor(dag, max_depth=3)

    parent_ctx = _make_ctx()
    await proc.enqueue(_make_se(), parent_ctx, depth=0)
    count = await proc.process_all()

    # depth 0 -> produces SE at depth 1 -> produces SE at depth 2 -> produces SE at depth 3 (dropped)
    assert count == 3


@pytest.mark.asyncio
async def test_side_effect_to_context():
    """Verify all fields mapped correctly from SideEffect to ActionContext."""
    step = MockStep("a")
    dag = PipelineDAG(steps=[step])
    proc = SideEffectProcessor(dag)

    parent_ctx = _make_ctx()
    se = SideEffect(
        effect_type="send_email",
        target_service=ServiceId("email_svc"),
        parameters={"to": "user@example.com"},
    )
    ctx = proc._side_effect_to_context(se, parent_ctx)

    assert ctx.action == "send_email"
    assert ctx.service_id == ServiceId("email_svc")
    assert ctx.actor_id == parent_ctx.actor_id
    assert ctx.input_data == {"to": "user@example.com"}
    assert ctx.request_id.startswith("se_")


@pytest.mark.asyncio
async def test_process_all_returns_count():
    """process_all returns int count."""
    step = MockStep("a")
    dag = PipelineDAG(steps=[step])
    proc = SideEffectProcessor(dag)

    parent_ctx = _make_ctx()
    await proc.enqueue(_make_se(), parent_ctx)
    await proc.enqueue(_make_se(), parent_ctx)
    count = await proc.process_all()

    assert isinstance(count, int)
    assert count == 2


@pytest.mark.asyncio
async def test_empty_queue_returns_zero():
    """Nothing enqueued -- returns 0."""
    step = MockStep("a")
    dag = PipelineDAG(steps=[step])
    proc = SideEffectProcessor(dag)

    count = await proc.process_all()
    assert count == 0
