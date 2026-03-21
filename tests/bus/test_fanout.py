"""Tests for terrarium.bus.fanout — fan-out delivery and wildcard matching."""
import pytest
import pytest_asyncio
from terrarium.bus.fanout import TopicFanout


@pytest.mark.asyncio
async def test_fanout_add_subscriber():
    ...


@pytest.mark.asyncio
async def test_fanout_remove_subscriber():
    ...


@pytest.mark.asyncio
async def test_fanout_delivers_to_matching():
    ...


@pytest.mark.asyncio
async def test_fanout_wildcard():
    ...


def test_fanout_subscriber_count():
    ...
