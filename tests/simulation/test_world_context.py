"""Tests for WorldContextBundle."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from volnix.simulation.world_context import WorldContextBundle


def test_world_context_frozen():
    """WorldContextBundle is immutable after creation."""
    ctx = WorldContextBundle(
        world_description="A test world",
        reality_summary="Ideal conditions",
        behavior_mode="static",
    )
    with pytest.raises(ValidationError):
        ctx.world_description = "Changed"  # type: ignore[misc]


def test_world_context_defaults():
    """WorldContextBundle has sensible defaults."""
    ctx = WorldContextBundle()

    assert ctx.world_description == ""
    assert ctx.reality_summary == ""
    assert ctx.behavior_mode == "dynamic"
    assert ctx.behavior_description == ""
    assert ctx.governance_rules_summary == ""
    assert ctx.available_services == []
    assert ctx.mission == ""
    assert ctx.reality_dimensions == {}
    assert ctx.seeds == []


def test_to_system_prompt_full():
    """to_system_prompt includes all sections when populated."""
    ctx = WorldContextBundle(
        world_description="Corporate helpdesk simulation.",
        reality_summary="Messy reality with delays.",
        behavior_mode="reactive",
        behavior_description="Responds to agent actions.",
        governance_rules_summary="No PII sharing.",
        mission="Evaluate agent quality.",
        seeds=["VIP customer waiting 3 days for refund"],
        available_services=[
            {
                "name": "reply_ticket",
                "service": "helpdesk",
                "http_method": "POST",
                "required_params": ["ticket_id", "text"],
            },
            {
                "name": "list_tickets",
                "service": "helpdesk",
                "http_method": "GET",
                "required_params": [],
            },
        ],
    )

    prompt = ctx.to_system_prompt()

    assert "## World" in prompt
    assert "Corporate helpdesk simulation." in prompt
    assert "## Reality" in prompt
    assert "Messy reality" in prompt
    assert "## Mission" in prompt
    assert "Evaluate agent quality." in prompt
    assert "## World Scenarios" in prompt
    assert "VIP customer waiting 3 days" in prompt
    assert "## Available Tools" in prompt
    assert "### helpdesk" in prompt
    assert "action_type: \"list_tickets\"" in prompt
    assert "action_type: \"reply_ticket\"" in prompt


def test_to_system_prompt_minimal():
    """to_system_prompt works with minimal configuration."""
    ctx = WorldContextBundle(
        world_description="Simple world",
        reality_summary="Ideal",
        behavior_mode="static",
    )

    prompt = ctx.to_system_prompt()

    assert "## World" in prompt
    assert "Simple world" in prompt
    assert "## Mission" not in prompt
    assert "## Available Tools" not in prompt


def test_to_system_prompt_multiple_services():
    """to_system_prompt renders services grouped by name with read/write."""
    ctx = WorldContextBundle(
        world_description="Multi-service world",
        reality_summary="Ideal",
        behavior_mode="dynamic",
        available_services=[
            {"name": "email_send", "service": "email", "http_method": "POST", "required_params": ["to", "body"]},
            {"name": "email_search", "service": "email", "http_method": "GET", "required_params": ["q"]},
            {"name": "create_event", "service": "calendar", "http_method": "POST", "required_params": ["title"]},
        ],
    )

    prompt = ctx.to_system_prompt()

    assert "### email" in prompt
    assert "action_type: \"email_search\"" in prompt
    assert "action_type: \"email_send\"" in prompt
    assert "### calendar" in prompt
    assert "action_type: \"create_event\"" in prompt


def test_world_context_equality():
    """Frozen models with same values are equal."""
    ctx1 = WorldContextBundle(world_description="World A")
    ctx2 = WorldContextBundle(world_description="World A")
    ctx3 = WorldContextBundle(world_description="World B")

    assert ctx1 == ctx2
    assert ctx1 != ctx3


def test_world_context_serialization():
    """WorldContextBundle can round-trip through JSON."""
    ctx = WorldContextBundle(
        world_description="Test world",
        reality_summary="Ideal",
        behavior_mode="reactive",
        behavior_description="Reacts to input",
        governance_rules_summary="No rules",
        mission="Test mission",
        available_services=[{"name": "svc", "actions": []}],
        reality_dimensions={"info_quality": 0.5},
    )

    data = ctx.model_dump()
    restored = WorldContextBundle(**data)

    assert restored == ctx
