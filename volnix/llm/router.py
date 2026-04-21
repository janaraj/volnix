"""LLM request router for the Volnix framework.

Routes LLM requests to the appropriate provider and model based on the
engine name and use-case, using the routing table from configuration.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from volnix.llm.config import LLMConfig, LLMRoutingEntry
from volnix.llm.provider import LLMProvider
from volnix.llm.registry import ProviderRegistry
from volnix.llm.tracker import UsageTracker
from volnix.llm.types import EmbeddingRequest, EmbeddingResponse, LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class LLMRouter:
    """Routes LLM requests to providers based on engine name and use-case."""

    def __init__(
        self,
        config: LLMConfig,
        registry: ProviderRegistry,
        tracker: UsageTracker | None = None,
    ) -> None:
        self._config = config
        self._registry = registry
        self._tracker = tracker
        self._semaphore = asyncio.Semaphore(
            config.max_concurrent if hasattr(config, "max_concurrent") else 10
        )

    def register_provider(self, name: str, provider: Any) -> None:
        """Register an LLM provider under a given name (PMF Plan
        Phase 4C Step 8 — post-impl audit H4/L2).

        Public wrapper over ``self._registry.register`` so callers
        (e.g., ``VolnixApp`` registering the replay provider)
        don't reach into the router's private ``_registry``
        attribute. Composition root continues to own provider
        construction; this method is pure glue.
        """
        self._registry.register(name, provider)

    def _resolve_routing(
        self, engine_name: str, use_case: str = "default"
    ) -> LLMRoutingEntry | None:
        """Look up the routing entry for the given engine and use-case.

        Tries ``{engine_name}_{use_case}`` first, then ``{engine_name}``.

        Args:
            engine_name: Name of the engine.
            use_case: The use-case category.

        Returns:
            The matched routing entry, or ``None`` for fallback to defaults.
        """
        routing_key = f"{engine_name}_{use_case}" if use_case != "default" else engine_name
        return self._config.routing.get(routing_key) or self._config.routing.get(engine_name)

    async def route(
        self,
        request: LLMRequest,
        engine_name: str,
        use_case: str = "default",
    ) -> LLMResponse:
        """Route an LLM request to the appropriate provider.

        Selects the provider and model based on the routing table, then
        delegates to the provider's ``generate`` method.

        Args:
            request: The LLM request payload.
            engine_name: Name of the engine making the request.
            use_case: The use-case category (e.g. ``"default"``, ``"structured"``).

        Returns:
            The LLM response from the selected provider.
        """
        # PMF Plan Phase 4C Step 8 — replay-mode interception. When
        # the caller sets ``replay_mode=True`` on the request, bypass
        # engine/use-case routing entirely and delegate to the
        # registered ``"replay"`` provider. Preserves the normal
        # path bit-identically when ``replay_mode=False`` (default).
        if request.replay_mode:
            # Post-impl audit H3: reject conflicting overrides
            # loudly. A caller that sets both ``replay_mode=True``
            # AND ``provider_override="<something else>"`` has a
            # bug — the current code would silently drop the
            # override; surface it as an error instead.
            if request.provider_override and request.provider_override != "replay":
                from volnix.core.errors import ReplayProviderNotFound

                raise ReplayProviderNotFound(
                    f"LLMRouter: replay_mode=True with "
                    f"provider_override={request.provider_override!r} "
                    f"is ambiguous — clear provider_override or set "
                    f"replay_mode=False."
                )
            try:
                replay_provider = self._registry.get("replay")
            except KeyError as exc:
                from volnix.core.errors import ReplayProviderNotFound

                raise ReplayProviderNotFound(
                    "LLMRouter: 'replay' provider not registered; "
                    "cannot service replay_mode=True request. "
                    "App startup must register ReplayLLMProvider after "
                    "the ledger is initialized."
                ) from exc
            return await replay_provider.generate(request)

        routing = self._resolve_routing(engine_name, use_case)

        if routing:
            provider_name = routing.provider or self._config.defaults.type
            model = routing.model or self._config.defaults.default_model
            updates: dict[str, Any] = {}
            if routing.temperature is not None:
                updates["temperature"] = routing.temperature
            if routing.max_tokens is not None:
                updates["max_tokens"] = routing.max_tokens
            if updates:
                request = request.model_copy(update=updates)
        else:
            provider_name = self._config.defaults.type
            model = self._config.defaults.default_model

        # Per-request overrides (from agent config or caller)
        if request.provider_override:
            provider_name = request.provider_override
        if request.model_override:
            model = request.model_override

        try:
            provider = self._registry.get(provider_name)
        except KeyError:
            routing_key = f"{engine_name}_{use_case}" if use_case != "default" else engine_name
            raise KeyError(
                f"No provider '{provider_name}' registered. "
                f"Routing: {routing_key} -> {'matched' if routing else 'fell through to defaults'}. "
                f"Check [llm.routing.{routing_key}] or [llm.defaults] in volnix.toml."
            )

        if not request.model_override:
            request = request.model_copy(update={"model_override": model})

        # Use configured timeout from routing or defaults (not hardcoded)
        timeout = (
            getattr(routing, "timeout_seconds", None)
            or self._config.defaults.timeout_seconds
            or 120.0
        )

        max_retries = self._config.max_retries
        backoff_base = self._config.retry_backoff_base

        for attempt in range(1 + max_retries):
            async with self._semaphore:
                try:
                    response = await asyncio.wait_for(
                        provider.generate(request),
                        timeout=timeout,
                    )
                except TimeoutError:
                    response = LLMResponse(
                        content="",
                        provider=provider_name,
                        model=model,
                        error=f"LLM call timed out after {int(timeout)}s",
                    )

            # Determine if the response is retryable
            is_retryable = False
            if response.error:
                is_retryable = self._is_transient_error(response.error)
            elif not response.content and not response.tool_calls:
                is_retryable = True  # Empty response with no error = transient

            if response.error and not is_retryable:
                logger.warning(
                    "LLM call failed (non-retryable): %s/%s — %s",
                    engine_name,
                    use_case,
                    response.error,
                )

            if not is_retryable or attempt >= max_retries:
                break

            delay = backoff_base * (2**attempt)
            logger.warning(
                "LLM call returned retryable result (attempt %d/%d), retrying in %.1fs: %s/%s — %s",
                attempt + 1,
                max_retries,
                delay,
                engine_name,
                use_case,
                response.error or "empty response",
            )
            await asyncio.sleep(delay)

        if self._tracker:
            await self._tracker.record(request, response, engine_name)

        # Write LLM request/response to file when llm_debug is enabled
        if getattr(self._config, "llm_debug", False):
            self._write_debug_response(engine_name, use_case, request, response)

        return response

    _TRANSIENT_PATTERNS = (
        "timeout",
        "timed out",
        "rate limit",
        "429",
        "500",
        "502",
        "503",
        "504",
        "overloaded",
    )

    def _is_transient_error(self, error: str) -> bool:
        """Check if an error message indicates a transient failure."""
        error_lower = error.lower()
        return any(p in error_lower for p in self._TRANSIENT_PATTERNS)

    async def embed(
        self,
        request: EmbeddingRequest,
        engine_name: str,
        use_case: str = "default",
    ) -> EmbeddingResponse:
        """Route an embedding request to the appropriate provider.

        Phase 4B Step 3.5 (G3 of the gap analysis). Mirrors ``route``
        with the same routing table, retry logic, and tracker hook —
        symmetry is intentional so operators reason about embeddings
        and completions identically (same ``[llm.routing.*]`` knob).

        Providers that don't support embeddings raise
        ``NotImplementedError`` from their default ``embed`` impl;
        that surfaces as a clean ``error`` field on the response.
        """
        routing = self._resolve_routing(engine_name, use_case)

        if routing:
            provider_name = routing.provider or self._config.defaults.type
            model = routing.model or self._config.defaults.default_model
        else:
            provider_name = self._config.defaults.type
            model = self._config.defaults.default_model

        if request.provider_override:
            provider_name = request.provider_override
        if request.model_override:
            model = request.model_override

        try:
            provider = self._registry.get(provider_name)
        except KeyError:
            routing_key = f"{engine_name}_{use_case}" if use_case != "default" else engine_name
            raise KeyError(
                f"No provider '{provider_name}' registered for embedding. "
                f"Routing: {routing_key} -> "
                f"{'matched' if routing else 'fell through to defaults'}. "
                f"Check [llm.routing.{routing_key}] or [llm.defaults] in volnix.toml."
            )

        if not request.model_override:
            request = request.model_copy(update={"model_override": model})

        timeout = (
            getattr(routing, "timeout_seconds", None)
            or self._config.defaults.timeout_seconds
            or 120.0
        )
        max_retries = self._config.max_retries
        backoff_base = self._config.retry_backoff_base

        response: EmbeddingResponse
        for attempt in range(1 + max_retries):
            async with self._semaphore:
                try:
                    response = await asyncio.wait_for(
                        provider.embed(request),
                        timeout=timeout,
                    )
                except TimeoutError:
                    response = EmbeddingResponse(
                        vectors=[],
                        provider=provider_name,
                        model=model,
                        error=f"Embedding call timed out after {int(timeout)}s",
                    )
                except NotImplementedError as e:
                    # Clean error — don't retry. Config pointed at a
                    # provider that doesn't support embeddings.
                    response = EmbeddingResponse(
                        vectors=[],
                        provider=provider_name,
                        model=model,
                        error=f"NotImplementedError: {e}",
                    )
                    break

            is_retryable = False
            if response.error:
                is_retryable = self._is_transient_error(response.error)

            if response.error and not is_retryable:
                logger.warning(
                    "Embedding call failed (non-retryable): %s/%s — %s",
                    engine_name,
                    use_case,
                    response.error,
                )

            if not is_retryable or attempt >= max_retries:
                break

            delay = backoff_base * (2**attempt)
            logger.warning(
                "Embedding call returned retryable result "
                "(attempt %d/%d), retrying in %.1fs: %s/%s — %s",
                attempt + 1,
                max_retries,
                delay,
                engine_name,
                use_case,
                response.error,
            )
            await asyncio.sleep(delay)

        if self._tracker:
            await self._tracker.record_embedding(request, response, engine_name)

        return response

    def get_provider_for(self, engine_name: str, use_case: str = "default") -> LLMProvider:
        """Resolve the provider for a given engine and use-case.

        Args:
            engine_name: Name of the engine.
            use_case: The use-case category.

        Returns:
            The resolved :class:`LLMProvider` instance.
        """
        routing = self._resolve_routing(engine_name, use_case)
        provider_name = (
            routing.provider if routing and routing.provider else self._config.defaults.type
        )
        return self._registry.get(provider_name)

    def get_model_for(self, engine_name: str, use_case: str = "default") -> str:
        """Resolve the model name for a given engine and use-case.

        Args:
            engine_name: Name of the engine.
            use_case: The use-case category.

        Returns:
            The model identifier string.
        """
        routing = self._resolve_routing(engine_name, use_case)
        if routing and routing.model:
            return routing.model
        return self._config.defaults.default_model

    # ── Debug response logging ────────────────────────────────────

    _LLM_DEBUG_DIR = Path.home() / ".volnix" / "data" / "llm_debug"

    def _write_debug_response(
        self,
        engine_name: str,
        use_case: str,
        request: LLMRequest,
        response: LLMResponse,
    ) -> None:
        """Write LLM response content to a debug file.

        Only called when log level is DEBUG. Files are written to
        ``data/llm_debug/`` with timestamps for easy correlation.
        """
        try:
            self._LLM_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
            filename = f"{ts}_{engine_name}_{use_case}.json"
            # Build message summary for multi-turn conversations
            messages_summary = None
            if request.messages:
                messages_summary = [
                    {"role": m.get("role", "?"), "length": len(m.get("content", "") or "")}
                    for m in request.messages
                ]

            # Capture tool calls from response
            tool_calls_data = None
            if response.tool_calls:
                tool_calls_data = [
                    {"name": tc.name, "id": tc.id, "args_keys": list(tc.arguments.keys())}
                    for tc in response.tool_calls
                ]

            payload = {
                "timestamp": ts,
                "engine": engine_name,
                "use_case": use_case,
                "provider": response.provider,
                "model": response.model,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "latency_ms": response.latency_ms,
                "success": response.error is None,
                "error": response.error,
                "system_prompt": (
                    request.system_prompt[:10000] + "..."
                    if len(request.system_prompt) > 10000
                    else request.system_prompt
                ),
                "user_content": request.user_content,
                "messages_summary": messages_summary,
                "tool_choice": request.tool_choice,
                "response_content": response.content,
                "response_tool_calls": tool_calls_data,
            }
            (self._LLM_DEBUG_DIR / filename).write_text(json.dumps(payload, indent=2, default=str))
        except Exception:
            logger.debug("Failed to write LLM debug file", exc_info=True)
