"""Google native LLM provider for the Terrarium framework.

Implements the :class:`~terrarium.llm.provider.LLMProvider` interface
using the Google Generative AI (Gemini) native SDK.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import ClassVar

from google import genai

from terrarium.llm.provider import LLMProvider
from terrarium.llm.types import LLMRequest, LLMResponse, LLMUsage, ProviderInfo

logger = logging.getLogger(__name__)


class GoogleNativeProvider(LLMProvider):
    """LLM provider backed by the Google Generative AI (Gemini) native API."""

    provider_name: ClassVar[str] = "google"

    def __init__(self, api_key: str, default_model: str = "gemini-3-flash-preview", timeout: float = 300.0) -> None:
        self._client = genai.Client(api_key=api_key)
        self._default_model = default_model
        self._timeout = timeout
        # Cache: hash(model:system_prompt:tools) → cache.name for reuse
        self._prompt_cache: dict[str, str] = {}

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
                declarations = [
                    types.FunctionDeclaration(
                        name=t.name,
                        description=t.description,
                        parameters=t.parameters,
                    )
                    for t in request.tools
                ]
                tool_objects = [types.Tool(function_declarations=declarations)]
                tool_config_obj = types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(mode="ANY")
                )

            # Explicit context caching for repeated system prompts.
            # Per Gemini docs, tools/tool_config must be part of the cache
            # creation — they cannot be passed separately in GenerateContent
            # when using a cache. Cache key includes tool signature so
            # different tool sets produce different caches.
            cached_content_name = None
            if request.cache_system_prompt and request.system_prompt:
                tool_sig = (
                    ",".join(sorted(t.name for t in request.tools))
                    if request.tools else ""
                )
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
                            cache_key, model, len(request.tools or []),
                        )
                    except Exception as exc:
                        logger.warning("Gemini cache creation failed (non-fatal): %s", exc)

            config: dict = {
                "max_output_tokens": request.max_tokens,
                "temperature": request.temperature,
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

            if cached_content_name:
                # Use cached content — system prompt and tools served from cache.
                # Do NOT add tools to config here; they are in the cache.
                config["cached_content"] = cached_content_name
                response = await asyncio.to_thread(
                    self._client.models.generate_content,
                    model=model,
                    contents=request.user_content,
                    config=config,
                )
            else:
                # No cache — add tools to config directly.
                if tool_objects:
                    config["tools"] = tool_objects
                    config["tool_config"] = tool_config_obj

                prompt = (
                    f"{request.system_prompt}\n\n{request.user_content}"
                    if request.system_prompt
                    else request.user_content
                )
                response = await asyncio.to_thread(
                    self._client.models.generate_content,
                    model=model,
                    contents=prompt,
                    config=config,
                )
            latency = (time.monotonic() - start) * 1000
            content = response.text if response.text else ""

            # Parse native tool calls from response
            parsed_tool_calls = None
            if hasattr(response, "candidates") and response.candidates:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "function_call") and part.function_call:
                        from terrarium.llm.types import ToolCall

                        fc = part.function_call
                        parsed_tool_calls = [
                            ToolCall(
                                name=fc.name,
                                arguments=dict(fc.args) if fc.args else {},
                            )
                        ]
                        break

            # Parse structured output when schema was requested
            parsed_structured = None
            if request.output_schema and content:
                try:
                    parsed_structured = json.loads(content)
                    items = len(parsed_structured) if isinstance(parsed_structured, list) else 1
                    logger.info(
                        "Gemini structured output parsed: %d items, %d chars",
                        items, len(content),
                    )
                except json.JSONDecodeError:
                    logger.warning(
                        "Gemini structured output was not valid JSON (%d chars)",
                        len(content),
                    )

            usage_meta = response.usage_metadata
            usage = LLMUsage(
                prompt_tokens=(
                    getattr(usage_meta, "prompt_token_count", 0) if usage_meta else 0
                ),
                completion_tokens=(
                    getattr(usage_meta, "candidates_token_count", 0) if usage_meta else 0
                ),
                total_tokens=(
                    getattr(usage_meta, "total_token_count", 0) if usage_meta else 0
                ),
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
                from terrarium.core.errors import LLMError
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
