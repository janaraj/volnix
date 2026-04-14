"""Configuration for the AgencyEngine."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AgencyConfig(BaseModel):
    """Config for the AgencyEngine."""

    model_config = ConfigDict(frozen=True)

    # ── Tier classification ─────────────────────────────────────
    # Promote actor to Tier 3 (individual LLM) if frustration >= this.
    frustration_threshold_tier3: float = 0.7
    # Roles always classified as Tier 3 regardless of frustration.
    high_stakes_roles: list[str] = Field(default_factory=list)

    # ── Batch settings ──────────────────────────────────────────
    # Max actors per Tier 2 batch LLM call.
    batch_size: int = 5

    # ── Patience / frustration ──────────────────────────────────
    # Frustration delta when patience expires without resolution.
    frustration_increase_per_patience: float = 0.1
    # Frustration delta after a positive event (goal progress, etc.).
    frustration_decrease_per_positive: float = 0.1
    # Default patience (logical time units) before frustration increases.
    default_patience: float = 300.0

    # ── Actor state management ──────────────────────────────────
    # Max recent interactions kept per actor (older ones trimmed).
    max_recent_interactions: int = 20
    # Max pending notification count per actor before dropping.
    max_pending_notifications: int = 50

    # ── Concurrency ─────────────────────────────────────────────
    # Semaphore limit for concurrent LLM calls across all actors.
    max_concurrent_actor_calls: int = 20
    # Max actors that can activate from a single committed event.
    max_activations_per_event: int = 100
    # Max response envelopes from agency per committed event.
    max_envelopes_per_event: int = 50

    # ── LLM routing ─────────────────────────────────────────────
    # Router builds key as "{engine_name}_{use_case}".
    # Engine name is "agency", so "individual" → "agency_individual".
    llm_use_case_individual: str = "individual"
    llm_use_case_batch: str = "batch"

    # ── Collaborative communication ─────────────────────────────
    # "tagged" = honor intended_for field; "open" = all actors see all messages.
    collaboration_mode: str = "tagged"
    # Enable subscription-based activation for collaborative actors.
    collaboration_enabled: bool = True
    # V2: Batch N notifications before activating (reduces LLM calls for chatty channels).
    # Unused in MVP — all subscriptions activate immediately.
    batch_threshold_default: int = 3
    # Reserve this % of max_ticks for final synthesis/deliverable production.
    synthesis_buffer_pct: float = 0.1
    # Logical time between autonomous agent activations (work loop interval).
    autonomous_tick_interval: float = 60.0
    # (Future) Auto-add chat service subscription for all internal actors.
    # auto_include_chat: bool = True  -- not yet enforced

    # ── History sanitisation ──────────────────────────────────
    # Max chars kept when summarising Phase 1 research history before
    # Phase 2 game-move activation.  Prevents hallucination from long
    # non-game tool_call context.
    history_sanitize_char_limit: int = 8000

    # ── Multi-turn tool loop ──────────────────────────────────
    # Max tool calls within a single agent activation loop.
    max_tool_calls_per_activation: int = 10
    # LLM tool_choice mode for agent activations: "auto" allows text responses.
    tool_choice_mode: str = "auto"
    # Max entries retained in an actor's rolling ``activation_messages``
    # window after a ``state_summary`` is injected by GameOrchestrator
    # re-activations (roughly ``max_activation_messages / 2`` exchanges).
    # Caps prompt size for long games.
    max_activation_messages: int = 20
    # Number of most-recent tool-result messages kept verbatim within a
    # single activation's tool loop. Older tool results have their
    # ``content`` replaced with an elision marker so prompts don't grow
    # linearly with iteration count. Pairing (tool_call_id ↔ tool result)
    # is preserved — only the content string is rewritten.
    max_verbatim_tool_results: int = 3
    # Per-tool-result character cap applied on every iteration (both
    # kept-verbatim and any new result). Prevents a single huge payload
    # from dominating the prompt.
    max_tool_result_chars: int = 800
