"""Shared memory-hook helpers for agency activation paths.

Phase 4B Step 11 shipped memory integration for the NPC path
(``NPCActivator``) only. This module closes the gap by lifting the
recall + implicit-remember logic into pure async helpers that both
``NPCActivator`` AND ``AgencyEngine._activate_with_tool_loop`` invoke.

Both helpers short-circuit when ``memory_engine is None`` — the
default, which keeps Phase 0 regression oracle byte-identical.
Failures are caught + logged; memory is additive and MUST NOT block
activation.

References:
- Phase 4B plan, Step 11 Design Decisions D11-3 through D11-9:
  ``internal_docs/pmf/phase-4b-memory-engine.md``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Final

from volnix.actors.state import ActorState
from volnix.core.events import Event
from volnix.core.protocols import MemoryEngineProtocol
from volnix.core.types import ActivationId, ActorId, SessionId

logger = logging.getLogger(__name__)

# Semantic-query text cap. Safely under ``SemanticQuery._MAX_QUERY_TEXT_LEN``
# (currently 10_000). Matches the existing NPCActivator cap introduced
# in Phase 4B Step 11 D11-3.
_QUERY_TEXT_MAX_CHARS: Final[int] = 1000

# Upper bound on the ``tool_names_invoked`` list written into the
# implicit episodic record. Prevents a runaway tool loop (e.g. a
# 20-iteration read loop) from inflating the memory payload without
# losing signal.
_TOOL_NAMES_CAP: Final[int] = 50


def _build_query_text(
    actor: ActorState,
    trigger_event: Event | None,
    prompt_describe: Callable[[Event | None], str],
) -> str:
    """Compose the HybridQuery ``semantic_text``.

    Concatenates the trigger-event description (what the actor is
    reacting to) with the actor's persona description (a stable
    signal of what they care about). Capped at
    ``_QUERY_TEXT_MAX_CHARS``. Falls back to an actor-id-only
    string when both signals are absent so the query is never empty
    (FTS5 rejects empty search strings).
    """
    persona_text = ""
    if actor.persona:
        persona_text = actor.persona.get("description") or ""
    trigger_text = prompt_describe(trigger_event)
    # L4 (audit-fold): persona FIRST, then trigger. Persona is a
    # stable signal; trigger can be long (e.g. a Slack thread dump).
    # Leading with persona ensures the actor's stable interests are
    # preserved even when the trigger fills the char cap.
    query_text = (persona_text + " " + trigger_text).strip()[:_QUERY_TEXT_MAX_CHARS]
    if not query_text:
        query_text = f"activation for actor {actor.actor_id}"
    return query_text


async def recall_for_activation(
    *,
    memory_engine: MemoryEngineProtocol | None,
    actor: ActorState,
    trigger_event: Event | None,
    prompt_describe: Callable[[Event | None], str],
    tick: int,
    session_id: SessionId | None = None,
) -> Any | None:
    """Pre-activation memory recall shared by both activation paths.

    Returns a ``MemoryRecall`` on success, ``None`` on any failure or
    when ``memory_engine is None``. Never raises — callers rely on
    this to avoid guarding every call site (D11-6).

    Query shape follows Phase 4B D11-3: ``HybridQuery`` with
    trigger-description + persona as semantic text. ``top_k`` read
    from the engine's memory config (default 5 when unset).

    Scoping: ``session_id`` is forwarded verbatim to
    ``MemoryEngine.recall`` — ``None`` reads session-less rows, a
    concrete SessionId reads only that session's rows
    (``tnl/session-scoped-memory.tnl``).
    """
    if memory_engine is None:
        return None

    # Local import keeps this module free of the memory package at
    # import time (per composition-root discipline — concrete engine
    # imports live only in ``registry/composition.py``).
    from volnix.core.memory_types import HybridQuery

    query_text = _build_query_text(actor, trigger_event, prompt_describe)

    top_k = int(
        getattr(
            getattr(memory_engine, "_memory_config", None),
            "default_recall_top_k",
            5,
        )
    )

    try:
        return await memory_engine.recall(
            caller=actor.actor_id,
            target_scope="actor",
            target_owner=str(actor.actor_id),
            query=HybridQuery(semantic_text=query_text, top_k=top_k),
            tick=tick,
            session_id=session_id,
        )
    except Exception as exc:  # noqa: BLE001 — D11-6
        logger.warning(
            "memory recall failed for %s: %s — continuing with no recalled memories.",
            actor.actor_id,
            exc,
        )
        return None


async def implicit_remember_activation(
    *,
    memory_engine: MemoryEngineProtocol | None,
    actor_id: ActorId,
    activation_id: ActivationId,
    reason: str,
    terminated_by: str,
    total_tool_calls: int,
    tool_names_invoked: list[str],
    final_text: str,
    tick: int,
    session_id: SessionId | None = None,
) -> None:
    """Post-activation raw episodic write shared by both paths.

    One structured ``MemoryWrite`` per activation, no LLM call — the
    Consolidator handles episodic→semantic distillation asynchronously
    on cohort rotation / periodic cadence. Never raises (D11-9).

    Tag list: ``[reason, *tool_names_invoked, terminated_by]``. Tool
    names are clipped to ``_TOOL_NAMES_CAP`` to keep the payload
    bounded on runaway loops.

    Importance: ``0.5`` when tools were used, else ``0.2`` (abstained)
    — matches D11-7.

    Scoping: ``session_id`` is forwarded verbatim to
    ``MemoryEngine.remember`` (``tnl/session-scoped-memory.tnl``).
    """
    if memory_engine is None:
        return

    from volnix.core.memory_types import MemoryWrite

    clipped_tools = tool_names_invoked[:_TOOL_NAMES_CAP]
    content = (
        f"{reason} → {terminated_by}: used {total_tool_calls} tool(s) "
        f"{clipped_tools}. text={final_text[:120]!r}"
    )
    importance = 0.5 if total_tool_calls > 0 else 0.2
    tags = [reason, *clipped_tools, terminated_by]

    try:
        await memory_engine.remember(
            caller=actor_id,
            target_scope="actor",
            target_owner=str(actor_id),
            write=MemoryWrite(
                content=content,
                kind="episodic",
                importance=importance,
                tags=tags,
                source="implicit",
                metadata={
                    "activation_id": str(activation_id),
                    "terminated_by": terminated_by,
                },
            ),
            tick=tick,
            session_id=session_id,
        )
    except Exception as exc:  # noqa: BLE001 — D11-9
        logger.warning(
            "implicit remember failed for %s: %s",
            actor_id,
            exc,
        )
