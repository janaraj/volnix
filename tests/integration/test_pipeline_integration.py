"""Integration tests for the full governance pipeline — allow, deny, hold, exhaust, side-effects."""
import pytest
import pytest_asyncio


@pytest.mark.asyncio
async def test_full_pipeline_allow(mock_event_bus, mock_ledger, stub_state_engine):
    ...


@pytest.mark.asyncio
async def test_full_pipeline_permission_deny(mock_event_bus, mock_ledger, stub_state_engine):
    ...


@pytest.mark.asyncio
async def test_full_pipeline_policy_hold(mock_event_bus, mock_ledger, stub_state_engine):
    ...


@pytest.mark.asyncio
async def test_full_pipeline_budget_exhaust(mock_event_bus, mock_ledger, stub_state_engine):
    ...


@pytest.mark.asyncio
async def test_full_pipeline_side_effects(mock_event_bus, mock_ledger, stub_state_engine):
    ...
