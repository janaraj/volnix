"""Google native LLM provider for the Volnix framework.

Implements the :class:`~volnix.llm.provider.LLMProvider` interface
using the Google Generative AI (Gemini) native SDK.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import time
from typing import Any, ClassVar

from google import genai

from volnix.llm.provider import LLMProvider
from volnix.llm.types import LLMRequest, LLMResponse, LLMUsage, ProviderInfo, ToolCall

logger = logging.getLogger(__name__)


# Gemini's function-declaration schema is a strict subset of JSON Schema.
# Any field outside this whitelist is rejected by the API with
# "Unknown name ... Cannot find field". This includes `additionalProperties`,
# which OpenAI / Anthropic accept (and Anthropic actually requires).
_GEMINI_SCHEMA_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "type",
        "description",
        "format",
        "nullable",
        "enum",
        "properties",
        "required",
        "items",
        "minimum",
        "maximum",
        "min_items",
        "max_items",
        "min_length",
        "max_length",
        "example",
        "default",
        "title",
    }
)


def _sanitize_tool_params_for_gemini(schema: Any) -> Any:
    """Recursively drop JSON Schema keys that Gemini's function-declaration
    API does not support.

    Gemini rejects requests containing unknown fields like
    ``additionalProperties`` (even though it is standard JSON Schema and
    required by Anthropic). This helper walks the parameter schema and
    keeps only keys in ``_GEMINI_SCHEMA_ALLOWED_KEYS``, recursing into
    ``properties`` and ``items``.

    Non-dict inputs are returned unchanged so the function is a no-op
    for primitive schema leaves.
    """
    if not isinstance(schema, dict):
        return schema
    result: dict[str, Any] = {}
    for k, v in schema.items():
        if k not in _GEMINI_SCHEMA_ALLOWED_KEYS:
            continue
        if k == "properties" and isinstance(v, dict):
            result[k] = {
                prop_name: _sanitize_tool_params_for_gemini(prop_schema)
                for prop_name, prop_schema in v.items()
            }
        elif k == "items":
            result[k] = _sanitize_tool_params_for_gemini(v)
        else:
            result[k] = v
    return result


def _find_tool_name_for_id(messages: list[dict], tool_call_id: str) -> str:
    """Look up the tool name matching a tool_call_id in earlier assistant messages.

    Gemini's FunctionResponse requires a name field, but OpenAI-format tool
    messages only carry tool_call_id + content. We resolve the name by
    scanning earlier assistant messages for the matching tool_calls entry.
    """
    if not tool_call_id:
        return ""
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            if tc.get("id") == tool_call_id:
                return (tc.get("function", {}) or {}).get("name", "") or ""
    return ""


class GoogleNativeProvider(LLMProvider):
    """LLM provider backed by the Google Generative AI (Gemini) native API."""

    provider_name: ClassVar[str] = "google"

    def __init__(
        self, api_key: str, default_model: str = "gemini-3-flash-preview", timeout: float = 300.0
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self._default_model = default_model
        self._timeout = timeout
        # Cache: hash(model:system_prompt:tools) → cache.name for reuse
        self._prompt_cache: dict[str, str] = {}

    @staticmethod
    def _build_contents_from_messages(
        messages: list[dict[str, Any]],
    ) -> tuple[list[Any], str]:
        """Convert OpenAI-format messages to Gemini Content list + system instruction.

        Mapping:
          - {role: "system", content}            → system_instruction (returned)
          - {role: "user", content}              → Content(role="user", parts=[text])
          - {role: "assistant", tool_calls, ...} → Content(role="model",
                                                    parts=[FunctionCall, ..., optional text])
          - {role: "tool", tool_call_id, content}→ Content(role="user",
                                                    parts=[FunctionResponse])
                                                    (per Gemini SDK AFC convention)

        Returns:
            Tuple of (contents_list, system_instruction_string).
            contents_list is never empty — uses a placeholder if needed.
            system_instruction_string is empty if no system messages.
        """
        from google.genai import types

        contents: list[types.Content] = []
        system_parts: list[str] = []

        for msg in messages:
            role = msg.get("role", "")
            text = msg.get("content", "") or ""

            if role == "system":
                if text:
                    system_parts.append(text)
                continue

            if role == "tool":
                tc_id = msg.get("tool_call_id", "") or ""
                try:
                    response_body = json.loads(text) if text else {}
                    if not isinstance(response_body, dict):
                        response_body = {"result": response_body}
                except (json.JSONDecodeError, ValueError):
                    response_body = {"result": text}
                tool_name = _find_tool_name_for_id(messages, tc_id) or "unknown_tool"
                fr = types.FunctionResponse(
                    name=tool_name,
                    response=response_body,
                    id=tc_id or None,
                )
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part(function_response=fr)],
                    )
                )
                continue

            if role == "assistant":
                tool_calls = msg.get("tool_calls") or []
                parts: list[types.Part] = []
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    fn_name = fn.get("name", "") or ""
                    fn_args_raw = fn.get("arguments", "") or "{}"
                    try:
                        fn_args = (
                            json.loads(fn_args_raw)
                            if isinstance(fn_args_raw, str)
                            else dict(fn_args_raw)
                        )
                    except (json.JSONDecodeError, ValueError):
                        fn_args = {}
                    fc = types.FunctionCall(
                        name=fn_name,
                        args=fn_args,
                        id=tc.get("id") or None,
                    )

                    # Restore Gemini-specific thought_signature when present so
                    # the assistant history re-matches what Gemini originally
                    # emitted. Gemini 3 thinking models reject follow-up calls
                    # whose history contains function_call parts without the
                    # signature, even when thinking_budget=0 is set.
                    thought_sig: bytes | None = None
                    metadata = tc.get("provider_metadata")
                    if isinstance(metadata, dict):
                        sig_b64 = metadata.get("thought_signature")
                        if isinstance(sig_b64, str) and sig_b64:
                            try:
                                thought_sig = base64.b64decode(sig_b64)
                            except (ValueError, TypeError):
                                thought_sig = None

                    if thought_sig is not None:
                        parts.append(
                            types.Part(
                                function_call=fc,
                                thought_signature=thought_sig,
                            )
                        )
                    else:
                        parts.append(types.Part(function_call=fc))
                if text:
                    parts.append(types.Part.from_text(text=text))
                if parts:
                    contents.append(types.Content(role="model", parts=parts))
                continue

            # Default: user (or any unknown role) → plain text part
            if text:
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=text)],
                    )
                )

        # Gemini rejects empty contents — fallback placeholder
        if not contents:
            contents = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=" ")],
                )
            ]

        return contents, "\n\n".join(system_parts)

    def _resolve_contents_and_config(self, request: LLMRequest, config: dict, cached: bool) -> Any:
        """Resolve the generate_content `contents` param and update config.

        Single source of truth for what to pass as `contents`. Handles both
        cached/non-cached and single-turn/multi-turn cases. Mutates `config`
        in place to set `system_instruction` when appropriate.

        Args:
            request: The LLM request.
            config: The generate_content config dict (mutated in place).
            cached: True if cached_content is being used (system already in cache).

        Returns:
            The value to pass as `contents` — either a string (single-turn)
            or a list of Content objects (multi-turn).
        """
        if request.messages:
            contents_list, sys_instr = self._build_contents_from_messages(request.messages)
            # Skip setting system_instruction when cached (cache already has it)
            if sys_instr and not cached:
                config["system_instruction"] = sys_instr
            return contents_list

        # Single-turn path
        if request.system_prompt and not cached:
            config["system_instruction"] = request.system_prompt
        return request.user_content

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Send a request to the Google Generative AI API.

        The google.genai client is synchronous, so calls are dispatched
        to a thread via :func:`asyncio.to_thread`.

        Args:
            request: The LLM request payload.

        Returns:
            The LLM response.
        """
        model = request.model_override or self._default_model
        start = time.monotonic()
        try:
            from google.genai import types

            # Build tool declarations once — reused in cache creation and/or config.
            tool_objects = None
            tool_config_obj = None
            if request.tools:
                # Sanitize each tool's parameter schema — Gemini's
                # function-declaration API rejects any JSON Schema key
                # outside its allowed set (e.g., `additionalProperties`).
                declarations = [
                    types.FunctionDeclaration(
                        name=t.name,
                        description=t.description,
                        parameters=_sanitize_tool_params_for_gemini(t.parameters),
                    )
                    for t in request.tools
                ]
                tool_objects = [types.Tool(function_declarations=declarations)]
                mode_map = {"auto": "AUTO", "required": "ANY", "none": "NONE"}
                tc_mode = mode_map.get(request.tool_choice or "required", "ANY")
                tool_config_obj = types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(mode=tc_mode)
                )

            # Explicit context caching for repeated system prompts.
            # Per Gemini docs, tools/tool_config must be part of the cache
            # creation — they cannot be passed separately in GenerateContent
            # when using a cache. Cache key includes tool signature so
            # different tool sets produce different caches.
            cached_content_name = None
            if request.cache_system_prompt and request.system_prompt:
                tool_sig = ",".join(sorted(t.name for t in request.tools)) if request.tools else ""
                cache_key = hashlib.sha256(
                    f"{model}:{request.system_prompt}:{tool_sig}".encode()
                ).hexdigest()[:16]

                if cache_key in self._prompt_cache:
                    cached_content_name = self._prompt_cache[cache_key]
                else:
                    try:
                        cache_config: dict = {
                            "system_instruction": request.system_prompt,
                            "ttl": "3600s",
                        }
                        if tool_objects:
                            cache_config["tools"] = tool_objects
                            cache_config["tool_config"] = tool_config_obj

                        cache = await asyncio.to_thread(
                            self._client.caches.create,
                            model=f"models/{model}",
                            config=types.CreateCachedContentConfig(**cache_config),
                        )
                        cached_content_name = cache.name
                        self._prompt_cache[cache_key] = cached_content_name
                        logger.info(
                            "Gemini cache created: %s for model %s (tools=%d)",
                            cache_key,
                            model,
                            len(request.tools or []),
                        )
                    except Exception as exc:
                        logger.warning("Gemini cache creation failed (non-fatal): %s", exc)

            config: dict = {
                "max_output_tokens": request.max_tokens,
                "temperature": request.temperature,
                # Disable thinking by default. Gemini 3 thinking models:
                # (a) generate thought tokens that are billed separately (cost)
                # (b) return thought_signature on function_call parts that must be
                #     echoed on subsequent requests, complicating multi-turn tool
                #     loops. Disabling thinking avoids both issues. Opt-in can be
                #     added later if debate-style games need it.
                "thinking_config": types.ThinkingConfig(thinking_budget=0),
            }
            if request.seed is not None:
                config["seed"] = request.seed

            # Structured output: force valid JSON matching the schema.
            # Uses response_json_schema (accepts raw dict) rather than
            # response_schema (requires google.genai.types.Schema object).
            if request.output_schema:
                config["response_mime_type"] = "application/json"
                config["response_json_schema"] = request.output_schema
                logger.info(
                    "Gemini structured output enabled (schema type=%s)",
                    request.output_schema.get("type", "?"),
                )

            # Configure tools and caching.
            # - Cached path: system_instruction + tools live in the cache.
            # - Non-cached path: add tools to config directly.
            if cached_content_name:
                config["cached_content"] = cached_content_name
            elif tool_objects:
                config["tools"] = tool_objects
                config["tool_config"] = tool_config_obj

            # Unified contents resolution — handles both single/multi-turn for
            # both cached and non-cached paths. Mutates config to set
            # system_instruction when appropriate (skipped for cached path since
            # system is already in the cache).
            final_contents = self._resolve_contents_and_config(
                request, config, cached=bool(cached_content_name)
            )

            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=model,
                contents=final_contents,
                config=config,
            )
            latency = (time.monotonic() - start) * 1000
            content = response.text if response.text else ""

            # Check finish reason for diagnostics (truncation detection)
            finish_reason = None
            if hasattr(response, "candidates") and response.candidates:
                candidate = response.candidates[0]
                finish_reason = getattr(candidate, "finish_reason", None)
                if finish_reason and str(finish_reason) not in ("STOP", "FinishReason.STOP"):
                    logger.warning(
                        "Gemini finish_reason=%s (content=%d chars, max_tokens=%d)",
                        finish_reason,
                        len(content),
                        request.max_tokens,
                    )

            # Schema-constrained generation produced empty content — retry without schema
            if request.output_schema and not content and "response_json_schema" in config:
                logger.warning(
                    "Gemini schema-constrained generation produced no content — "
                    "retrying without schema enforcement"
                )
                del config["response_json_schema"]
                response = await asyncio.to_thread(
                    self._client.models.generate_content,
                    model=model,
                    contents=final_contents,
                    config=config,
                )
                content = response.text if response.text else ""

            # Parse native tool calls from response.
            # Capture thought_signature per-Part so Gemini 3 thinking models
            # can round-trip signatures in subsequent requests; otherwise
            # Gemini returns 400 INVALID_ARGUMENT on follow-up calls whose
            # history contains function_call parts without the signature.
            parsed_tool_calls: list[ToolCall] | None = None
            if hasattr(response, "candidates") and response.candidates:
                collected: list[ToolCall] = []
                for part in response.candidates[0].content.parts:
                    if not (hasattr(part, "function_call") and part.function_call):
                        continue
                    fc = part.function_call
                    sig = getattr(part, "thought_signature", None)
                    metadata: dict[str, Any] | None = None
                    if sig:
                        metadata = {
                            "thought_signature": base64.b64encode(sig).decode("ascii"),
                        }
                    collected.append(
                        ToolCall(
                            name=fc.name,
                            arguments=dict(fc.args) if fc.args else {},
                            id=getattr(fc, "id", "") or "",
                            provider_metadata=metadata,
                        )
                    )
                if collected:
                    parsed_tool_calls = collected

            # Parse structured output when schema was requested
            parsed_structured = None
            if request.output_schema and content:
                try:
                    parsed_structured = json.loads(content)
                    items = len(parsed_structured) if isinstance(parsed_structured, list) else 1
                    logger.info(
                        "Gemini structured output parsed: %d items, %d chars",
                        items,
                        len(content),
                    )
                except json.JSONDecodeError:
                    logger.warning(
                        "Gemini structured output was not valid JSON "
                        "(%d chars, finish=%s, tail=%.200s)",
                        len(content),
                        finish_reason,
                        content[-200:] if content else "",
                    )

            usage_meta = response.usage_metadata
            usage = LLMUsage(
                prompt_tokens=(getattr(usage_meta, "prompt_token_count", 0) if usage_meta else 0),
                completion_tokens=(
                    getattr(usage_meta, "candidates_token_count", 0) if usage_meta else 0
                ),
                total_tokens=(getattr(usage_meta, "total_token_count", 0) if usage_meta else 0),
            )
            return LLMResponse(
                content=content,
                structured_output=parsed_structured,
                tool_calls=parsed_tool_calls,
                usage=usage,
                model=model,
                provider="google",
                latency_ms=latency,
            )
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            error_str = str(e)
            # Rate limit errors should propagate so callers can retry
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                from volnix.core.errors import LLMError

                raise LLMError(
                    f"Gemini rate limit exceeded. {error_str[:200]}",
                    context={"provider": "google", "model": model},
                )
            return LLMResponse(
                content="",
                usage=LLMUsage(),
                model=model,
                provider="google",
                latency_ms=latency,
                error=f"{type(e).__name__}: {error_str[:500]}",
            )

    async def validate_connection(self) -> bool:
        """Validate connectivity to the Google API.

        Returns:
            ``True`` if reachable with valid credentials.
        """
        try:
            await asyncio.to_thread(
                self._client.models.generate_content,
                model=self._default_model,
                contents="ping",
            )
            return True
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        """List available Google Gemini models.

        Returns:
            A list of model identifier strings.
        """
        return [
            "gemini-3-flash-preview",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
        ]

    def get_info(self) -> ProviderInfo:
        """Return provider metadata.

        Returns:
            A :class:`ProviderInfo` describing this Google provider.
        """
        return ProviderInfo(
            name="google",
            type="google",
            base_url="https://generativelanguage.googleapis.com",
            available_models=[
                "gemini-3-flash-preview",
                "gemini-2.5-pro",
                "gemini-2.5-flash",
            ],
        )
