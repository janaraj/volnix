# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.8] - 2026-04-13

### Added

- **LLM cache observability**: `LLMUsage.cached_tokens` + `LLMCallEntry.cached_tokens` record per-provider prompt-cache hits across all three providers (Gemini `cached_content_token_count`, OpenAI `prompt_tokens_details.cached_tokens`, Anthropic `cache_read_input_tokens`).
- **Tool-result compaction** for long multi-turn activations: `volnix/llm/_history_compaction.py` elides older tool-result content while preserving `tool_call_id` pairing, keeping prompt size flat across iterations.
- `AgencyConfig.max_verbatim_tool_results` (default 3) and `AgencyConfig.max_tool_result_chars` (default 800).
- Per-agent LLM provider routing in game blueprints (cross-provider head-to-head, e.g. Claude vs. Gemini in the same contest).

### Changed

- **Game engine rewritten event-driven**: round-based `GameRunner` / `TurnManager` replaced by `GameOrchestrator` + `GameActivePolicy` + scorer strategy package (`BehavioralScorer`, `CompetitiveScorer`). No rounds, no turns — the orchestrator subscribes to committed game-tool events, scores each, and re-activates the next player. Blueprint `flow.type: event_driven` with `max_events` / `stalemate_timeout_seconds` / `max_wall_clock_seconds` / `all_budgets_exhausted` failsafes. Legacy `rounds` / `turn_protocol` / `between_rounds` keys are rejected at compile time.
- Agency multi-turn loop keeps the last N tool results verbatim and elides older ones — flat prompt growth across iterations.
- Dashboard decision-trace tab hardened (null safety, type fixes); richer post-mortem narrative.
- `supply_chain_disruption` and `negotiation_competition` blueprints rewritten against the event-driven schema.

### Fixed

- Multi-turn tool-loop dropped tool calls on certain provider message shapes — cross-provider pairing repair centralized in `volnix/llm/_tool_pairing.py`.
- `LLMUsage` accepts `None` for token fields (Gemini intermittently returns null counts) via pydantic `field_validator(mode="before")`.
- Pre-existing real-API test guarded behind `VOLNIX_RUN_REAL_API_TESTS`.
- Hollow decision trace when no mutations committed in a turn.

## [0.1.0] - 2026-04-03

### Added

- 10-engine architecture: State, Policy, Permission, Budget, World Responder, World Animator, Agency, Agent Adapter, Report Generator, Feedback
- World Compiler: natural language and YAML world definitions compiled into runnable simulations
- 7-step governance pipeline: permission, policy, budget, capability, responder, validation, commit
- CLI with 28 commands: create, run, serve, mcp, dashboard, blueprints, report, check, config, attach, detach, inspect, diff, and more
- REST API with 39 endpoints + WebSocket live event streaming
- MCP server for agent integration (stdio and HTTP transports)
- React dashboard for run observation, scorecards, deliverables, and comparison
- 10 verified service packs: Gmail, Slack, Zendesk, Stripe, GitHub, Google Calendar, Twitter, Reddit, Alpaca, Browser
- 15 official blueprints: customer support, incident response, open sandbox, market prediction, campaign brainstorm, climate research, feature prioritization, security assessment, support ticket triage, governance test, and 5 internal agent team templates
- Multi-provider LLM routing: Anthropic, OpenAI, Google Gemini, Ollama, CLI-based, ACP-based
- Reality dimensions: information quality, reliability, social friction, complexity, boundaries (with ideal/messy/hostile presets)
- Behavior modes: static, reactive, dynamic
- Internal agent simulation with collaborative communication, subscriptions, and deliverable synthesis
- Python SDK client for programmatic access
- Agent config integration: one-command attach for Claude Desktop, Cursor, Windsurf
- Config export for OpenAI, Anthropic, LangGraph, CrewAI, AutoGen formats
- Layered TOML configuration system with environment and local overrides
- SQLite async persistence with WAL mode
- Event bus for inter-engine communication
- Ledger for audit logging and observability
- Seeded reproducibility: same seed produces same world state
