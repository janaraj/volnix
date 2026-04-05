"""CLI subprocess provider -- invokes local CLI tools as LLM providers.

Supports different CLI invocation patterns:
- claude: `claude -p "prompt" --model MODEL`
- codex:  `codex exec "prompt"`
- gemini: `gemini "prompt"`

The prompt is passed as a command-line argument (not stdin).
Each CLI has its own flag conventions configured via `args`.

Config examples in volnix.toml:
    [llm.providers.claude_cli]
    type = "cli"
    command = "claude"
    args = ["-p"]
    default_model = "claude-sonnet-4-6"

    [llm.providers.codex_cli]
    type = "cli"
    command = "codex"
    args = ["exec"]

    [llm.providers.gemini_cli]
    type = "cli"
    command = "gemini"
    args = []
"""

from __future__ import annotations

import asyncio
import shutil
import time
from typing import ClassVar

from volnix.llm.provider import LLMProvider
from volnix.llm.types import LLMRequest, LLMResponse, LLMUsage, ProviderInfo


class CLISubprocessProvider(LLMProvider):
    """LLM provider that invokes a local CLI command as a subprocess.

    The prompt is passed as a command-line argument after the configured args.
    Model selection uses --model flag (configurable via model_flag).
    """

    provider_name: ClassVar[str] = "cli"

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        default_model: str = "",
        timeout: float = 120.0,
        model_flag: str = "--model",
    ) -> None:
        self._command = command
        self._args = args or []
        self._default_model = default_model
        self._timeout = timeout
        self._model_flag = model_flag

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Invoke the CLI with the prompt as a command argument.

        Command is built as: [command] [args...] [--model MODEL] "prompt"
        The prompt is the LAST argument.

        Args:
            request: The LLM request payload.

        Returns:
            The LLM response from the CLI tool's stdout.
        """
        start = time.monotonic()
        prompt = (
            f"{request.system_prompt}\n\n{request.user_content}"
            if request.system_prompt
            else request.user_content
        )

        # Build command: [command] [args...] [--model MODEL] "prompt"
        cmd = [self._command] + list(self._args)
        model = request.model_override or self._default_model
        if model and self._model_flag:
            cmd.extend([self._model_flag, model])
        # Prompt goes as the last argument
        cmd.append(prompt)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self._timeout,
            )
            latency = (time.monotonic() - start) * 1000

            if proc.returncode != 0:
                error_msg = (
                    stderr.decode().strip()
                    or f"Command exited with code {proc.returncode}"
                )
                return LLMResponse(
                    content="",
                    usage=LLMUsage(),
                    model=model or self._command,
                    provider="cli",
                    latency_ms=latency,
                    error=error_msg,
                )

            content = stdout.decode().strip()
            # Estimate tokens from word count
            est_tokens = len(content.split())
            usage = LLMUsage(
                completion_tokens=est_tokens,
                total_tokens=est_tokens,
            )
            return LLMResponse(
                content=content,
                usage=usage,
                model=model or self._command,
                provider="cli",
                latency_ms=latency,
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass
            latency = (time.monotonic() - start) * 1000
            return LLMResponse(
                content="",
                usage=LLMUsage(),
                model=model or self._command,
                provider="cli",
                latency_ms=latency,
                error=f"Command timed out after {self._timeout}s",
            )
        except FileNotFoundError:
            latency = (time.monotonic() - start) * 1000
            return LLMResponse(
                content="",
                usage=LLMUsage(),
                model=self._command,
                provider="cli",
                latency_ms=latency,
                error=f"Command '{self._command}' not found",
            )

    async def validate_connection(self) -> bool:
        """Check that the command exists on the system PATH."""
        return shutil.which(self._command) is not None

    async def list_models(self) -> list[str]:
        """Return the default model, if any."""
        return [self._default_model] if self._default_model else []

    def get_info(self) -> ProviderInfo:
        """Return provider metadata."""
        return ProviderInfo(name=self._command, type="cli")
