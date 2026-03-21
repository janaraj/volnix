"""Integration tests for world compilation and simulation run lifecycle."""
import pytest
import pytest_asyncio


@pytest.mark.asyncio
async def test_compile_and_run_simple_world(test_config, mock_llm_provider):
    ...


@pytest.mark.asyncio
async def test_run_produces_valid_report(test_config, mock_llm_provider):
    ...


@pytest.mark.asyncio
async def test_run_governance_scores(test_config, mock_llm_provider):
    ...


@pytest.mark.asyncio
async def test_compile_world_with_reality_preset():
    """Test world compilation with reality preset applied."""
    ...


@pytest.mark.asyncio
async def test_governed_vs_ungoverned_comparison():
    """Test running same world in governed and ungoverned modes."""
    ...
