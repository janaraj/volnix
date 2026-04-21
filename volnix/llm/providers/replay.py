"""ReplayLLMProvider — replays journaled utterances instead of
calling a live LLM (PMF Plan Phase 4C Step 8).

Given an ``LLMRequest.replay_context`` carrying ``(session_id,
actor_id, activation_id)``, queries the ledger for matching
``LLMUtteranceEntry`` rows and reconstructs an ``LLMResponse``
whose ``content`` is the journaled ``assistant``-role utterance
text. Zero LLM cost; bit-identical outputs across replays.

Registered under provider name ``"replay"`` by composition root
(``volnix/app.py`` after LLM router + ledger are ready).
``LLMRouter.route`` intercepts ``request.replay_mode=True`` and
delegates to this provider.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from volnix.core.errors import ReplayJournalMismatch
from volnix.llm.provider import LLMProvider
from volnix.llm.types import LLMRequest, LLMResponse, LLMUsage, ProviderInfo

logger = logging.getLogger(__name__)


class ReplayLLMProvider(LLMProvider):
    """LLM provider that replays recorded utterances from the ledger.

    Stateless — each ``generate()`` queries the ledger fresh. No
    in-memory index at 0.2.0; an LRU cache can layer later if the
    replay path becomes hot.

    **Scope limits at 0.2.0 (documented explicitly per Step-8
    post-impl audit C1/H1/H2):**

    - **NPC single-turn path only.** The lead-actor tool-loop
      path in ``AgencyEngine._activate_with_tool_loop`` does NOT
      currently write utterance entries to the journal, so
      lead-actor activations cannot be replayed yet — Step 8
      ships only the deterministic ``activation_id`` derivation
      (prereq) on that path. The follow-up lands the journal
      writer for the lead-actor site.
    - **Tool calls dropped.** ``tool_calls=None`` on the
      reconstructed response. An activation that originally
      invoked tools will replay as a text-only response. Storing
      tool-call payloads is a future extension of the schema.
    - **Single assistant row per activation.** Multi-turn tool
      loops (one activation → N LLM calls) emit N assistant rows
      but this provider returns the first one. A multi-turn
      replay requires an additional ``sequence`` selector in
      ``replay_context`` — tracked for a future step.

    None of these are correctness bugs; they are scope commitments
    for 0.2.0. Consumers targeting replay today MUST use NPC
    single-turn activations.
    """

    provider_name: ClassVar[str] = "replay"

    def __init__(self, ledger: Any) -> None:
        """Construct with the shared ledger (read-only usage — the
        replay provider only ``query()``s, never ``append()``s)."""
        self._ledger = ledger

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Reconstruct an ``LLMResponse`` from the utterance journal.

        Raises ``ReplayJournalMismatch`` when required context is
        missing OR no matching ``assistant``-role entry exists.
        """
        ctx = getattr(request, "replay_context", None) or {}
        required = ("session_id", "actor_id", "activation_id")
        missing = [k for k in required if not ctx.get(k)]
        if missing:
            raise ReplayJournalMismatch(f"replay_context missing required fields: {missing}")

        # Import here to avoid top-of-module circular risk.
        from volnix.ledger.query import LedgerQueryBuilder

        q = (
            LedgerQueryBuilder()
            .filter_type("llm.utterance")
            .filter_session(ctx["session_id"])
            .filter_activation(ctx["activation_id"])
            .limit(100)
            .build()
        )
        entries = await self._ledger.query(q)

        # Filter by actor_id locally — rarely more than a handful
        # of rows match (session, activation) so the O(N) Python
        # filter is fine. Using a dedicated builder method for
        # actor would nest another WHERE clause without benefit.
        target_actor = str(ctx["actor_id"])
        matched = [e for e in entries if str(getattr(e, "actor_id", "")) == target_actor]
        if not matched:
            raise ReplayJournalMismatch(
                f"no utterance entries for activation "
                f"{ctx['activation_id']!r} / actor {target_actor!r}"
            )

        # The assistant row carries the content we replay.
        assistant = next(
            (e for e in matched if getattr(e, "role", "") == "assistant"),
            None,
        )
        if assistant is None:
            raise ReplayJournalMismatch(
                f"no 'assistant' role in replay journal for activation {ctx['activation_id']!r}"
            )

        tokens = int(getattr(assistant, "tokens", 0) or 0)
        return LLMResponse(
            content=str(getattr(assistant, "content", "")),
            tool_calls=None,  # Step-8 NPC path: no tool-role entries.
            usage=LLMUsage(
                prompt_tokens=0,
                completion_tokens=tokens,
                total_tokens=tokens,
                cost_usd=0.0,
            ),
            model="replay",
            provider="replay",
            latency_ms=0.0,
        )

    async def validate_connection(self) -> bool:
        return self._ledger is not None

    async def list_models(self) -> list[str]:
        return ["replay"]

    def get_info(self) -> ProviderInfo:
        return ProviderInfo(
            name="replay",
            type="replay",
            available_models=["replay"],
        )
