"""Tool-call ↔ tool-response pairing invariant.

OpenAI's Chat Completions API enforces that every ``role="tool"`` message
must be a response to a preceding ``role="assistant"`` message whose
``tool_calls`` declared the matching ``tool_call_id`` — and that every
declared id has a matching response before the next non-tool message.

This module centralises the repair logic so it can be enforced at the
source (e.g. history sanitizers in the agency engine) and as a
belt-and-suspenders boundary guard in the OpenAI provider.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def repair_tool_call_pairing(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop messages that violate the tool_call ↔ tool-response pairing invariant.

    Each ``(assistant-with-tool_calls, tool-responses...)`` segment is
    treated as atomic. If every declared id has a matching response the
    segment is kept (in arrival order). Otherwise the whole segment —
    including any partial responses — is dropped. Stray ``role="tool"``
    messages with no matching preceding assistant are dropped. Plain
    messages (system / user / text-only assistant) pass through.
    """
    result: list[dict[str, Any]] = []
    i = 0
    n = len(messages)
    while i < n:
        msg = messages[i]
        role = msg.get("role")

        if role == "tool":
            # Stray tool message with no preceding assistant block: drop.
            i += 1
            continue

        if role == "assistant" and msg.get("tool_calls"):
            expected_ids = {tc.get("id", "") for tc in msg["tool_calls"]}
            j = i + 1
            seen_ids: set[str] = set()
            responded: list[dict[str, Any]] = []
            while j < n and messages[j].get("role") == "tool":
                tc_id = messages[j].get("tool_call_id", "")
                if tc_id in expected_ids and tc_id not in seen_ids:
                    responded.append(messages[j])
                    seen_ids.add(tc_id)
                # Duplicate or unmatched tool responses are dropped implicitly.
                j += 1

            if seen_ids == expected_ids:
                result.append(msg)
                result.extend(responded)
            else:
                logger.debug(
                    "repair_tool_call_pairing: dropping incomplete block "
                    "(expected_ids=%s answered=%s)",
                    expected_ids,
                    seen_ids,
                )
            i = j
            continue

        # system / user / text-only assistant: preserve.
        result.append(msg)
        i += 1

    return result
