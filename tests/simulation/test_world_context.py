"""Tests for WorldContextBundle."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from terrarium.simulation.world_context import WorldContextBundle


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


def test_to_system_prompt_full():
    """to_system_prompt includes all sections when populated."""
    ctx = WorldContextBundle(
        world_description="Corporate helpdesk simulation.",
        reality_summary="Messy reality with delays.",
        behavior_mode="reactive",
        behavior_description="Responds to agent actions.",
        governance_rules_summary="No PII sharing.",
        mission="Evaluate agent quality.",
        available_services=[
            {
                "name": "helpdesk",
                "actions": [
                    {"name": "reply_ticket"},
                    {"name": "close_ticket"},
                ],
            }
        ],
    )

    prompt = ctx.to_system_prompt()

    assert "## World" in prompt
    assert "Corporate helpdesk simulation." in prompt
    assert "## Reality" in prompt
    assert "Messy reality" in prompt
    assert "## Behavior Mode" in prompt
    assert "reactive: Responds to agent actions." in prompt
    assert "## Governance Rules" in prompt
    assert "No PII sharing." in prompt
    assert "## Mission" in prompt
    assert "Evaluate agent quality." in prompt
    assert "## Available Services" in prompt
    assert "helpdesk: reply_ticket, close_ticket" in prompt


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
    assert "## Governance Rules" not in prompt
    assert "## Mission" not in prompt
    assert "## Available Services" not in prompt


def test_to_system_prompt_multiple_services():
    """to_system_prompt renders multiple services correctly."""
    ctx = WorldContextBundle(
        world_description="Multi-service world",
        reality_summary="Ideal",
        behavior_mode="dynamic",
        available_services=[
            {
                "name": "email",
                "actions": [{"name": "send_email"}, {"name": "list_emails"}],
            },
            {
                "name": "calendar",
                "actions": [{"name": "create_event"}],
            },
        ],
    )

    prompt = ctx.to_system_prompt()

    assert "- email: send_email, list_emails" in prompt
    assert "- calendar: create_event" in prompt


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
