"""Provider-agnostic message-history compaction.

Applied once upstream on the generic message-dict list built by the
agency engine, before any provider-specific sanitization runs. Keeps
prompts from growing linearly with tool-loop iteration count.

Design:
- Operates purely on the shape ``{"role": ..., "content": ..., ...}``
  that the agency engine builds. No provider SDK objects, no
  provider-specific keys are touched.
- Only ``role == "tool"`` entries are modified. Their ``tool_call_id``
  and position are preserved — pairing invariants (enforced downstream
  by ``_tool_pairing.repair_tool_call_pairing`` for OpenAI and by the
  agency history sanitizer for other providers) continue to hold.
- Pure function: returns a new list, never mutates the input.
"""

from __future__ import annotations

from typing import Any

_ELIDED_MARKER = "[elided]"


def compact_tool_results(
    messages: list[dict[str, Any]],
    keep_last: int,
    max_chars: int,
) -> list[dict[str, Any]]:
    """Compact tool-result messages in place-safe fashion.

    Args:
        messages: Generic message dicts. Only entries with
            ``role == "tool"`` are considered for compaction.
        keep_last: Number of most-recent tool-result messages whose
            ``content`` is retained (subject to ``max_chars`` truncation).
            Older tool-result messages have their ``content`` replaced
            with a short elision marker. Must be ``>= 0``.
        max_chars: Character cap applied to every tool-result
            ``content`` that is NOT elided. ``<= 0`` disables the cap.

    Returns:
        A new list with the same length, ordering, and non-tool messages
        as the input. Tool messages have rewritten ``content`` strings.
    """
    if keep_last < 0:
        keep_last = 0

    # Index positions of all tool-result messages, oldest-first.
    tool_indices = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    if not tool_indices:
        # Nothing to compact — return a shallow copy so caller can treat
        # the result as independent of the input.
        return list(messages)

    # Positions that stay verbatim (still subject to max_chars).
    verbatim_indices = set(tool_indices[-keep_last:]) if keep_last else set()

    result: list[dict[str, Any]] = []
    for i, msg in enumerate(messages):
        if msg.get("role") != "tool":
            result.append(msg)
            continue

        new_msg = dict(msg)
        if i in verbatim_indices:
            content = new_msg.get("content", "")
            if max_chars > 0 and isinstance(content, str) and len(content) > max_chars:
                new_msg["content"] = content[:max_chars]
        else:
            new_msg["content"] = _ELIDED_MARKER
        result.append(new_msg)

    return result
