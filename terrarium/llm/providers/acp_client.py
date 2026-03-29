"""ACP client provider -- connects to local coding agents via stdio JSON-RPC.

Spawns ACP-compatible CLIs (codex-acp, gemini, claude-agent-acp) as subprocesses
and communicates via JSON-RPC 2.0 over stdin/stdout.

Based on the ACP specification: https://agentclientprotocol.com/
Reference: symphony-go ACPClient implementation.

The client must handle bidirectional messages:
- Sends: initialize, authenticate, session/new, session/prompt
- Receives: responses, session/update notifications, agent requests
- Responds to: session/request_permission (auto-approve), fs/read_text_file,
  fs/write_text_file, terminal/*
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, ClassVar

from terrarium.llm.provider import LLMProvider
from terrarium.llm.types import LLMRequest, LLMResponse, LLMUsage, ProviderInfo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON-RPC message helpers
# ---------------------------------------------------------------------------

def _is_response(msg: dict[str, Any]) -> bool:
    """Message is a response: has 'id', no 'method'."""
    return "id" in msg and "method" not in msg


def _is_notification(msg: dict[str, Any]) -> bool:
    """Message is a notification: has 'method', no 'id'."""
    return "method" in msg and "id" not in msg


def _is_request(msg: dict[str, Any]) -> bool:
    """Message is an agent-initiated request: has both 'id' and 'method'."""
    return "id" in msg and "method" in msg


# ---------------------------------------------------------------------------
# Terminal tracking for terminal/* agent requests
# ---------------------------------------------------------------------------

class _TerminalEntry:
    """Tracks a running terminal command spawned by the agent."""

    __slots__ = ("process", "output", "done", "exit_code")

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self.process = process
        self.output = ""
        self.done = False
        self.exit_code = 0


# ---------------------------------------------------------------------------
# ACPClientProvider
# ---------------------------------------------------------------------------

class ACPClientProvider(LLMProvider):
    """Connects to local coding agents via ACP stdio JSON-RPC.

    Spawns the ACP binary as a subprocess, then communicates over
    stdin (send) / stdout (receive) using newline-delimited JSON-RPC 2.0.

    Supports two modes:

    - Single-turn: :meth:`generate` for one-shot prompt -> response
    - Multi-turn: :meth:`create_session` -> :meth:`generate_in_session`
      -> :meth:`end_session`
    """

    provider_name: ClassVar[str] = "acp"

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        auth_method: str = "",
        cwd: str = "",
        timeout: float = 300.0,
    ) -> None:
        self._command = command
        self._args = args or []
        self._auth_method = auth_method
        self._cwd = cwd or os.getcwd()
        self._timeout = timeout

        # Subprocess state (lazily created)
        self._process: asyncio.subprocess.Process | None = None
        self._stdin: asyncio.StreamWriter | None = None
        self._stdout: asyncio.StreamReader | None = None
        self._stderr_task: asyncio.Task[None] | None = None

        # JSON-RPC ID counter
        self._next_id = 0

        # Session management
        self._session_id: str | None = None
        self._sessions: dict[str, str] = {}  # external-id -> acp-session-id

        # Terminal tracking
        self._terminals: dict[str, _TerminalEntry] = {}
        self._term_counter = 0

        # Collected text from session/update notifications during a prompt
        self._collected_text: list[str] = []

        # Token usage extracted from notifications
        self._last_usage: LLMUsage = LLMUsage()

        # Lock to serialize generate() calls — _collected_text is shared
        # instance state that is cleared at the start of each generate().
        # Concurrent generate() calls would corrupt results without this.
        self._generate_lock = asyncio.Lock()

        # Persistent session — created lazily on first generate() call,
        # reused across all subsequent calls. Cleared on error so next
        # call creates a fresh session. Avoids cold-start overhead per call.
        self._persistent_session: str | None = None

    # ------------------------------------------------------------------
    # Public: single-turn
    # ------------------------------------------------------------------

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """ACP flow with session reuse: spawn once, create session once, prompt.

        The persistent session is created lazily on the first call and
        reused for all subsequent calls.  This avoids the cold-start overhead
        of creating a new Codex agent session per LLM call.

        On error the session is cleared so the next call creates a fresh one.
        """
        async with self._generate_lock:
            start = time.monotonic()
            try:
                await self._ensure_running()

                # Session management: fresh_session=True creates an isolated
                # session (for actor-per-call isolation). Default reuses
                # the persistent session (for compiler efficiency).
                if request.fresh_session:
                    session_id = await self._session_new()
                elif self._persistent_session is None:
                    self._persistent_session = await self._session_new()
                    session_id = self._persistent_session
                else:
                    session_id = self._persistent_session

                # Build prompt content blocks
                prompt = self._build_prompt(request)

                # Send prompt and collect response
                self._collected_text.clear()
                self._last_usage = LLMUsage()
                await self._session_prompt(session_id, prompt)

                content = "".join(self._collected_text).strip()
                latency = (time.monotonic() - start) * 1000

                return LLMResponse(
                    content=content,
                    usage=self._last_usage,
                    model=self._command,
                    provider="acp",
                    latency_ms=latency,
                )
            except Exception as e:
                self._persistent_session = None  # Clear so next call creates fresh
                await self.close()
                latency = (time.monotonic() - start) * 1000
                logger.exception("ACP generate failed")
                return LLMResponse(
                    content="",
                    usage=LLMUsage(),
                    model=self._command,
                    provider="acp",
                    latency_ms=latency,
                    error=str(e),
                )

    # ------------------------------------------------------------------
    # Public: multi-turn session management
    # ------------------------------------------------------------------

    async def create_session(self) -> str:
        """Create a new ACP session and return an external session ID."""
        await self._ensure_running()
        acp_session_id = await self._session_new()
        external_id = f"acp_session_{acp_session_id}"
        self._sessions[external_id] = acp_session_id
        return external_id

    async def generate_in_session(
        self, session_id: str, request: LLMRequest
    ) -> LLMResponse:
        """Generate within an existing ACP session.

        Warning: _collected_text is shared instance state cleared at the start
        of each call.  A lock serializes concurrent calls to prevent data
        corruption.
        """
        async with self._generate_lock:
            start = time.monotonic()

            acp_session_id = self._sessions.get(session_id)
            if acp_session_id is None:
                return LLMResponse(
                    content="",
                    usage=LLMUsage(),
                    model=self._command,
                    provider="acp",
                    latency_ms=0.0,
                    error=f"Session '{session_id}' not found",
                )

            try:
                prompt = self._build_prompt(request)
                self._collected_text.clear()
                self._last_usage = LLMUsage()
                await self._session_prompt(acp_session_id, prompt)

                content = "".join(self._collected_text).strip()
                latency = (time.monotonic() - start) * 1000

                return LLMResponse(
                    content=content,
                    usage=self._last_usage,
                    model=self._command,
                    provider="acp",
                    latency_ms=latency,
                )
            except Exception as e:
                await self.close()  # Kill subprocess on failure
                latency = (time.monotonic() - start) * 1000
                return LLMResponse(
                    content="",
                    usage=LLMUsage(),
                    model=self._command,
                    provider="acp",
                    latency_ms=latency,
                    error=str(e),
                )

    async def end_session(self, session_id: str) -> None:
        """End a conversation session."""
        acp_session_id = self._sessions.pop(session_id, None)
        if acp_session_id is not None:
            try:
                await self._send_notification("session/cancel", {
                    "sessionId": acp_session_id,
                })
            except Exception:
                pass  # best-effort

    def list_sessions(self) -> list[str]:
        """List active external session IDs."""
        return list(self._sessions.keys())

    # ------------------------------------------------------------------
    # Public: connection management
    # ------------------------------------------------------------------

    async def validate_connection(self) -> bool:
        """Try to spawn and initialize the ACP binary."""
        if shutil.which(self._command) is None:
            return False
        try:
            await self._ensure_running()
            return True
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        """ACP agents don't expose model lists; return the command name."""
        return [self._command]

    def get_info(self) -> ProviderInfo:
        """Return provider metadata."""
        return ProviderInfo(name=self._command, type="acp")

    async def close(self) -> None:
        """Terminate the ACP subprocess."""
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            self._stderr_task = None
        if self._stdin is not None:
            self._stdin.close()
            self._stdin = None
        if self._process is not None:
            try:
                self._process.kill()
            except ProcessLookupError:
                pass
            await self._process.wait()
            self._process = None
        self._stdout = None
        self._session_id = None
        self._sessions.clear()
        self._terminals.clear()

    # ------------------------------------------------------------------
    # Private: subprocess lifecycle
    # ------------------------------------------------------------------

    async def _spawn(self) -> None:
        """Launch the ACP binary as a subprocess."""
        cmd_parts = [self._command] + self._args

        # Increase stream buffer limit to 4MB to handle large LLM responses
        # (default 64KB is too small for entity generation JSON)
        self._process = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._cwd,
            limit=4 * 1024 * 1024,  # 4MB buffer for large JSON responses
        )

        self._stdin = self._process.stdin  # type: ignore[assignment]
        self._stdout = self._process.stdout  # type: ignore[assignment]

        # Drain stderr in background
        if self._process.stderr is not None:
            self._stderr_task = asyncio.create_task(
                self._drain_stderr(self._process.stderr)
            )

    async def _ensure_running(self) -> None:
        """Ensure the subprocess is running and initialized."""
        if self._process is None or self._process.returncode is not None:
            await self._spawn()
            await self._initialize()
            if self._auth_method:
                await self._authenticate()

    async def _drain_stderr(self, stream: asyncio.StreamReader) -> None:
        """Read and log stderr lines until EOF."""
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break
                logger.debug("acp stderr: %s", line.decode(errors="replace").rstrip())
        except asyncio.CancelledError:
            pass

    # ------------------------------------------------------------------
    # Private: JSON-RPC send/receive
    # ------------------------------------------------------------------

    def _next_request_id(self) -> int:
        self._next_id += 1
        return self._next_id

    async def _send_request(self, method: str, params: Any) -> int:
        """Send a JSON-RPC request and return the request ID."""
        assert self._stdin is not None, "subprocess not spawned"
        req_id = self._next_request_id()
        msg = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        data = json.dumps(msg, separators=(",", ":")) + "\n"
        logger.debug("acp_send: %s", data.rstrip())
        self._stdin.write(data.encode())
        await self._stdin.drain()
        return req_id

    async def _send_response(self, msg_id: int, result: Any) -> None:
        """Send a JSON-RPC response (for agent-initiated requests)."""
        assert self._stdin is not None, "subprocess not spawned"
        msg = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": result,
        }
        data = json.dumps(msg, separators=(",", ":")) + "\n"
        logger.debug("acp_send_response: %s", data.rstrip())
        self._stdin.write(data.encode())
        await self._stdin.drain()

    async def _send_error_response(self, msg_id: int, code: int, message: str) -> None:
        """Send a JSON-RPC error response (per spec: top-level 'error' key)."""
        assert self._stdin is not None, "subprocess not spawned"
        msg = {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
        line = json.dumps(msg) + "\n"
        self._stdin.write(line.encode())
        await self._stdin.drain()

    async def _send_notification(self, method: str, params: Any) -> None:
        """Send a JSON-RPC notification (no id, no response expected)."""
        assert self._stdin is not None, "subprocess not spawned"
        msg = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        data = json.dumps(msg, separators=(",", ":")) + "\n"
        self._stdin.write(data.encode())
        await self._stdin.drain()

    async def _read_message(self, timeout: float) -> dict[str, Any] | None:
        """Read the next JSON-RPC message from stdout.

        Returns ``None`` on empty/malformed lines. Raises on timeout or EOF.
        """
        assert self._stdout is not None, "subprocess not spawned"
        try:
            line = await asyncio.wait_for(
                self._stdout.readline(), timeout=timeout
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"read timeout after {timeout}s")

        if not line:
            raise ConnectionError("ACP subprocess closed stdout (EOF)")

        text = line.decode(errors="replace").strip()
        if not text:
            return None

        try:
            msg = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("malformed JSON-RPC message: %s", text[:200])
            return None

        logger.debug("acp_recv: method=%s id=%s", msg.get("method"), msg.get("id"))
        return msg

    async def _read_response_by_id(self, req_id: int, timeout: float) -> dict[str, Any]:
        """Read messages until finding the response with the given ID.

        Handles notifications and agent-initiated requests inline.
        """
        deadline = time.monotonic() + timeout

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"response timeout waiting for id={req_id}")

            msg = await self._read_message(remaining)
            if msg is None:
                continue  # empty or malformed, keep reading

            # Check: is this our response?
            if _is_response(msg) and msg["id"] == req_id:
                if "error" in msg and msg["error"] is not None:
                    err = msg["error"]
                    code = err.get("code", -1)
                    message = err.get("message", "unknown error")
                    raise RuntimeError(f"RPC error (code={code}): {message}")
                return msg

            # Handle notifications (no id, has method)
            if _is_notification(msg):
                self._handle_notification(msg)
                continue

            # Handle agent-initiated requests (has id AND method)
            if _is_request(msg):
                await self._handle_agent_request(msg)
                continue

            # Unexpected message shape -- log and skip
            logger.warning("unexpected message shape: %s", json.dumps(msg)[:200])

    # ------------------------------------------------------------------
    # Private: ACP protocol steps
    # ------------------------------------------------------------------

    async def _initialize(self) -> dict[str, Any]:
        """Perform the ACP initialize handshake."""
        params = {
            "protocolVersion": 1,
            "clientInfo": {
                "name": "terrarium",
                "version": "0.1.0",
            },
            "clientCapabilities": {
                "fs": {
                    "readTextFile": True,
                    "writeTextFile": True,
                },
                "terminal": True,
            },
        }
        req_id = await self._send_request("initialize", params)
        resp = await self._read_response_by_id(req_id, timeout=self._timeout)
        logger.info(
            "ACP initialized: %s",
            json.dumps(resp.get("result", {}), indent=2)[:300],
        )
        return resp

    async def _authenticate(self) -> dict[str, Any]:
        """Send the authenticate request if an auth method is configured."""
        params: dict[str, Any] = {"methodId": self._auth_method}
        req_id = await self._send_request("authenticate", params)
        resp = await self._read_response_by_id(req_id, timeout=self._timeout)
        logger.info("ACP authenticated with method=%s", self._auth_method)
        return resp

    async def _session_new(self) -> str:
        """Create a new ACP session and return the session ID."""
        params = {
            "cwd": self._cwd,
            "mcpServers": [],
        }
        req_id = await self._send_request("session/new", params)
        resp = await self._read_response_by_id(req_id, timeout=self._timeout)

        result = resp.get("result", {})
        session_id = result.get("sessionId", "")
        if not session_id:
            raise RuntimeError("session/new returned empty sessionId")

        # Set yolo mode (auto-approve all tools)
        await self._set_mode(session_id, "yolo")

        logger.info("ACP session created: %s", session_id)
        return session_id

    async def _set_mode(self, session_id: str, mode_id: str) -> None:
        """Switch the agent to a different operating mode."""
        try:
            req_id = await self._send_request("session/set_mode", {
                "sessionId": session_id,
                "modeId": mode_id,
            })
            await self._read_response_by_id(req_id, timeout=min(self._timeout, 30.0))
            logger.info("ACP mode set: %s for session %s", mode_id, session_id)
        except Exception as e:
            logger.warning("session/set_mode failed (non-fatal): %s", e)

    async def _session_prompt(
        self,
        session_id: str,
        prompt: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Send a prompt and wait for the turn to complete.

        Collects text from session/update notifications into
        ``self._collected_text`` while waiting for the response.
        """
        params = {
            "sessionId": session_id,
            "prompt": prompt,
        }
        req_id = await self._send_request("session/prompt", params)
        resp = await self._read_response_by_id(req_id, timeout=self._timeout)
        return resp

    # ------------------------------------------------------------------
    # Private: notification handling
    # ------------------------------------------------------------------

    def _handle_notification(self, msg: dict[str, Any]) -> None:
        """Process an incoming notification message."""
        method = msg.get("method", "")
        params = msg.get("params", {})

        if method == "session/update":
            self._handle_session_update(params)
            return

        # Token usage notifications (Gemini sends extNotification or tokenUsage)
        if method == "extNotification" or "tokenUsage" in method:
            self._extract_token_usage(params)
            return

        logger.debug("unhandled notification: %s", method)

    def _handle_session_update(self, params: dict[str, Any]) -> None:
        """Extract text from a session/update notification."""
        update = params.get("update", {})

        # Direct text field on the update
        text = update.get("text", "")
        if text:
            self._collected_text.append(text)

        # Content field — may be a string, a dict with "text", or a list of dicts
        content = update.get("content")
        if isinstance(content, str) and content:
            self._collected_text.append(content)
        elif isinstance(content, dict) and content.get("text"):
            # e.g., {"type": "text", "text": "terrarium"} from agent_message_chunk
            self._collected_text.append(content["text"])
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("text"):
                    self._collected_text.append(item["text"])

        # Message parts: params.messages[].parts[].text
        messages = params.get("messages", [])
        for message in messages:
            parts = message.get("parts", [])
            for part in parts:
                part_text = part.get("text", "")
                if part_text:
                    self._collected_text.append(part_text)

    def _extract_token_usage(self, params: dict[str, Any]) -> None:
        """Try to extract token usage from a notification payload."""
        usage = _extract_token_usage_from_map(params)
        if usage is not None:
            self._last_usage = usage

    # ------------------------------------------------------------------
    # Private: agent request handling
    # ------------------------------------------------------------------

    async def _handle_agent_request(self, msg: dict[str, Any]) -> None:
        """Handle an agent-initiated request and send back a response."""
        method = msg.get("method", "")
        msg_id = msg["id"]

        if method == "session/request_permission":
            await self._handle_permission_request(msg_id, msg.get("params", {}))
        elif method == "fs/read_text_file":
            await self._handle_fs_read(msg_id, msg.get("params", {}))
        elif method == "fs/write_text_file":
            await self._handle_fs_write(msg_id, msg.get("params", {}))
        elif method.startswith("terminal/"):
            await self._handle_terminal(method, msg_id, msg.get("params", {}))
        else:
            logger.warning("unhandled agent request: %s", method)
            await self._send_error_response(msg_id, -32601, f"method not supported: {method}")

    async def _handle_permission_request(
        self, msg_id: int, params: dict[str, Any]
    ) -> None:
        """Auto-approve permission requests by selecting an 'allow' option."""
        options = params.get("options", [])

        # Find first "allow" option
        option_id = ""
        for opt in options:
            kind = opt.get("kind", "")
            if "allow" in kind:
                option_id = opt.get("optionId", "")
                break

        # Fall back to first option
        if not option_id and options:
            option_id = options[0].get("optionId", "")

        if not option_id:
            await self._send_error_response(msg_id, -32602, "no permission options to select from")
            return

        tool_call = params.get("toolCall", {})
        logger.info(
            "auto-approving permission: tool_call_id=%s option_id=%s",
            tool_call.get("toolCallId"),
            option_id,
        )

        await self._send_response(msg_id, {
            "outcome": {
                "outcome": "selected",
                "optionId": option_id,
            },
        })

    async def _handle_fs_read(self, msg_id: int, params: dict[str, Any]) -> None:
        """Handle fs/read_text_file: read a file and respond with its content."""
        file_path = params.get("path") or params.get("filePath", "")

        if not file_path:
            await self._send_error_response(msg_id, -32602, "path is required")
            return

        resolved = Path(file_path).resolve()
        allowed = Path(self._cwd).resolve()
        if not resolved.is_relative_to(allowed):
            await self._send_error_response(msg_id, -32602, f"Path {file_path} is outside working directory")
            return

        logger.debug("fs/read_text_file: %s", file_path)

        try:
            content = Path(file_path).read_text(errors="replace")
        except Exception as e:
            logger.debug("fs/read_text_file failed: %s %s", file_path, e)
            await self._send_error_response(msg_id, -32603, str(e))
            return

        # Handle line/limit for partial reads
        line_start = params.get("line")
        limit = params.get("limit")

        if line_start is not None or limit is not None:
            lines = content.split("\n")
            start = max(0, (line_start or 1) - 1)  # 1-based to 0-based
            if start >= len(lines):
                content = ""
            else:
                end = len(lines)
                if limit is not None and limit > 0:
                    end = min(start + limit, len(lines))
                content = "\n".join(lines[start:end])

        await self._send_response(msg_id, {"content": content})

    async def _handle_fs_write(self, msg_id: int, params: dict[str, Any]) -> None:
        """Handle fs/write_text_file: write content to a file."""
        file_path = params.get("path") or params.get("filePath", "")
        content = params.get("content", "")

        if not file_path:
            await self._send_error_response(msg_id, -32602, "path is required")
            return

        resolved = Path(file_path).resolve()
        allowed = Path(self._cwd).resolve()
        if not resolved.is_relative_to(allowed):
            await self._send_error_response(msg_id, -32602, f"Path {file_path} is outside working directory")
            return

        logger.debug("fs/write_text_file: %s", file_path)

        try:
            p = Path(file_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        except Exception as e:
            await self._send_error_response(msg_id, -32603, str(e))
            return

        # ACP spec: successful write returns null/None result
        await self._send_response(msg_id, None)

    async def _handle_terminal(
        self, method: str, msg_id: int, params: dict[str, Any]
    ) -> None:
        """Handle terminal/* agent requests."""
        if method == "terminal/create":
            command = params.get("command", "")
            args = params.get("args", [])
            cwd = params.get("cwd", "")

            try:
                proc = await asyncio.create_subprocess_exec(
                    command, *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=cwd or None,
                )
            except Exception as e:
                await self._send_response(msg_id, {"error": str(e)})
                return

            self._term_counter += 1
            term_id = f"term_{self._term_counter}"
            entry = _TerminalEntry(proc)
            self._terminals[term_id] = entry

            # Wait in background and collect output; suppress unhandled task warnings
            task = asyncio.create_task(self._terminal_wait(term_id, entry))
            task.add_done_callback(
                lambda t: t.exception() if not t.cancelled() and t.exception() else None
            )

            logger.debug("terminal/create: id=%s command=%s args=%s", term_id, command, args)
            await self._send_response(msg_id, {"terminalId": term_id})

        elif method == "terminal/output":
            term_id = params.get("terminalId", "")
            entry = self._terminals.get(term_id)
            if entry is None:
                await self._send_response(msg_id, {"error": "unknown terminal"})
                return
            await self._send_response(msg_id, {
                "output": entry.output,
                "finished": entry.done,
            })

        elif method == "terminal/wait_for_exit":
            term_id = params.get("terminalId", "")
            entry = self._terminals.get(term_id)
            if entry is None:
                await self._send_response(msg_id, {"error": "unknown terminal"})
                return

            # Wait for completion with timeout (60s)
            for _ in range(600):
                if entry.done:
                    break
                await asyncio.sleep(0.1)

            await self._send_response(msg_id, {
                "output": entry.output,
                "exitCode": entry.exit_code,
            })

        elif method == "terminal/release":
            term_id = params.get("terminalId", "")
            self._terminals.pop(term_id, None)
            await self._send_response(msg_id, {"success": True})

        elif method == "terminal/kill":
            term_id = params.get("terminalId", "")
            entry = self._terminals.get(term_id)
            if entry is not None and entry.process.returncode is None:
                try:
                    entry.process.kill()
                except ProcessLookupError:
                    pass
            await self._send_response(msg_id, {"success": True})

        else:
            await self._send_response(msg_id, {
                "error": f"unknown terminal method: {method}",
            })

    async def _terminal_wait(self, term_id: str, entry: _TerminalEntry) -> None:
        """Background task: wait for a terminal process and collect output."""
        try:
            stdout_data, _ = await entry.process.communicate()
            entry.output = stdout_data.decode(errors="replace") if stdout_data else ""
            entry.exit_code = entry.process.returncode or 0
        except Exception:
            entry.exit_code = 1
        finally:
            entry.done = True

    # ------------------------------------------------------------------
    # Private: helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(request: LLMRequest) -> list[dict[str, str]]:
        """Build ACP content blocks from a request."""
        text = request.user_content
        if request.system_prompt:
            text = f"{request.system_prompt}\n\n{text}"
        return [{"type": "text", "text": text}]


# ---------------------------------------------------------------------------
# Token usage extraction
# ---------------------------------------------------------------------------

def _extract_token_usage_from_map(m: dict[str, Any]) -> LLMUsage | None:
    """Try to find token counts in a notification payload.

    Handles Gemini-style (promptTokenCount/candidatesTokenCount) and
    common aliases (input_tokens/output_tokens).
    """
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    found = False

    # Gemini-style
    if "promptTokenCount" in m:
        prompt_tokens = _to_int(m["promptTokenCount"])
        found = True
    if "candidatesTokenCount" in m:
        completion_tokens = _to_int(m["candidatesTokenCount"])
        found = True

    # Common aliases
    if "input_tokens" in m:
        prompt_tokens = _to_int(m["input_tokens"])
        found = True
    if "output_tokens" in m:
        completion_tokens = _to_int(m["output_tokens"])
        found = True
    if "total_tokens" in m:
        total_tokens = _to_int(m["total_tokens"])
        found = True
    if "totalTokenCount" in m:
        total_tokens = _to_int(m["totalTokenCount"])
        found = True

    # Check nested objects only if no top-level usage keys were found
    if not found:
        for key in ("usage", "data", "params"):
            nested = m.get(key)
            if isinstance(nested, dict):
                inner = _extract_token_usage_from_map(nested)
                if inner is not None:
                    return inner
        return None

    if total_tokens == 0:
        total_tokens = prompt_tokens + completion_tokens

    return LLMUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )


def _to_int(v: Any) -> int:
    """Convert a value to int, handling float/int/str."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0
