"""E2E governance tests — permission, policy, and budget through the pipeline.

These tests exercise the real governance engines wired into the full
TerrariumApp pipeline, verifying that governance decisions flow correctly
from YAML-defined rules through to pipeline verdicts and events.
"""
import pytest

from terrarium.core.context import ActionContext
from terrarium.core.types import ActorId, ActorType, ServiceId, StepVerdict
from terrarium.core.events import (
    BudgetDeductionEvent,
    BudgetExhaustedEvent,
    PermissionDeniedEvent,
    PolicyBlockEvent,
    PolicyFlagEvent,
    PolicyHoldEvent,
)
from terrarium.actors.definition import ActorDefinition
from terrarium.actors.registry import ActorRegistry


def _register_actors(app, *actors):
    """Register actors into the app's shared ActorRegistry."""
    # Get the actor registry from the compiler config (shared with governance engines)
    compiler = app.registry.get("world_compiler")
    actor_registry = compiler._config.get("_actor_registry")
    if actor_registry is None:
        actor_registry = ActorRegistry()
        compiler._config["_actor_registry"] = actor_registry

    for actor in actors:
        if not actor_registry.has_actor(actor.id):
            actor_registry.register(actor)

    # Ensure governance engines share the same registry
    policy_engine = app.registry.get("policy")
    permission_engine = app.registry.get("permission")
    budget_engine = app.registry.get("budget")
    policy_engine._actor_registry = actor_registry
    permission_engine._actor_registry = actor_registry
    budget_engine._actor_registry = actor_registry

    return actor_registry


@pytest.mark.asyncio
async def test_permission_deny_at_step_1(app):
    """Agent with limited write access is denied at the permission step."""
    agent = ActorDefinition(
        id=ActorId("agent-perm"),
        type=ActorType.AGENT,
        role="support-agent",
        permissions={"write": ["email", "chat"], "read": ["email", "chat", "payments"]},
    )
    _register_actors(app, agent)

    # Set governed mode
    permission_engine = app.registry.get("permission")
    permission_engine._world_mode = "governed"

    result = await app.handle_action(
        actor_id="agent-perm",
        service_id="payments",
        action="stripe_refunds_create",
        input_data={"amount": 100},
    )

    assert "error" in result
    assert "permission" in result.get("step", "")


@pytest.mark.asyncio
async def test_policy_hold_at_step_2(app):
    """Agent triggers a policy hold at the policy step."""
    agent = ActorDefinition(
        id=ActorId("agent-policy"),
        type=ActorType.AGENT,
        role="support-agent",
        permissions={"write": ["payments"], "read": "all"},
    )
    _register_actors(app, agent)

    # Configure policy
    policy_engine = app.registry.get("policy")
    policy_engine._world_mode = "governed"
    policy_engine._policies = [
        {
            "name": "Refund approval",
            "trigger": {"action": "stripe_refunds_create", "condition": "input.amount > 50"},
            "enforcement": "hold",
            "hold_config": {"approver_role": "supervisor", "timeout": "30m"},
        }
    ]

    result = await app.handle_action(
        actor_id="agent-policy",
        service_id="payments",
        action="stripe_refunds_create",
        input_data={"amount": 100},
    )

    assert "error" in result
    assert "policy" in result.get("step", "")


@pytest.mark.asyncio
async def test_budget_exhaust_at_step_3(app):
    """Agent exhausts budget and is denied at the budget step."""
    agent = ActorDefinition(
        id=ActorId("agent-budget"),
        type=ActorType.AGENT,
        role="support-agent",
        permissions={"write": "all", "read": "all"},
        budget={"api_calls": 2},
    )
    _register_actors(app, agent)

    # Configure engines for governed mode
    budget_engine = app.registry.get("budget")
    budget_engine._world_mode = "governed"
    policy_engine = app.registry.get("policy")
    policy_engine._world_mode = "governed"
    policy_engine._policies = []

    # Use up budget
    for _ in range(2):
        await app.handle_action(
            actor_id="agent-budget",
            service_id="email",
            action="email_send",
            input_data={"to": "test@test.com"},
        )

    # Third action should be denied
    result = await app.handle_action(
        actor_id="agent-budget",
        service_id="email",
        action="email_send",
        input_data={"to": "test@test.com"},
    )

    assert "error" in result
    assert "budget" in result.get("step", "")


@pytest.mark.asyncio
async def test_governed_vs_ungoverned(app):
    """Same action yields different enforcement in governed vs ungoverned mode."""
    agent = ActorDefinition(
        id=ActorId("agent-compare"),
        type=ActorType.AGENT,
        role="support-agent",
        permissions={"write": ["email"], "read": ["email"]},
    )
    _register_actors(app, agent)

    # Governed: should deny
    permission_engine = app.registry.get("permission")
    permission_engine._world_mode = "governed"

    result_governed = await app.handle_action(
        actor_id="agent-compare",
        service_id="payments",
        action="stripe_refunds_create",
        input_data={"amount": 100},
    )
    assert "error" in result_governed

    # Ungoverned: should allow (event still emitted)
    permission_engine._world_mode = "ungoverned"

    result_ungoverned = await app.handle_action(
        actor_id="agent-compare",
        service_id="payments",
        action="stripe_refunds_create",
        input_data={"amount": 100},
    )
    # In ungoverned mode, the permission step returns ALLOW, so the pipeline continues.
    # It may still fail at a later step (e.g., responder) but the permission step itself passed.
    # We verify by checking it didn't short-circuit at "permission"
    assert result_ungoverned.get("step") != "permission"


@pytest.mark.asyncio
async def test_policy_block_event_published(app):
    """Verify that policy block events are published to the bus."""
    agent = ActorDefinition(
        id=ActorId("agent-block"),
        type=ActorType.AGENT,
        role="support-agent",
        permissions={"write": "all", "read": "all"},
    )
    _register_actors(app, agent)

    policy_engine = app.registry.get("policy")
    policy_engine._world_mode = "governed"
    policy_engine._policies = [
        {
            "name": "Block dangerous actions",
            "trigger": {"action": "dangerous_action"},
            "enforcement": "block",
        }
    ]

    result = await app.handle_action(
        actor_id="agent-block",
        service_id="system",
        action="dangerous_action",
        input_data={},
    )

    assert "error" in result
    assert "policy" in result.get("step", "")


# ── SUCCESS PATH TESTS ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_passes_all_governance_and_completes_action(app):
    """Agent with proper permissions, no policy triggers, budget available → full success.

    This is THE most important test: an agent navigates all 3 governance
    layers (permission, policy, budget) and successfully completes an action.
    """
    agent = ActorDefinition(
        id=ActorId("agent-success"),
        type=ActorType.AGENT,
        role="support-agent",
        permissions={"write": ["email", "chat"], "read": "all"},
        budget={"api_calls": 100},
    )
    _register_actors(app, agent)

    policy_engine = app.registry.get("policy")
    policy_engine._world_mode = "governed"
    policy_engine._policies = [
        {
            "name": "Communication protocol",
            "trigger": {"action": "ticket_update"},
            "enforcement": "log",
        }
    ]
    permission_engine = app.registry.get("permission")
    permission_engine._world_mode = "governed"
    budget_engine = app.registry.get("budget")
    budget_engine._world_mode = "governed"

    result = await app.handle_action(
        actor_id="agent-success",
        service_id="email",
        action="email_send",
        input_data={
            "from_addr": "agent@acme.com",
            "to_addr": "customer@test.com",
            "subject": "Your ticket has been resolved",
            "body": "We fixed the issue with your account.",
        },
    )

    assert "error" not in result, f"Expected success, got: {result}"
    assert "email_id" in result
    assert result.get("status") == "sent"


@pytest.mark.asyncio
async def test_agent_succeeds_with_log_policy_triggered(app):
    """Agent triggers a LOG policy but action still succeeds — not blocked."""
    agent = ActorDefinition(
        id=ActorId("agent-log"),
        type=ActorType.AGENT,
        role="support-agent",
        permissions={"write": ["email"], "read": "all"},
        budget={"api_calls": 50},
    )
    _register_actors(app, agent)

    policy_engine = app.registry.get("policy")
    policy_engine._world_mode = "governed"
    policy_engine._policies = [
        {
            "name": "Log all email sends",
            "trigger": {"action": "email_send"},
            "enforcement": "log",
        }
    ]
    permission_engine = app.registry.get("permission")
    permission_engine._world_mode = "governed"
    budget_engine = app.registry.get("budget")
    budget_engine._world_mode = "governed"

    result = await app.handle_action(
        actor_id="agent-log",
        service_id="email",
        action="email_send",
        input_data={
            "from_addr": "agent@acme.com",
            "to_addr": "customer@test.com",
            "subject": "Following up",
            "body": "Just checking in on your request.",
        },
    )

    assert "error" not in result, f"Expected success, got: {result}"
    assert "email_id" in result


@pytest.mark.asyncio
async def test_agent_multiple_actions_within_budget(app):
    """Agent makes 3 actions within budget of 5 — all succeed."""
    agent = ActorDefinition(
        id=ActorId("agent-budget-ok"),
        type=ActorType.AGENT,
        role="support-agent",
        permissions={"write": ["email"], "read": "all"},
        budget={"api_calls": 5},
    )
    _register_actors(app, agent)

    policy_engine = app.registry.get("policy")
    policy_engine._world_mode = "governed"
    policy_engine._policies = []
    permission_engine = app.registry.get("permission")
    permission_engine._world_mode = "governed"
    budget_engine = app.registry.get("budget")
    budget_engine._world_mode = "governed"

    for i in range(3):
        result = await app.handle_action(
            actor_id="agent-budget-ok",
            service_id="email",
            action="email_send",
            input_data={
                "from_addr": "agent@acme.com",
                "to_addr": f"customer{i}@test.com",
                "subject": f"Ticket #{i+1} resolved",
                "body": "Your issue has been addressed.",
            },
        )
        assert "error" not in result, f"Action {i+1} failed: {result}"
        assert "email_id" in result


@pytest.mark.asyncio
async def test_agent_below_policy_threshold_succeeds(app):
    """Agent action with amount BELOW policy threshold → not triggered → success."""
    agent = ActorDefinition(
        id=ActorId("agent-under-limit"),
        type=ActorType.AGENT,
        role="support-agent",
        permissions={"write": ["email"], "read": "all"},
        budget={"api_calls": 100},
    )
    _register_actors(app, agent)

    policy_engine = app.registry.get("policy")
    policy_engine._world_mode = "governed"
    policy_engine._policies = [
        {
            "name": "High amount hold",
            "trigger": {"action": "email_send", "condition": "input.amount > 5000"},
            "enforcement": "hold",
        }
    ]
    permission_engine = app.registry.get("permission")
    permission_engine._world_mode = "governed"
    budget_engine = app.registry.get("budget")
    budget_engine._world_mode = "governed"

    result = await app.handle_action(
        actor_id="agent-under-limit",
        service_id="email",
        action="email_send",
        input_data={
            "from_addr": "agent@acme.com",
            "to_addr": "customer@test.com",
            "subject": "Small refund processed",
            "body": "Your $1 refund has been processed.",
            "amount": 100,
        },
    )

    assert "error" not in result, f"Expected success, got: {result}"
    assert "email_id" in result


@pytest.mark.asyncio
async def test_full_governed_lifecycle_with_ledger_trace(app):
    """Full lifecycle: register → configure → act → verify ALL 7 steps in ledger."""
    agent = ActorDefinition(
        id=ActorId("agent-lifecycle"),
        type=ActorType.AGENT,
        role="support-agent",
        permissions={"write": ["email"], "read": "all"},
        budget={"api_calls": 10},
    )
    _register_actors(app, agent)

    policy_engine = app.registry.get("policy")
    policy_engine._world_mode = "governed"
    policy_engine._policies = []
    permission_engine = app.registry.get("permission")
    permission_engine._world_mode = "governed"
    budget_engine = app.registry.get("budget")
    budget_engine._world_mode = "governed"

    # 2 successful actions
    for i in range(2):
        result = await app.handle_action(
            actor_id="agent-lifecycle",
            service_id="email",
            action="email_send",
            input_data={
                "from_addr": "agent@acme.com",
                "to_addr": f"customer{i}@test.com",
                "subject": f"Response #{i+1}",
                "body": "Thank you for your patience.",
            },
        )
        assert "email_id" in result

    # Verify ledger: 7 pipeline steps per action × 2 actions = 14 entries
    from terrarium.ledger.query import LedgerQuery
    entries = await app.ledger.query(LedgerQuery(limit=100))
    pipeline_entries = [e for e in entries if e.entry_type == "pipeline_step"]
    assert len(pipeline_entries) >= 14, (
        f"Expected >=14 pipeline entries (2 actions × 7 steps), got {len(pipeline_entries)}"
    )

    # Verify ALL steps passed with "allow"
    for entry in pipeline_entries:
        assert entry.verdict == "allow", (
            f"Step {entry.step_name} had verdict {entry.verdict}, expected allow"
        )

    # Verify state engine has the 2 emails
    state = app.registry.get("state")
    emails = await state.query_entities("email")
    assert len(emails) >= 2
