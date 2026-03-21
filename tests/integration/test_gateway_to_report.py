"""Integration tests for the full gateway-to-report flow including ledger capture."""
import pytest
import pytest_asyncio


@pytest.mark.asyncio
async def test_gateway_request_to_pipeline(mock_event_bus, mock_ledger, stub_state_engine):
    ...


@pytest.mark.asyncio
async def test_full_flow_gateway_to_report(mock_event_bus, mock_ledger, stub_state_engine, mock_llm_provider):
    ...


@pytest.mark.asyncio
async def test_ledger_captures_all_steps(mock_event_bus, mock_ledger, stub_state_engine):
    ...
