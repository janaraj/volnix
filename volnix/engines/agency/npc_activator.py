"""NPCActivator — LLM tool-loop for Active NPCs.

Runs a purpose-built, narrower LLM loop than
:meth:`AgencyEngine._activate_with_tool_loop`. The agent loop carries
delegation, synthesis phases, team-roster context, autonomous
re-activation scaffolding, and game-move logic — none of which apply
to a consumer NPC deciding whether to try a product.

Design choices:

* **Single-turn** per activation in Phase 2. Multi-turn NPC reasoning
  is out of scope until a concrete need surfaces. One LLM call + its
  tool calls are plenty for exposure/word-of-mouth/probe responses.
* **Reuses the agency engine's private helpers** (``_parse_tool_call``,
  ``_autofill_comm_context``, etc.) by accepting the engine as a
  ``host`` kwarg. Both classes live in :mod:`volnix.engines.agency`,
  so this is intra-package coupling — not a cross-engine violation.
  Duplicating ``_parse_tool_call`` (~60 lines) would drift from the
  agent path over time and invite bugs where the two interpret the
  same tool differently.
* **Shared invariants**: every NPC tool call goes through the injected
  ``tool_executor`` (the 7-step governance pipeline), respects the
  shared ``pipeline_lock`` and ``llm_semaphore``, and is recorded in
  the ledger.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from volnix.actors.activation_profile import ActivationProfile, ToolScope
from volnix.actors.state import ActorState
from volnix.core.envelope import ActionEnvelope
from volnix.core.events import Event, WorldEvent

logger = logging.getLogger(__name__)


class NPCActivator:
    """Orchestrates the Active-NPC LLM loop.

    Construction is lightweight — just remember the prompt builder and
    profile loader. Heavy dependencies (LLM router, tool executor,
    engine) are passed per-activation via :meth:`run_tool_loop` kwargs
    so the activator never holds ambient references that might get
    stale across an ``AgencyEngine.configure`` call.
    """

    def __init__(
        self,
        *,
        prompt_builder: Any,  # NPCPromptBuilder (duck-typed, avoid circular import)
        activation_profile_loader: Any,  # ActivationProfileLoaderProtocol
    ) -> None:
        self._prompt_builder = prompt_builder
        self._loader = activation_profile_loader

    async def activate_npc(
        self,
        *,
        actor: ActorState,
        reason: str,
        trigger_event: Event | None,
        max_calls_override: int | None,
        host: Any,  # NPCHostProtocol — typed Any to avoid import cycle
    ) -> list[ActionEnvelope]:
        """Run a single-turn NPC decision cycle.

        Implements :class:`volnix.core.protocols.NPCActivatorProtocol`.
        Returns the list of ActionEnvelopes that reached the pipeline
        during this activation (matches
        :meth:`AgencyEngine._activate_with_tool_loop`'s return type so
        the caller treats both paths uniformly).
        """
        if actor.activation_profile_name is None:
            logger.warning(
                "NPCActivator invoked for actor %s without activation_profile_name",
                actor.actor_id,
            )
            return []

        llm_router = host._llm_router
        tool_executor = host._tool_executor
        if llm_router is None:
            logger.warning(
                "NPCActivator: no LLM router — activation skipped for %s",
                actor.actor_id,
            )
            return []
        if tool_executor is None:
            logger.warning(
                "NPCActivator: no tool executor — activation skipped for %s",
                actor.actor_id,
            )
            return []

        try:
            profile = self._loader.load(actor.activation_profile_name)
        except (FileNotFoundError, ValueError) as exc:
            logger.error(
                "NPCActivator: failed to load profile %r for actor %s: %s",
                actor.activation_profile_name,
                actor.actor_id,
                exc,
            )
            return []

        max_calls = self._resolve_max_calls(profile, max_calls_override, host._typed_config)

        scoped_tools = self._scoped_tools(
            profile.tool_scope,
            host._tool_definitions,
            host._available_actions,
            host._tool_name_map,
        )

        system_prompt = self._prompt_builder.build(
            state=actor,
            profile=profile,
            trigger_event=trigger_event,
            recent_events=self._recent_events(actor),
            available_tools=[
                {"name": t.name, "description": getattr(t, "description", "") or ""}
                for t in scoped_tools
            ],
        )
        user_prompt = self._user_nudge(reason, trigger_event)

        activation_id = uuid.uuid4().hex[:12]
        loop_start = time.monotonic()
        ledger = getattr(host, "_ledger", None)

        def _record_cohort_activation() -> None:
            # Review fix M7: previously ``record_activation`` was
            # called only at the end of the main loop — text-response
            # early-return and error-path early-return both skipped
            # it. That made NPCs who abstain or hit a provider error
            # look "never activated" forever, making them the LRU
            # policy's permanent top candidate → thrash. Call this
            # helper in every termination path.
            cm = getattr(host, "_cohort_manager", None)
            if cm is None:
                return
            tick_now = 0
            progress = getattr(host, "_simulation_progress", None)
            if progress is not None:
                tick_now = progress[0]
            try:
                cm.record_activation(actor.actor_id, tick_now)
            except (AttributeError, RuntimeError) as exc:
                # Review fix N2: narrow the exception surface. These
                # are the only realistic failure modes — a manager
                # missing the method (misconfigured mock) or a state
                # mutation raising. Other exceptions propagate.
                logger.warning(
                    "Cohort record_activation failed for %s: %s",
                    actor.actor_id,
                    exc,
                )

        # Import lazily — keeps the module decoupled from the LLM package
        # at import time (zero circular-import risk).
        from volnix.ledger.entries import (
            ActivationCompleteEntry,
            ToolLoopStepEntry,
        )
        from volnix.llm.types import LLMRequest

        request = LLMRequest(
            system_prompt=system_prompt,
            user_content=user_prompt,
            tools=scoped_tools or None,
            cache_system_prompt=True,
            model_override=actor.llm_model,
            provider_override=actor.llm_provider,
        )

        envelopes: list[ActionEnvelope] = []
        total_tool_calls = 0
        terminated_by = "text_response"
        llm_spend_cap = profile.budget_defaults.llm_spend
        cumulative_spend = 0.0
        final_text = ""

        async with host._llm_semaphore:
            # M3: LLM call is the most likely source of runtime failure
            # (rate limit, provider outage, malformed response). A raised
            # exception here would bubble out of activate_for_event and
            # take down the surrounding tick; instead, terminate the
            # activation gracefully and record the failure in the ledger.
            llm_start = time.monotonic()
            try:
                response = await llm_router.route(
                    request,
                    "agency",
                    "npc_decision",
                )
            except (
                ConnectionError,
                TimeoutError,
                RuntimeError,
                ValueError,
            ) as exc:
                # Review fix N2: narrowed from bare ``except Exception``.
                # Provider failures manifest as these four; anything
                # else (e.g., KeyboardInterrupt, asyncio.CancelledError)
                # should propagate so the tick can unwind cleanly.
                logger.warning(
                    "[NPC %s] LLM call failed: %s — ending activation",
                    actor.actor_id,
                    exc,
                )
                _record_cohort_activation()
                await _append_ledger(
                    ledger,
                    ActivationCompleteEntry(
                        actor_id=actor.actor_id,
                        activation_id=activation_id,
                        activation_reason=reason,
                        total_tool_calls=0,
                        total_envelopes=0,
                        terminated_by="error",
                        final_text=f"llm_error: {type(exc).__name__}",
                    ),
                )
                return envelopes
            llm_latency_ms = (time.monotonic() - llm_start) * 1000

            # M4: track LLM spend against the profile budget cap. The
            # router's own budget accounting is provider-wide; this cap
            # is per-profile and per-activation.
            response_cost = _response_cost_usd(response)
            cumulative_spend += response_cost

            # Phase 4A: capture prompt-cache hit/write token counts so
            # the ledger can be used to empirically tune cohort K and
            # rotation_interval. Providers that don't report cache
            # metadata leave both fields as ``None``.
            cache_hit_tokens, cache_write_tokens = _cache_tokens(response)

            tool_calls = getattr(response, "tool_calls", []) or []
            final_text = getattr(response, "content", "") or ""

            if not tool_calls:
                # NPC abstained (text-only or empty response). Record and exit.
                _record_cohort_activation()
                await _append_ledger(
                    ledger,
                    ActivationCompleteEntry(
                        actor_id=actor.actor_id,
                        activation_id=activation_id,
                        activation_reason=reason,
                        total_tool_calls=0,
                        total_envelopes=0,
                        terminated_by="text_response",
                        final_text=(final_text or "")[:200],
                        cache_hit_tokens=cache_hit_tokens,
                        cache_write_tokens=cache_write_tokens,
                    ),
                )
                return envelopes

            for step_index, tc in enumerate(tool_calls):
                if total_tool_calls >= max_calls:
                    terminated_by = "max_tool_calls"
                    break

                # do_nothing is a sentinel — ends the activation early.
                if getattr(tc, "name", "") == "do_nothing":
                    await _append_ledger(
                        ledger,
                        ToolLoopStepEntry(
                            actor_id=actor.actor_id,
                            activation_id=activation_id,
                            step_index=step_index,
                            tool_name="do_nothing",
                            llm_latency_ms=llm_latency_ms if step_index == 0 else 0.0,
                        ),
                    )
                    total_tool_calls += 1
                    terminated_by = "do_nothing"
                    break

                # Reuse agency's parser to produce an ActionEnvelope
                # with all the same metadata an agent would produce
                # (intended_for, parent_event_ids, auto-filled comm
                # context, logical_time, priority). NPCs get the same
                # shape so downstream pipeline code can't tell them
                # apart from agent actions.
                trigger_world_event = (
                    trigger_event if isinstance(trigger_event, WorldEvent) else None
                )
                env = host._parse_tool_call(actor, tc, reason, trigger_world_event)
                if env is None:
                    continue

                async with host._pipeline_lock:
                    committed = await tool_executor(env)

                total_tool_calls += 1
                envelopes.append(env)

                blocked = committed is None
                await _append_ledger(
                    ledger,
                    ToolLoopStepEntry(
                        actor_id=actor.actor_id,
                        activation_id=activation_id,
                        step_index=step_index,
                        tool_name=getattr(tc, "name", ""),
                        tool_arguments=dict(getattr(tc, "arguments", {}) or {}),
                        event_id=getattr(committed, "event_id", None) if committed else None,
                        blocked=blocked,
                        llm_latency_ms=llm_latency_ms if step_index == 0 else 0.0,
                    ),
                )

                if blocked:
                    logger.debug(
                        "[NPC %s] tool call %s was blocked by the pipeline",
                        actor.actor_id,
                        getattr(tc, "name", ""),
                    )

                # M4: enforce per-activation spend cap. Cap==0 means
                # "use global default" (no enforcement here); positive
                # values are hard caps.
                if llm_spend_cap > 0 and cumulative_spend >= llm_spend_cap:
                    terminated_by = "llm_spend_cap"
                    break

        duration_ms = (time.monotonic() - loop_start) * 1000
        # Review fix M7: record activation for every termination
        # path including max_tool_calls / do_nothing / spend_cap /
        # normal-loop-exit. ``_record_cohort_activation`` is a no-op
        # when no cohort manager is wired.
        _record_cohort_activation()

        await _append_ledger(
            ledger,
            ActivationCompleteEntry(
                actor_id=actor.actor_id,
                activation_id=activation_id,
                activation_reason=reason,
                total_tool_calls=total_tool_calls,
                total_envelopes=len(envelopes),
                terminated_by=terminated_by,
                final_text=final_text[:200] if final_text else "",
                cache_hit_tokens=cache_hit_tokens,
                cache_write_tokens=cache_write_tokens,
            ),
        )
        logger.info(
            "[NPC %s] activation_id=%s reason=%s tool_calls=%d duration_ms=%.1f terminated_by=%s",
            actor.actor_id,
            activation_id,
            reason,
            total_tool_calls,
            duration_ms,
            terminated_by,
        )
        return envelopes

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _resolve_max_calls(
        profile: ActivationProfile,
        override: int | None,
        typed_config: Any,
    ) -> int:
        """Pick the per-activation call cap with priority override > profile > global."""
        if isinstance(override, int) and override > 0:
            return override
        profile_cap = profile.budget_defaults.api_calls
        if profile_cap and profile_cap > 0:
            return profile_cap
        return typed_config.max_tool_calls_per_activation

    @staticmethod
    def _scoped_tools(
        tool_scope: ToolScope,
        tool_definitions: list[Any],
        available_actions: list[dict[str, Any]],
        tool_name_map: dict[str, str],
    ) -> list[Any]:
        """Filter the engine's tool catalog against the profile's tool_scope.

        Mirrors the GET/write semantics of
        :meth:`AgencyEngine._get_tools_for_actor` (engine.py:481-526)
        but reads from the frozen :class:`ToolScope` instead of the
        legacy ``permissions`` dict. Service-less tools (``do_nothing``)
        are always allowed — they cost nothing and let an NPC abstain.
        """
        read = set(tool_scope.read)
        write = set(tool_scope.write)
        all_services = {t.service for t in tool_definitions if getattr(t, "service", None)}
        if "all" in read:
            read = all_services
        if "all" in write:
            write = all_services

        method_lookup = {
            a.get("name", ""): a.get("http_method", "POST").upper() for a in available_actions
        }

        allowed: list[Any] = []
        for tool in tool_definitions:
            service = getattr(tool, "service", None)
            if not service:
                allowed.append(tool)
                continue
            original_name = tool_name_map.get(tool.name, "")
            method = method_lookup.get(original_name, "POST")
            if method == "GET" and service in read:
                allowed.append(tool)
            elif method != "GET" and service in write:
                allowed.append(tool)
        return allowed

    @staticmethod
    def _recent_events(actor: ActorState) -> list[dict[str, Any]]:
        return [
            {"summary": ir.summary, "tick": ir.tick}
            for ir in (actor.recent_interactions or [])[-10:]
        ]

    @staticmethod
    def _user_nudge(reason: str, trigger_event: Event | None) -> str:
        """One-line user message nudging the NPC to decide.

        The system prompt already carries the full persona and state;
        this keeps the user turn short so prompt caching stays
        effective across activations.
        """
        base = "Decide what (if anything) to do next. Be honest to your persona."
        etype = getattr(trigger_event, "event_type", "") if trigger_event else ""
        return f"[trigger: {reason} / {etype or 'none'}] {base}"


# -- module-level helpers -----------------------------------------------------


async def _append_ledger(ledger: Any, entry: Any) -> None:
    """Append to the ledger if one is wired; tolerate absent ledger (tests).

    Failures in the ledger are non-fatal for the activation itself — we
    log and continue. The alternative (propagating the exception) would
    couple NPC correctness to ledger availability, which is the wrong
    direction per DESIGN_PRINCIPLES ("separate bus from ledger").
    """
    if ledger is None:
        return
    try:
        await ledger.append(entry)
    except Exception as exc:  # noqa: BLE001 — intentionally non-fatal
        logger.warning("NPC ledger append failed: %s", exc)


def _response_cost_usd(response: Any) -> float:
    """Extract USD cost from an ``LLMResponse`` if the router tracked it.

    Routers that don't populate ``usage.cost_usd`` return 0.0 here — the
    activation-level spend cap then defers to the router's own global
    cap (``M4`` is belt-and-braces, not the sole guard).
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0.0
    cost = getattr(usage, "cost_usd", None)
    if cost is None:
        return 0.0
    try:
        return float(cost)
    except (TypeError, ValueError):
        return 0.0


def _cache_tokens(response: Any) -> tuple[int | None, int | None]:
    """Extract prompt-cache hit + write token counts from an LLM response.

    Anthropic / OpenAI / Google all expose these via ``response.usage``
    with the canonical Anthropic names:
    ``cache_read_input_tokens`` and ``cache_creation_input_tokens``.
    Providers that don't report cache metadata (or responses that
    bypass the cache entirely) return ``(None, None)``.

    Used by Phase 4A to populate cache observability on
    ``ActivationCompleteEntry``. Absent metadata stays ``None`` so
    analytics can distinguish "no-cache-hit" from "no-data".
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return None, None
    hit = getattr(usage, "cache_read_input_tokens", None)
    write = getattr(usage, "cache_creation_input_tokens", None)

    def _maybe_int(v: Any) -> int | None:
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    return _maybe_int(hit), _maybe_int(write)
