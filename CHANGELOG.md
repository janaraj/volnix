# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
