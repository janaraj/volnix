"""OpenAI-compatible LLM provider for the Volnix framework.

Implements the :class:`~volnix.llm.provider.LLMProvider` interface using
the OpenAI Chat Completions API format.  Works with any service exposing the
OpenAI-compatible endpoint, including:

- OpenAI
- Google Gemini (via OpenAI-compatible endpoint)
- Together AI
- Groq
- Ollama
- vLLM
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, ClassVar

import openai
from openai import AsyncOpenAI

from volnix.llm._tool_pairing import repair_tool_call_pairing as _repair_tool_call_pairing
from volnix.llm.provider import LLMProvider
from volnix.llm.types import LLMRequest, LLMResponse, LLMUsage, ProviderInfo

logger = logging.getLogger(__name__)


_OPENAI_TOOL_CALL_KEYS = frozenset({"id", "type", "function"})


def _sanitize_messages_for_openai(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Strip framework-only keys before handing messages to the OpenAI SDK.

    OpenAI's chat completions API rejects unknown fields inside ``tool_calls``
    entries with "Additional properties are not allowed". We defensively strip:

    - Any top-level message-dict key starting with ``_`` (framework-only,
      e.g. ``_provider_metadata`` used to round-trip Anthropic extended-
      thinking blocks on the next turn — harmless to OpenAI if the field
      is never sent).
    - The ``provider_metadata`` key inside each ``tool_calls`` entry (used
      to round-trip Gemini ``thought_signature`` via ToolCall).

    After key stripping, :func:`_repair_tool_call_pairing` enforces the
    strict tool_call ↔ tool-response pairing OpenAI requires.

    A shallow copy is made so the original message dicts are never mutated
    (callers may retain references to them).
    """
    result: list[dict[str, Any]] = []
    for m in messages:
        # Strip top-level framework-only keys (underscore-prefixed).
        m_copy = {k: v for k, v in m.items() if not k.startswith("_")}
        if m_copy.get("tool_calls"):
            m_copy["tool_calls"] = [
                {k: v for k, v in tc.items() if k in _OPENAI_TOOL_CALL_KEYS}
                for tc in m_copy["tool_calls"]
            ]
        result.append(m_copy)
    return _repair_tool_call_pairing(result)


def _fix_bare_arrays(schema: Any) -> Any:
    """Recursively add ``items`` to bare array schemas for OpenAI compatibility.

    OpenAI structured output requires every ``{"type": "array"}`` to include
    an ``items`` definition.  Many service pack schemas omit this (e.g.
    ``"data": {"type": "array"}``).  This function adds a permissive
    ``"items": {"type": "object"}`` default so the schema passes validation.
    """
    if not isinstance(schema, dict):
        return schema
    result: dict[str, Any] = {}
    for k, v in schema.items():
        if isinstance(v, dict):
            if v.get("type") == "array" and "items" not in v:
                v = {**v, "items": {"type": "object"}}
            result[k] = _fix_bare_arrays(v)
        else:
            result[k] = v
    return result


class OpenAICompatibleProvider(LLMProvider):
    """LLM provider for any OpenAI-compatible Chat Completions API."""

    provider_name: ClassVar[str] = "openai_compatible"

    # Cost per 1M tokens: (input_usd, output_usd). [assumed] — these are
    # approximate public list prices and should be kept in sync with vendor
    # pricing pages. Unknown models fall back to the gpt-5.4-mini rate so
    # the tracker still records a non-zero cost.
    # NOTE: Local providers (Ollama, vLLM) have zero marginal API cost —
    # `_estimate_cost` short-circuits to 0.0 for `self._is_local`.
    COST_TABLE: ClassVar[dict[str, tuple[float, float]]] = {
        # OpenAI
        "gpt-5.4-mini": (0.25, 2.00),
        "gpt-5.4": (2.50, 10.00),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4o": (2.50, 10.00),
        # Gemini via OpenAI-compatible endpoint (if used)
        "gemini-3-flash-preview": (0.075, 0.30),
        "gemini-3.1-pro": (1.25, 5.00),
    }
    _DEFAULT_RATE: ClassVar[tuple[float, float]] = (0.25, 2.00)

    def __init__(
        self,
        api_key: str | None,
        base_url: str,
        default_model: str = "gpt-5.4-mini",
        timeout: float = 300.0,
    ) -> None:
        # OpenAI SDK requires a non-empty api_key string.
        # For local endpoints (Ollama, vLLM) that don't need auth,
        # we use a placeholder that satisfies the SDK's validation.
        import httpx

        # Local providers (Ollama, vLLM) need longer timeouts and
        # don't support json_schema structured output.
        self._is_local = "localhost" in base_url or "127.0.0.1" in base_url
        if self._is_local:
            t = httpx.Timeout(connect=30.0, read=max(timeout, 600.0), write=30.0, pool=30.0)
        else:
            t = httpx.Timeout(connect=10.0, read=timeout, write=10.0, pool=10.0)
        self._client = AsyncOpenAI(
            api_key=api_key if api_key else "local-no-auth-needed",
            base_url=base_url,
            timeout=t,
        )
        self._default_model = default_model
        self._base_url = base_url

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Send a request to the OpenAI-compatible endpoint.

        Args:
            request: The LLM request payload.

        Returns:
            The LLM response.
        """
        model = request.model_override or self._default_model
        start = time.monotonic()
        try:
            if request.messages:
                messages: list[dict[str, Any]] = _sanitize_messages_for_openai(request.messages)
            else:
                messages: list[dict[str, Any]] = []
                if request.system_prompt:
                    messages.append({"role": "system", "content": request.system_prompt})
                messages.append({"role": "user", "content": request.user_content})

            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": request.temperature,
            }

            # Prompt cache key groups calls sharing the same system prompt prefix.
            # All actors in a simulation share the same world system prompt,
            # so they share cache hits. Different worlds get different keys.
            if request.cache_system_prompt and request.system_prompt:
                import hashlib

                kwargs["prompt_cache_key"] = hashlib.sha256(
                    request.system_prompt.encode()
                ).hexdigest()[:16]

            # Structured output: force valid JSON matching the schema.
            # Local providers (Ollama, vLLM) don't support json_schema —
            # use simple json_object mode instead. The prompt still asks
            # for JSON, and the parser handles raw JSON content.
            _unwrap_array = False
            if request.output_schema:
                if self._is_local:
                    # Simple JSON mode — no schema enforcement
                    kwargs["response_format"] = {"type": "json_object"}
                    logger.info("Local provider: using json_object mode (no schema enforcement)")
                else:
                    schema = _fix_bare_arrays(request.output_schema)
                    if schema.get("type") == "array":
                        # Wrap array in object: {"items": [...]}
                        schema = {
                            "type": "object",
                            "properties": {"items": schema},
                            "required": ["items"],
                        }
                        _unwrap_array = True
                    kwargs["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "response",
                            "schema": schema,
                            "strict": False,
                        },
                    }
                    schema_type = request.output_schema.get("type", "?")
                    logger.info("OpenAI structured output enabled (schema type=%s)", schema_type)

            # Native tool calling: pass tool definitions so the LLM returns
            # structured tool_calls instead of raw JSON text.
            if request.tools:
                kwargs["tools"] = [
                    {
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.parameters,
                        },
                    }
                    for t in request.tools
                ]
                kwargs["tool_choice"] = request.tool_choice or "required"

            # Newer OpenAI models (gpt-5.x, o-series) use max_completion_tokens
            # instead of max_tokens. Try new parameter first, fall back to old,
            # then try without either (some models reject both when using
            # structured output / response_format).
            kwargs["max_completion_tokens"] = request.max_tokens
            try:
                response = await self._client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
            except (openai.BadRequestError, TypeError, KeyError):
                # Fall back: try max_tokens (older models)
                kwargs.pop("max_completion_tokens", None)
                kwargs.pop("prompt_cache_retention", None)
                kwargs["max_tokens"] = request.max_tokens
                try:
                    response = await self._client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
                except (openai.BadRequestError, TypeError, KeyError):
                    # Last resort: omit token limit entirely
                    kwargs.pop("max_tokens", None)
                    response = await self._client.chat.completions.create(**kwargs)  # type: ignore[arg-type]

            latency = (time.monotonic() - start) * 1000
            message = response.choices[0].message if response.choices else None
            # Check content, then refusal (model may refuse via refusal field)
            content = ""
            if message:
                content = message.content or getattr(message, "refusal", None) or ""
                # Sanitize invalid Unicode surrogates (local models like Ollama
                # can produce these, causing JSON serialization failures).
                if self._is_local and content:
                    content = content.encode("utf-8", errors="replace").decode("utf-8")

            # Parse native tool calls from response.
            # Note: message.tool_calls can be [] (empty list) which is falsy —
            # we must check explicitly for None vs empty.
            parsed_tool_calls = None
            if message and message.tool_calls is not None and len(message.tool_calls) > 0:
                import json as _json

                from volnix.llm.types import ToolCall

                parsed_tool_calls = []
                for tc in message.tool_calls:
                    try:
                        args = (
                            _json.loads(tc.function.arguments)
                            if isinstance(tc.function.arguments, str)
                            else tc.function.arguments or {}
                        )
                    except _json.JSONDecodeError:
                        args = {}
                    parsed_tool_calls.append(
                        ToolCall(name=tc.function.name, arguments=args, id=tc.id or "")
                    )

            # Log unexpected empty: model generated tokens but we captured nothing
            if not content and not parsed_tool_calls and message:
                comp_tokens = response.usage.completion_tokens if response.usage else 0
                finish = response.choices[0].finish_reason if response.choices else "?"
                refusal = getattr(message, "refusal", None)
                raw_tc = message.tool_calls
                logger.warning(
                    "OpenAI response empty despite %d completion tokens: "
                    "finish_reason=%s, refusal=%s, raw_tool_calls=%s, "
                    "content=%r",
                    comp_tokens,
                    finish,
                    refusal,
                    raw_tc,
                    message.content,
                )

            usage_data = response.usage

            # Extract cached token count for observability
            cached_tokens = 0
            if usage_data and hasattr(usage_data, "prompt_tokens_details"):
                details = usage_data.prompt_tokens_details
                if details and hasattr(details, "cached_tokens"):
                    cached_tokens = details.cached_tokens or 0

            p_tok = usage_data.prompt_tokens if usage_data else 0
            c_tok = usage_data.completion_tokens if usage_data else 0
            usage = LLMUsage(
                prompt_tokens=p_tok,
                completion_tokens=c_tok,
                total_tokens=usage_data.total_tokens if usage_data else 0,
                cached_tokens=cached_tokens,
                cost_usd=self._estimate_cost(model, p_tok, c_tok),
            )

            if cached_tokens > 0:
                logger.info(
                    "OpenAI cache hit: %d/%d prompt tokens cached",
                    cached_tokens,
                    usage.prompt_tokens,
                )

            # Parse structured output when schema was requested
            parsed_structured = None
            if request.output_schema and content:
                try:
                    parsed_structured = json.loads(content)
                    # Unwrap array that was wrapped in object for OpenAI compat
                    if _unwrap_array and isinstance(parsed_structured, dict):
                        parsed_structured = parsed_structured.get("items", parsed_structured)
                    items = len(parsed_structured) if isinstance(parsed_structured, list) else 1
                    logger.info(
                        "OpenAI structured output parsed: %d items, %d chars", items, len(content)
                    )
                except json.JSONDecodeError:
                    logger.warning(
                        "OpenAI structured output was not valid JSON (%d chars)", len(content)
                    )

            return LLMResponse(
                content=content or "",
                structured_output=parsed_structured,
                tool_calls=parsed_tool_calls,
                usage=usage,
                model=model,
                provider="openai_compatible",
                latency_ms=latency,
            )
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            return LLMResponse(
                content="",
                usage=LLMUsage(),
                model=model,
                provider="openai_compatible",
                latency_ms=latency,
                error=f"{type(e).__name__}: {str(e)[:500]}",
            )

    async def validate_connection(self) -> bool:
        """Validate connectivity to the OpenAI-compatible endpoint.

        Returns:
            ``True`` if reachable with valid credentials.
        """
        try:
            await self._client.models.list()
            return True
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        """List available models from the endpoint.

        Returns:
            A list of model identifier strings.
        """
        try:
            models = await self._client.models.list()
            return [m.id for m in models.data]
        except Exception:
            return [self._default_model]

    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate request cost in USD from the COST_TABLE.

        Local providers (Ollama, vLLM) have no per-token billing, so they
        return 0.0. Unknown hosted models fall back to ``_DEFAULT_RATE``.
        """
        if self._is_local:
            return 0.0
        in_cost, out_cost = self.COST_TABLE.get(model, self._DEFAULT_RATE)
        return (input_tokens * in_cost + output_tokens * out_cost) / 1_000_000

    def get_info(self) -> ProviderInfo:
        """Return provider metadata.

        Returns:
            A :class:`ProviderInfo` describing this provider instance.
        """
        return ProviderInfo(
            name="openai_compatible",
            type="openai_compatible",
            base_url=self._base_url,
            available_models=[self._default_model],
        )
