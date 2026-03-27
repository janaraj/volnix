"""Tests for terrarium.packs.verified.slack -- backward-compatible smoke tests.

Full test suite lives in tests/packs/verified/test_chat.py.
"""

import pytest

from terrarium.packs.verified.slack.pack import ChatPack


def test_chat_pack_tools():
    pack = ChatPack()
    tools = pack.get_tools()
    assert len(tools) == 16


def test_chat_pack_name():
    pack = ChatPack()
    assert pack.pack_name == "slack"
    assert pack.category == "communication"


@pytest.mark.asyncio
async def test_chat_post_message():
    """Smoke test: posting a message returns a valid proposal."""
    from terrarium.core.types import ToolName

    pack = ChatPack()
    proposal = await pack.handle_action(
        ToolName("chat_postMessage"),
        {"channel_id": "C001", "text": "Hello world"},
        {"channels": [{"id": "C001", "name": "general"}], "messages": []},
    )
    assert proposal.response_body["ok"] is True
