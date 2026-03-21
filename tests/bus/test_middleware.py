"""Tests for terrarium.bus.middleware — before/after hooks, logging, metrics."""
import pytest
import pytest_asyncio
from terrarium.bus.middleware import MiddlewareChain


@pytest.mark.asyncio
async def test_middleware_chain_before():
    ...


@pytest.mark.asyncio
async def test_middleware_chain_after():
    ...


@pytest.mark.asyncio
async def test_logging_middleware():
    ...


@pytest.mark.asyncio
async def test_metrics_middleware():
    ...


@pytest.mark.asyncio
async def test_middleware_drop_event():
    ...
