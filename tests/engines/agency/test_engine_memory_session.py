"""Session-scope contract tests for AgencyEngine's memory call sites.

Pins the MUST clause from ``tnl/session-scoped-memory.tnl``:
``AgencyEngine._activate_with_tool_loop`` MUST pass
``self._session_id`` to both ``recall_for_activation`` and
``implicit_remember_activation`` on every call.

Uses source inspection rather than end-to-end activation because
the AgencyEngine tool loop requires a full LLM-router + pipeline
stack to drive — the point of this test is to catch regressions at
the call sites, which source inspection does cleanly.

This mirrors the audit-fold pattern used for the D10 double-fire
assertion: source-inspection is fair game when driving the real
call path would require a heavyweight fixture.
"""

from __future__ import annotations

import inspect

from volnix.engines.agency.engine import AgencyEngine


def test_positive_activate_with_tool_loop_forwards_session_id_to_recall_helper() -> None:
    source = inspect.getsource(AgencyEngine._activate_with_tool_loop)
    # Find the recall_for_activation call and inspect the kwargs
    # literal. The presence of ``session_id=self._session_id`` in
    # the same call-body is what satisfies the TNL clause.
    assert "recall_for_activation" in source, (
        "expected recall_for_activation call to be present in _activate_with_tool_loop"
    )
    # Narrower: the TNL-mandated kwarg literal.
    assert "session_id=self._session_id" in source, (
        "expected _activate_with_tool_loop to pass "
        "session_id=self._session_id; "
        "tnl/session-scoped-memory.tnl requires this forwarding"
    )


def test_positive_activate_with_tool_loop_forwards_session_id_to_remember_helper() -> None:
    source = inspect.getsource(AgencyEngine._activate_with_tool_loop)
    assert "implicit_remember_activation" in source
    # Both call sites forward; count the forwarding-literal occurrences.
    # There are two call sites (recall + remember), so we expect at
    # least 2 instances of the forward.
    assert source.count("session_id=self._session_id") >= 2, (
        "expected both recall_for_activation AND "
        "implicit_remember_activation call sites in "
        "_activate_with_tool_loop to forward self._session_id; "
        "tnl/session-scoped-memory.tnl requires both"
    )
