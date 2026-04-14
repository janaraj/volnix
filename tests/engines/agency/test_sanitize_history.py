"""Tests for ``_sanitize_history_for_game_move``.

The sanitizer filters Phase-1 research tool_calls out of the history
before replay for Phase-2 game_move, while preserving game tool_calls
and maintaining OpenAI's strict tool_call ↔ tool-response pairing.
"""

from __future__ import annotations

from volnix.engines.agency.engine import _sanitize_history_for_game_move

GAME_TOOLS = frozenset({"negotiate_propose", "negotiate_counter", "negotiate_accept"})


def _assistant(tool_calls: list[dict]) -> dict:
    return {"role": "assistant", "tool_calls": tool_calls}


def _tc(tc_id: str, name: str) -> dict:
    return {"id": tc_id, "type": "function", "function": {"name": name, "arguments": "{}"}}


def _tool(tc_id: str, content: str = "r") -> dict:
    return {"role": "tool", "tool_call_id": tc_id, "content": content}


def test_preserves_system_and_user():
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]
    assert _sanitize_history_for_game_move(msgs, GAME_TOOLS) == msgs


def test_all_game_block_preserved():
    msgs = [
        {"role": "user", "content": "go"},
        _assistant([_tc("g1", "negotiate_propose")]),
        _tool("g1", "ok"),
    ]
    out = _sanitize_history_for_game_move(msgs, GAME_TOOLS)
    assert out == msgs


def test_all_non_game_block_absorbed_into_research_summary():
    msgs = [
        {"role": "user", "content": "go"},
        _assistant([_tc("r1", "databases.retrieve")]),
        _tool("r1", "finding A"),
    ]
    out = _sanitize_history_for_game_move(msgs, GAME_TOOLS)
    # Assistant and tool gone; research summary inserted.
    assert all(m.get("role") != "tool" for m in out)
    assert not any(m.get("tool_calls") for m in out)
    summary = [m for m in out if m["role"] == "assistant"]
    assert summary and "finding A" in summary[0]["content"]


def test_mixed_branch_strips_non_game_tool_calls():
    """Mixed assistant: non-game tool_calls stripped so no orphan ids remain."""
    msgs = [
        {"role": "user", "content": "go"},
        _assistant([_tc("g1", "negotiate_propose"), _tc("r1", "databases.retrieve")]),
        _tool("g1", "ok"),
        _tool("r1", "finding A"),
    ]
    out = _sanitize_history_for_game_move(msgs, GAME_TOOLS)
    # Find the assistant with tool_calls — it should only have g1 now.
    asst = next(m for m in out if m.get("role") == "assistant" and m.get("tool_calls"))
    assert [tc["id"] for tc in asst["tool_calls"]] == ["g1"]
    # g1 tool response kept; r1 absorbed into research summary.
    tool_msgs = [m for m in out if m.get("role") == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["g1"]
    summary = [m for m in out if m["role"] == "assistant" and not m.get("tool_calls")]
    assert any("finding A" in m["content"] for m in summary)


def test_pairing_invariant_always_holds():
    """Output never contains an assistant with tool_calls missing responses."""
    msgs = [
        _assistant([_tc("g1", "negotiate_propose"), _tc("r1", "databases.retrieve")]),
        _tool("g1", "ok"),
        _tool("r1", "finding"),
        _assistant([_tc("g2", "negotiate_counter")]),
        _tool("g2", "ok"),
    ]
    out = _sanitize_history_for_game_move(msgs, GAME_TOOLS)
    # Walk output: every assistant with tool_calls must be followed by
    # tool responses for ALL its declared ids.
    i = 0
    while i < len(out):
        m = out[i]
        if m.get("role") == "assistant" and m.get("tool_calls"):
            expected = {tc["id"] for tc in m["tool_calls"]}
            seen: set[str] = set()
            j = i + 1
            while j < len(out) and out[j].get("role") == "tool":
                seen.add(out[j]["tool_call_id"])
                j += 1
            assert seen >= expected, f"orphan tool_call ids: {expected - seen}"
            i = j
        else:
            i += 1


def test_partial_prior_turn_block_dropped():
    """Input with assistant-tool_calls but missing responses is dropped entirely."""
    msgs = [
        {"role": "user", "content": "hi"},
        _assistant([_tc("g1", "negotiate_propose")]),
        # No tool response for g1 (e.g. crash mid-turn).
        {"role": "user", "content": "retry"},
    ]
    out = _sanitize_history_for_game_move(msgs, GAME_TOOLS)
    # Incomplete block dropped by final repair pass.
    assert not any(m.get("tool_calls") for m in out)
    assert [m["role"] for m in out] == ["user", "user"]


def test_short_input_passthrough():
    msgs = [{"role": "user", "content": "hi"}]
    assert _sanitize_history_for_game_move(msgs, GAME_TOOLS) == msgs
