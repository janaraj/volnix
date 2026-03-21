"""Tests for terrarium.packs.verified.chat — chat tools, visibility, and state machines."""
import pytest
import pytest_asyncio
from terrarium.packs.verified.chat.pack import ChatPack
from terrarium.packs.verified.chat.handlers import handle_chat_send_message
from terrarium.packs.verified.chat.state_machines import CHANNEL_STATES


def test_chat_pack_tools():
    ...


@pytest.mark.asyncio
async def test_chat_send_message():
    ...


@pytest.mark.asyncio
async def test_chat_channel_visibility():
    ...


def test_chat_message_state_machine():
    ...
