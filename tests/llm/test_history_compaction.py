"""Tests for provider-agnostic tool-result compaction."""

from __future__ import annotations

from volnix.llm._history_compaction import compact_tool_results


def _tool_msg(call_id: str, content: str) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": content}


def _assistant_with_tc(tc_id: str) -> dict:
    return {
        "role": "assistant",
        "tool_calls": [{"id": tc_id, "type": "function", "function": {"name": "x"}}],
    }


def test_empty_list_returns_empty():
    assert compact_tool_results([], keep_last=3, max_chars=800) == []


def test_no_tool_messages_untouched():
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    out = compact_tool_results(msgs, keep_last=3, max_chars=800)
    assert out == msgs
    # Pure function — returned list is a fresh object.
    assert out is not msgs


def test_fewer_than_keep_last_no_elision_but_char_cap_applies():
    long = "x" * 2000
    msgs = [
        _assistant_with_tc("a"),
        _tool_msg("a", long),
        _assistant_with_tc("b"),
        _tool_msg("b", long),
    ]
    out = compact_tool_results(msgs, keep_last=3, max_chars=800)
    assert out[1]["content"] == "x" * 800
    assert out[3]["content"] == "x" * 800
    # tool_call_id preserved
    assert out[1]["tool_call_id"] == "a"
    assert out[3]["tool_call_id"] == "b"


def test_older_tool_results_elided_last_n_kept():
    long = "y" * 2000
    msgs = [
        _assistant_with_tc("a"),
        _tool_msg("a", long),  # oldest → elided
        _assistant_with_tc("b"),
        _tool_msg("b", long),  # elided
        _assistant_with_tc("c"),
        _tool_msg("c", long),  # kept (last 3)
        _assistant_with_tc("d"),
        _tool_msg("d", long),  # kept
        _assistant_with_tc("e"),
        _tool_msg("e", long),  # kept
    ]
    out = compact_tool_results(msgs, keep_last=3, max_chars=500)

    assert out[1]["content"] == "[elided]"
    assert out[3]["content"] == "[elided]"
    assert out[5]["content"] == "y" * 500
    assert out[7]["content"] == "y" * 500
    assert out[9]["content"] == "y" * 500
    # tool_call_id preserved on every tool message, even elided ones.
    assert [out[i]["tool_call_id"] for i in (1, 3, 5, 7, 9)] == ["a", "b", "c", "d", "e"]
    # Assistant messages (with tool_calls) untouched.
    for i in (0, 2, 4, 6, 8):
        assert out[i] == msgs[i]


def test_keep_last_zero_elides_all():
    msgs = [_tool_msg("a", "data"), _tool_msg("b", "data")]
    out = compact_tool_results(msgs, keep_last=0, max_chars=800)
    assert out[0]["content"] == "[elided]"
    assert out[1]["content"] == "[elided]"


def test_negative_keep_last_treated_as_zero():
    msgs = [_tool_msg("a", "data")]
    out = compact_tool_results(msgs, keep_last=-1, max_chars=800)
    assert out[0]["content"] == "[elided]"


def test_max_chars_zero_or_negative_disables_truncation():
    big = "z" * 5000
    msgs = [_tool_msg("a", big)]
    out = compact_tool_results(msgs, keep_last=1, max_chars=0)
    assert out[0]["content"] == big
    out2 = compact_tool_results(msgs, keep_last=1, max_chars=-5)
    assert out2[0]["content"] == big


def test_short_content_under_cap_unchanged():
    msgs = [_tool_msg("a", "short")]
    out = compact_tool_results(msgs, keep_last=1, max_chars=800)
    assert out[0]["content"] == "short"


def test_input_not_mutated():
    long = "q" * 1500
    msgs = [_tool_msg("a", long), _tool_msg("b", long), _tool_msg("c", long)]
    _ = compact_tool_results(msgs, keep_last=1, max_chars=400)
    # Original list still has original content.
    assert msgs[0]["content"] == long
    assert msgs[1]["content"] == long
    assert msgs[2]["content"] == long


def test_pairing_preserved_in_mixed_conversation():
    """End-to-end shape check: every tool msg retains its tool_call_id,
    and the sequence of roles is identical to the input."""
    msgs = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
        _assistant_with_tc("t1"),
        _tool_msg("t1", "r1" * 2000),
        _assistant_with_tc("t2"),
        _tool_msg("t2", "r2" * 2000),
        _assistant_with_tc("t3"),
        _tool_msg("t3", "r3" * 2000),
    ]
    out = compact_tool_results(msgs, keep_last=2, max_chars=100)

    # Role sequence identical.
    assert [m["role"] for m in out] == [m["role"] for m in msgs]
    # All tool_call_ids preserved in order.
    tool_ids_in = [m["tool_call_id"] for m in msgs if m["role"] == "tool"]
    tool_ids_out = [m["tool_call_id"] for m in out if m["role"] == "tool"]
    assert tool_ids_in == tool_ids_out
    # Oldest tool result elided, last two kept (truncated).
    assert out[3]["content"] == "[elided]"
    assert out[5]["content"].startswith("r2")
    assert len(out[5]["content"]) == 100
    assert out[7]["content"].startswith("r3")
    assert len(out[7]["content"]) == 100
