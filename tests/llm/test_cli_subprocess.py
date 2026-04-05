"""Tests for volnix.llm.providers.cli_subprocess -- CLI subprocess provider."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from volnix.llm.providers.cli_subprocess import CLISubprocessProvider
from volnix.llm.types import LLMRequest


def test_cli_subprocess_init():
    """CLISubprocessProvider initialises with command, args, and model."""
    provider = CLISubprocessProvider(
        command="claude",
        args=["--quiet"],
        default_model="claude-sonnet",
    )
    assert provider._command == "claude"
    assert provider._args == ["--quiet"]
    assert provider._default_model == "claude-sonnet"


def test_cli_subprocess_timeout_configurable():
    """CLISubprocessProvider accepts a custom timeout."""
    provider = CLISubprocessProvider(command="my-tool", timeout=120.0)
    assert provider._timeout == 120.0

    provider_default = CLISubprocessProvider(command="my-tool")
    assert provider_default._timeout == 120.0  # default is 120s for CLI tools


@pytest.mark.asyncio
async def test_cli_subprocess_generate_success():
    """Successful CLI invocation returns stdout content."""
    provider = CLISubprocessProvider(command="my-llm-tool")

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"The answer is 42", b""))

    with patch("volnix.llm.providers.cli_subprocess.asyncio.create_subprocess_exec", return_value=mock_proc):
        req = LLMRequest(user_content="What is the answer?")
        resp = await provider.generate(req)

    assert resp.content == "The answer is 42"
    assert resp.provider == "cli"
    assert resp.usage.completion_tokens > 0
    assert resp.error is None


@pytest.mark.asyncio
async def test_cli_subprocess_command_not_found():
    """Provider returns error when command is not found."""
    provider = CLISubprocessProvider(command="nonexistent_command_xyz_123")
    req = LLMRequest(user_content="test")
    resp = await provider.generate(req)
    assert resp.error is not None
    assert "not found" in resp.error
    assert resp.content == ""
    assert resp.provider == "cli"


@pytest.mark.asyncio
async def test_cli_subprocess_error_exit():
    """Provider returns error on non-zero exit code."""
    provider = CLISubprocessProvider(command="my-tool")

    mock_proc = AsyncMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"something went wrong"))

    with patch("volnix.llm.providers.cli_subprocess.asyncio.create_subprocess_exec", return_value=mock_proc):
        resp = await provider.generate(LLMRequest(user_content="test"))

    assert resp.error is not None
    assert "something went wrong" in resp.error
    assert resp.content == ""


@pytest.mark.asyncio
async def test_cli_subprocess_timeout():
    """Provider returns error when the command times out."""
    provider = CLISubprocessProvider(command="my-tool")

    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())

    with patch("volnix.llm.providers.cli_subprocess.asyncio.create_subprocess_exec", return_value=mock_proc):
        with patch("volnix.llm.providers.cli_subprocess.asyncio.wait_for", side_effect=asyncio.TimeoutError()):
            resp = await provider.generate(LLMRequest(user_content="test"))

    assert resp.error is not None
    assert "timed out" in resp.error.lower() or "timeout" in resp.error.lower()
    assert resp.content == ""


@pytest.mark.asyncio
async def test_cli_subprocess_validate_connection():
    """validate_connection checks shutil.which for the command."""
    provider = CLISubprocessProvider(command="python3")
    result = await provider.validate_connection()
    assert result is True

    provider2 = CLISubprocessProvider(command="nonexistent_xyz_789")
    result2 = await provider2.validate_connection()
    assert result2 is False


def test_cli_subprocess_get_info():
    """get_info returns CLI provider metadata."""
    provider = CLISubprocessProvider(command="my-tool", default_model="my-model")
    info = provider.get_info()
    assert info.name == "my-tool"
    assert info.type == "cli"


# ─── Real CLI Integration Tests ──────────────────────────────────────

import os
import shutil

RUN_REAL = os.environ.get("VOLNIX_RUN_REAL_API_TESTS", "").lower() in ("1", "true", "yes")

HAS_CLAUDE = shutil.which("claude") is not None
HAS_CODEX = shutil.which("codex") is not None
HAS_GEMINI = shutil.which("gemini") is not None

skipif_no_claude = pytest.mark.skipif(
    not (HAS_CLAUDE and RUN_REAL), reason="claude CLI not installed or VOLNIX_RUN_REAL_API_TESTS not set"
)
skipif_no_codex = pytest.mark.skipif(
    not (HAS_CODEX and RUN_REAL), reason="codex CLI not installed or VOLNIX_RUN_REAL_API_TESTS not set"
)
skipif_no_gemini = pytest.mark.skipif(
    not (HAS_GEMINI and RUN_REAL), reason="gemini CLI not installed or VOLNIX_RUN_REAL_API_TESTS not set"
)


@skipif_no_claude
@pytest.mark.asyncio
async def test_real_claude_cli():
    """Real Claude CLI: invoke claude -p with a simple prompt."""
    provider = CLISubprocessProvider(
        command="claude", args=["-p"], default_model="claude-sonnet-4-6", timeout=60.0,
    )
    resp = await provider.generate(LLMRequest(user_content="respond with only the word: volnix"))
    assert resp.error is None, f"Claude CLI error: {resp.error}"
    assert "volnix" in resp.content.lower()
    assert resp.latency_ms > 0


@skipif_no_codex
@pytest.mark.asyncio
async def test_real_codex_cli():
    """Real Codex CLI: invoke codex exec with a simple prompt."""
    provider = CLISubprocessProvider(
        command="codex", args=["exec"], default_model="", timeout=60.0, model_flag="",
    )
    resp = await provider.generate(LLMRequest(user_content="respond with only the word: volnix"))
    assert resp.error is None, f"Codex CLI error: {resp.error}"
    assert "volnix" in resp.content.lower()
    assert resp.latency_ms > 0


@skipif_no_gemini
@pytest.mark.asyncio
async def test_real_gemini_cli():
    """Real Gemini CLI: invoke gemini with a simple prompt."""
    provider = CLISubprocessProvider(
        command="gemini", args=[], default_model="", timeout=60.0, model_flag="",
    )
    resp = await provider.generate(LLMRequest(user_content="respond with only the word: volnix"))
    assert resp.error is None, f"Gemini CLI error: {resp.error}"
    assert "volnix" in resp.content.lower()
    assert resp.latency_ms > 0


@skipif_no_claude
@pytest.mark.asyncio
async def test_real_claude_cli_multi_turn_via_conversation():
    """Real Claude CLI multi-turn: verify context retention through ConversationManager."""
    from volnix.llm.conversation import ConversationManager

    class CLIRouter:
        def __init__(self):
            self._provider = CLISubprocessProvider(
                command="claude", args=["-p"], default_model="claude-sonnet-4-6", timeout=60.0,
            )
        def get_provider_for(self, engine_name, use_case="default"):
            return self._provider
        async def route(self, request, engine_name, use_case="default"):
            return await self._provider.generate(request)

    conv = ConversationManager()
    router = CLIRouter()
    sid = conv.create_session(system_prompt="You have perfect memory. Always recall exactly what the user told you.")

    resp1 = await conv.generate(sid, router, "Remember this code: CLITEST99", engine_name="test")
    assert resp1.error is None, f"Turn 1 error: {resp1.error}"

    resp2 = await conv.generate(sid, router, "What was the code I told you to remember? Reply with just the code.", engine_name="test")
    assert resp2.error is None, f"Turn 2 error: {resp2.error}"
    assert "CLITEST99" in resp2.content.upper(), f"CLI did not retain context. Response: {resp2.content}"

    conv.end_session(sid)
