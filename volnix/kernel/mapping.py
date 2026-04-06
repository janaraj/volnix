"""Capability-to-tool mapping generator.

Maps semantic capability names (e.g., ``cases.list``, ``messages.send``)
to the actual tool names available in a running Volnix world
(e.g., ``tickets.list``, ``users.messages.send``).

Uses keyword matching against tool names and descriptions — no LLM needed.
The mapping is deterministic and computed at connection time.
"""

from __future__ import annotations

from typing import Any


def generate_target_mapping(
    capabilities: list[str],
    tools: list[dict[str, Any]],
) -> dict[str, str]:
    """Match semantic capabilities to actual tool names.

    Args:
        capabilities: List of semantic capability names
            (e.g., ``["cases.list", "cases.read", "messages.send"]``).
        tools: Tool manifest from ``GET /api/v1/tools``. Each dict
            has at least ``name`` and ``description``.

    Returns:
        Dict mapping each capability to its best-matching tool name.
        Capabilities with no match are omitted.
    """
    mapping: dict[str, str] = {}
    tool_index = _build_tool_index(tools)

    for capability in capabilities:
        keywords = _capability_to_keywords(capability)
        best = _find_best_match(keywords, tool_index)
        if best:
            mapping[capability] = best

    return mapping


def _build_tool_index(tools: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Build a searchable index: tool_name → [keywords from name + description]."""
    index: dict[str, list[str]] = {}
    for tool in tools:
        name = tool.get("name", "")
        desc = str(tool.get("description", "")).lower()
        # Split tool name on underscores and add description words
        name_words = name.lower().replace("-", "_").split("_")
        desc_words = desc.split()
        index[name] = name_words + desc_words
    return index


def _capability_to_keywords(capability: str) -> list[str]:
    """Extract search keywords from a semantic capability name.

    ``cases.list``    → ``["case", "cases", "ticket", "tickets", "list"]``
    ``messages.send`` → ``["message", "messages", "send", "email", "gmail"]``
    ``customers.read``→ ``["customer", "customers", "user", "users", "read", "show"]``

    Uses a small synonym map for common domain terms.
    """
    # Split on dots and underscores
    parts = capability.lower().replace(".", " ").replace("_", " ").split()

    # Expand with synonyms
    expanded: list[str] = []
    for part in parts:
        expanded.append(part)
        for synonym in _SYNONYMS.get(part, []):
            expanded.append(synonym)

    return expanded


# Domain-specific synonyms — maps capability vocabulary to tool vocabulary
_SYNONYMS: dict[str, list[str]] = {
    # Entity types
    "cases": ["ticket", "tickets", "zendesk"],
    "case": ["ticket", "tickets", "zendesk"],
    "messages": ["message", "email", "gmail", "send"],
    "message": ["email", "gmail"],
    "customers": ["customer", "user", "users"],
    "customer": ["user", "users"],
    "comments": ["comment", "note", "notes"],
    "comment": ["note", "notes"],
    "issues": ["issue", "github", "jira"],
    "channels": ["channel", "slack"],
    "events": ["event", "calendar"],
    "payments": ["payment", "charge", "stripe"],
    "orders": ["order", "position", "trade"],
    # Actions
    "list": ["list", "search", "index"],
    "read": ["show", "get", "detail", "read"],
    "create": ["create", "new", "add", "post"],
    "update": ["update", "modify", "edit", "patch"],
    "delete": ["delete", "remove", "destroy"],
    "send": ["send", "post", "deliver"],
}


def _find_best_match(
    keywords: list[str],
    tool_index: dict[str, list[str]],
) -> str | None:
    """Find the tool whose keywords best overlap with the given keywords."""
    best_name: str | None = None
    best_score = 0

    keyword_set = set(keywords)

    for tool_name, tool_keywords in tool_index.items():
        tool_set = set(tool_keywords)
        overlap = len(keyword_set & tool_set)
        if overlap > best_score:
            best_score = overlap
            best_name = tool_name

    return best_name if best_score >= 2 else None  # Require at least 2 keyword matches
