"""Tests for terrarium.llm.providers.acp_client -- ACP stdio JSON-RPC provider."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from terrarium.llm.providers.acp_client import (
    ACPClientProvider,
    _extract_token_usage_from_map,
    _is_notification,
    _is_request,
    _is_response,
)
from terrarium.llm.types import LLMRequest, LLMUsage


# ---------------------------------------------------------------------------
# Unit tests: construction and metadata
# ---------------------------------------------------------------------------


def test_acp_client_init():
    """ACPClientProvider initialises with command, auth_method, and timeout."""
    provider = ACPClientProvider(
        command="codex-acp",
        args=["--flag"],
        auth_method="openai-api-key",
        cwd="/tmp",
        timeout=60.0,
    )
    assert provider._command == "codex-acp"
    assert provider._args == ["--flag"]
    assert provider._auth_method == "openai-api-key"
    assert provider._cwd == "/tmp"
    assert provider._timeout == 60.0


def test_acp_client_init_defaults():
    """ACPClientProvider uses sensible defaults."""
    provider = ACPClientProvider(command="codex-acp")
    assert provider._args == []
    assert provider._auth_method == ""
    assert provider._timeout == 300.0
    assert provider._cwd == os.getcwd()


def test_acp_client_get_info():
    """get_info returns correct ACP metadata."""
    provider = ACPClientProvider(command="codex-acp")
    info = provider.get_info()
    assert info.type == "acp"
    assert info.name == "codex-acp"


def test_acp_client_provider_name():
    """Class-level provider_name is 'acp'."""
    assert ACPClientProvider.provider_name == "acp"


# ---------------------------------------------------------------------------
# Unit tests: message type detection
# ---------------------------------------------------------------------------


def test_is_response():
    assert _is_response({"jsonrpc": "2.0", "id": 1, "result": {}})
    assert not _is_response({"jsonrpc": "2.0", "method": "session/update"})
    assert not _is_response({"jsonrpc": "2.0", "id": 1, "method": "session/request_permission"})


def test_is_notification():
    assert _is_notification({"jsonrpc": "2.0", "method": "session/update", "params": {}})
    assert not _is_notification({"jsonrpc": "2.0", "id": 1, "result": {}})
    assert not _is_notification({"jsonrpc": "2.0", "id": 1, "method": "foo"})


def test_is_request():
    assert _is_request({"jsonrpc": "2.0", "id": 99, "method": "session/request_permission"})
    assert not _is_request({"jsonrpc": "2.0", "id": 1, "result": {}})
    assert not _is_request({"jsonrpc": "2.0", "method": "session/update"})


# ---------------------------------------------------------------------------
# Unit tests: token usage extraction
# ---------------------------------------------------------------------------


def test_extract_token_usage_gemini_style():
    m = {"promptTokenCount": 100, "candidatesTokenCount": 200}
    usage = _extract_token_usage_from_map(m)
    assert usage is not None
    assert usage.prompt_tokens == 100
    assert usage.completion_tokens == 200
    assert usage.total_tokens == 300


def test_extract_token_usage_common_aliases():
    m = {"input_tokens": 50, "output_tokens": 75, "total_tokens": 125}
    usage = _extract_token_usage_from_map(m)
    assert usage is not None
    assert usage.prompt_tokens == 50
    assert usage.completion_tokens == 75
    assert usage.total_tokens == 125


def test_extract_token_usage_nested():
    m = {"usage": {"input_tokens": 10, "output_tokens": 20}}
    usage = _extract_token_usage_from_map(m)
    assert usage is not None
    assert usage.prompt_tokens == 10
    assert usage.completion_tokens == 20


def test_extract_token_usage_empty():
    assert _extract_token_usage_from_map({}) is None
    assert _extract_token_usage_from_map({"foo": "bar"}) is None


# ---------------------------------------------------------------------------
# Unit tests: prompt building
# ---------------------------------------------------------------------------


def test_build_prompt_user_only():
    provider = ACPClientProvider(command="test")
    req = LLMRequest(user_content="hello")
    blocks = provider._build_prompt(req)
    assert blocks == [{"type": "text", "text": "hello"}]


def test_build_prompt_with_system():
    provider = ACPClientProvider(command="test")
    req = LLMRequest(system_prompt="Be brief.", user_content="hello")
    blocks = provider._build_prompt(req)
    assert len(blocks) == 1
    assert "Be brief." in blocks[0]["text"]
    assert "hello" in blocks[0]["text"]


# ---------------------------------------------------------------------------
# Unit tests: session management (no subprocess needed)
# ---------------------------------------------------------------------------


def test_list_sessions_empty():
    provider = ACPClientProvider(command="test")
    assert provider.list_sessions() == []


# ---------------------------------------------------------------------------
# Unit tests: validate_connection when command not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_connection_command_not_found():
    """validate_connection returns False when the command does not exist."""
    provider = ACPClientProvider(command="nonexistent_acp_binary_xyz_999")
    result = await provider.validate_connection()
    assert result is False


# ---------------------------------------------------------------------------
# Unit tests: generate failure when spawn fails
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_spawn_failure():
    """generate returns error when the binary cannot be found/spawned."""
    provider = ACPClientProvider(
        command="nonexistent_acp_binary_xyz_999",
        timeout=5.0,
    )
    req = LLMRequest(user_content="test prompt")
    resp = await provider.generate(req)

    assert resp.error is not None
    assert resp.content == ""
    assert resp.provider == "acp"
    assert resp.latency_ms >= 0


# ---------------------------------------------------------------------------
# Unit tests: generate_in_session with unknown session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_in_session_unknown():
    """generate_in_session returns error for a nonexistent session."""
    provider = ACPClientProvider(command="test")
    resp = await provider.generate_in_session(
        "nonexistent_session", LLMRequest(user_content="test")
    )
    assert resp.error is not None
    assert "not found" in resp.error


# ---------------------------------------------------------------------------
# Unit tests: session/update text extraction
# ---------------------------------------------------------------------------


def test_handle_session_update_direct_text():
    provider = ACPClientProvider(command="test")
    provider._collected_text = []
    provider._handle_notification({
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": "sess_1",
            "update": {
                "sessionUpdate": "text",
                "text": "Hello world",
            },
        },
    })
    assert "Hello world" in provider._collected_text


def test_handle_session_update_message_parts():
    provider = ACPClientProvider(command="test")
    provider._collected_text = []
    provider._handle_notification({
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": "sess_1",
            "update": {"sessionUpdate": "message"},
            "messages": [
                {
                    "parts": [
                        {"text": "Part 1"},
                        {"text": "Part 2"},
                    ]
                }
            ],
        },
    })
    assert "Part 1" in provider._collected_text
    assert "Part 2" in provider._collected_text


def test_handle_session_update_content_list():
    provider = ACPClientProvider(command="test")
    provider._collected_text = []
    provider._handle_notification({
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": "sess_1",
            "update": {
                "sessionUpdate": "content",
                "content": [{"text": "Inside content"}],
            },
        },
    })
    assert "Inside content" in provider._collected_text


# ---------------------------------------------------------------------------
# Unit tests: permission auto-approve
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_permission_request():
    """Auto-approve selects the first 'allow' option."""
    provider = ACPClientProvider(command="test")
    # Mock the stdin/stdout so we can capture the response
    provider._stdin = MagicMock()
    provider._stdin.write = MagicMock()
    provider._stdin.drain = AsyncMock()

    await provider._handle_permission_request(99, {
        "sessionId": "sess_1",
        "toolCall": {"toolCallId": "tc_1"},
        "options": [
            {"optionId": "deny_all", "name": "Deny", "kind": "deny"},
            {"optionId": "allow_once", "name": "Allow once", "kind": "allow_once"},
            {"optionId": "allow_all", "name": "Allow all", "kind": "allow_always"},
        ],
    })

    # Verify a response was written to stdin
    assert provider._stdin.write.called
    written = provider._stdin.write.call_args[0][0].decode()
    msg = json.loads(written)
    assert msg["id"] == 99
    assert msg["result"]["outcome"]["outcome"] == "selected"
    assert msg["result"]["outcome"]["optionId"] == "allow_once"


@pytest.mark.asyncio
async def test_handle_permission_fallback_to_first():
    """Auto-approve falls back to first option when no 'allow' found."""
    provider = ACPClientProvider(command="test")
    provider._stdin = MagicMock()
    provider._stdin.write = MagicMock()
    provider._stdin.drain = AsyncMock()

    await provider._handle_permission_request(50, {
        "sessionId": "sess_1",
        "toolCall": {"toolCallId": "tc_2"},
        "options": [
            {"optionId": "first_opt", "name": "First", "kind": "other"},
        ],
    })

    written = provider._stdin.write.call_args[0][0].decode()
    msg = json.loads(written)
    assert msg["result"]["outcome"]["optionId"] == "first_opt"


# ---------------------------------------------------------------------------
# Unit tests: fs/read_text_file handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_fs_read(tmp_path):
    """fs/read_text_file reads a file and responds with content."""
    test_file = tmp_path / "hello.txt"
    test_file.write_text("Hello from test file!")

    provider = ACPClientProvider(command="test", cwd=str(tmp_path))
    provider._stdin = MagicMock()
    provider._stdin.write = MagicMock()
    provider._stdin.drain = AsyncMock()

    await provider._handle_fs_read(42, {"path": str(test_file)})

    written = provider._stdin.write.call_args[0][0].decode()
    msg = json.loads(written)
    assert msg["id"] == 42
    assert msg["result"]["content"] == "Hello from test file!"


@pytest.mark.asyncio
async def test_handle_fs_read_missing_file():
    """fs/read_text_file responds with error for missing file."""
    provider = ACPClientProvider(command="test")
    provider._stdin = MagicMock()
    provider._stdin.write = MagicMock()
    provider._stdin.drain = AsyncMock()

    await provider._handle_fs_read(43, {"path": "/nonexistent/file.txt"})

    written = provider._stdin.write.call_args[0][0].decode()
    msg = json.loads(written)
    assert msg["id"] == 43
    assert "error" in msg
    assert "message" in msg["error"]


@pytest.mark.asyncio
async def test_handle_fs_read_partial(tmp_path):
    """fs/read_text_file supports line/limit for partial reads."""
    test_file = tmp_path / "lines.txt"
    test_file.write_text("line1\nline2\nline3\nline4\nline5")

    provider = ACPClientProvider(command="test", cwd=str(tmp_path))
    provider._stdin = MagicMock()
    provider._stdin.write = MagicMock()
    provider._stdin.drain = AsyncMock()

    # Read lines 2-3 (line=2, limit=2)
    await provider._handle_fs_read(44, {
        "path": str(test_file),
        "line": 2,
        "limit": 2,
    })

    written = provider._stdin.write.call_args[0][0].decode()
    msg = json.loads(written)
    assert msg["result"]["content"] == "line2\nline3"


# ---------------------------------------------------------------------------
# Unit tests: fs/write_text_file handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_fs_write(tmp_path):
    """fs/write_text_file writes content to a file."""
    target = tmp_path / "output.txt"

    provider = ACPClientProvider(command="test", cwd=str(tmp_path))
    provider._stdin = MagicMock()
    provider._stdin.write = MagicMock()
    provider._stdin.drain = AsyncMock()

    await provider._handle_fs_write(45, {
        "path": str(target),
        "content": "Written by ACP",
    })

    assert target.read_text() == "Written by ACP"
    written = provider._stdin.write.call_args[0][0].decode()
    msg = json.loads(written)
    assert msg["id"] == 45
    assert msg["result"] is None


# ---------------------------------------------------------------------------
# Unit tests: close
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_no_process():
    """close is safe to call when no process is running."""
    provider = ACPClientProvider(command="test")
    await provider.close()  # should not raise


# ---------------------------------------------------------------------------
# Unit tests: no httpx import
# ---------------------------------------------------------------------------


def test_no_httpx_import():
    """ACP provider does not import httpx directly."""
    import inspect
    import terrarium.llm.providers.acp_client as mod

    source = inspect.getsource(mod)
    assert "import httpx" not in source


def test_no_acp_sdk_import():
    """ACP provider does not import acp_sdk (uses raw stdio JSON-RPC)."""
    import inspect
    import terrarium.llm.providers.acp_client as mod

    source = inspect.getsource(mod)
    assert "acp_sdk" not in source


# ---------------------------------------------------------------------------
# Integration test helpers
# ---------------------------------------------------------------------------


def _has_command(cmd: str) -> bool:
    return shutil.which(cmd) is not None


RUN_REAL = os.environ.get("TERRARIUM_RUN_REAL_API_TESTS", "").lower() in (
    "1", "true", "yes",
)

HAS_CODEX_ACP = _has_command("codex-acp")
HAS_GEMINI = _has_command("gemini")

skipif_no_codex_acp = pytest.mark.skipif(
    not (HAS_CODEX_ACP and RUN_REAL),
    reason="codex-acp not installed or TERRARIUM_RUN_REAL_API_TESTS not set",
)

skipif_no_gemini_acp = pytest.mark.skipif(
    not (HAS_GEMINI and RUN_REAL),
    reason="gemini not installed or TERRARIUM_RUN_REAL_API_TESTS not set",
)


# ---------------------------------------------------------------------------
# Real integration tests (skipped unless CLI installed + env flag)
# ---------------------------------------------------------------------------


@skipif_no_codex_acp
@pytest.mark.asyncio
async def test_real_codex_acp_single_turn():
    """Real codex-acp: single-turn prompt via ACP stdio JSON-RPC."""
    provider = ACPClientProvider(
        command="codex-acp",
        auth_method="openai-api-key",
        cwd=os.getcwd(),
        timeout=120.0,
    )
    try:
        resp = await provider.generate(
            LLMRequest(user_content="respond with only the word: terrarium")
        )
        assert resp.error is None, f"codex-acp error: {resp.error}"
        assert "terrarium" in resp.content.lower()
        assert resp.latency_ms > 0
    finally:
        await provider.close()


@skipif_no_codex_acp
@pytest.mark.asyncio
async def test_real_codex_acp_multi_turn():
    """Real codex-acp: multi-turn via ACP sessions."""
    provider = ACPClientProvider(
        command="codex-acp",
        auth_method="openai-api-key",
        cwd=os.getcwd(),
        timeout=120.0,
    )
    try:
        session_id = await provider.create_session()
        assert session_id in provider.list_sessions()

        resp1 = await provider.generate_in_session(
            session_id,
            LLMRequest(user_content="Remember the number 42"),
        )
        assert resp1.error is None, f"Turn 1 error: {resp1.error}"

        resp2 = await provider.generate_in_session(
            session_id,
            LLMRequest(user_content="What number did I ask you to remember? Reply with just the number."),
        )
        assert resp2.error is None, f"Turn 2 error: {resp2.error}"

        await provider.end_session(session_id)
        assert session_id not in provider.list_sessions()
    finally:
        await provider.close()


@skipif_no_gemini_acp
@pytest.mark.asyncio
async def test_real_gemini_acp_single_turn():
    """Real gemini ACP: single-turn prompt."""
    provider = ACPClientProvider(
        command="gemini",
        args=["--experimental-acp"],
        auth_method="",
        cwd=os.getcwd(),
        timeout=120.0,
    )
    try:
        resp = await provider.generate(
            LLMRequest(user_content="respond with only the word: terrarium")
        )
        assert resp.error is None, f"gemini ACP error: {resp.error}"
        assert "terrarium" in resp.content.lower()
        assert resp.latency_ms > 0
    finally:
        await provider.close()
