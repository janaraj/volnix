"""Tests for ``tnl/animator-event-volume-reduction.tnl``.

Two MUSTs under test:
- B. ``AnimatorConfig.creativity_budget_per_tick`` default is 1.
- A. Activity-gated ``_dynamic_tick_loop`` — flag initialized True
  on the app, the bus subscriber sets it on non-animator committed
  events, the dynamic tick loop reads-and-clears it.

The dynamic-tick-loop body and the ``_on_committed_event`` closure
are both defined INSIDE ``VolnixApp._start_animator_bridge``. Driving
them via a real app start is heavyweight, so the closure-logic
invariants are locked via ``inspect.getsource`` (same audit pattern
we used for the session-id forwarding guards in
``test_engine_memory_session.py``). The flag initialization is
tested directly on a fresh ``VolnixApp``.
"""

from __future__ import annotations

import inspect

from volnix.app import VolnixApp
from volnix.config.schema import VolnixConfig
from volnix.engines.animator.config import AnimatorConfig

# ---------------------------------------------------------------------------
# B. creativity_budget_per_tick default
# ---------------------------------------------------------------------------


class TestCreativityBudgetDefault:
    def test_positive_default_is_one(self) -> None:
        """TNL B: default MUST be 1 (down from 3)."""
        cfg = AnimatorConfig()
        assert cfg.creativity_budget_per_tick == 1

    def test_positive_explicit_override_still_accepted(self) -> None:
        """Worlds that want higher volume set it explicitly via
        ``animator_settings``. The default flip MUST NOT invalidate
        explicit 3 (nor any other positive int)."""
        cfg = AnimatorConfig(creativity_budget_per_tick=3)
        assert cfg.creativity_budget_per_tick == 3


# ---------------------------------------------------------------------------
# A. Activity-gated _dynamic_tick_loop
# ---------------------------------------------------------------------------


class TestActivityGateFlagOnApp:
    """The flag is an attribute of the app itself, not a closure variable,
    so external callers (tests, future code) can inspect and drive it.
    """

    def test_positive_flag_initialized_true_on_fresh_app(self) -> None:
        """TNL A: flag starts True so the first scheduled tick always
        fires after bridge-start."""
        app = VolnixApp(config=VolnixConfig())
        assert app._animator_has_activity_since_last_tick is True

    def test_positive_flag_is_writable_plain_bool(self) -> None:
        """Not an asyncio primitive — just a bool. The atomicity guard
        in the TNL relies on single-assignment semantics under asyncio
        (no await between the check-and-clear in the loop body)."""
        app = VolnixApp(config=VolnixConfig())
        assert isinstance(app._animator_has_activity_since_last_tick, bool)
        app._animator_has_activity_since_last_tick = False
        assert app._animator_has_activity_since_last_tick is False


class TestBridgeClosureLogic:
    """Source-inspection guards locking the closure-body contract
    inside ``VolnixApp._start_animator_bridge``. A future refactor
    that removes the flag wiring or moves it to the wrong closure
    surfaces here as a structural test failure."""

    def test_positive_on_committed_event_sets_flag_after_actor_filter(self) -> None:
        """TNL A: the subscriber MUST set the flag on every qualifying
        committed event (non-system/animator/world_compiler actor).
        The assignment MUST sit after the actor-filter early-return so
        organic events from ``actor=system`` don't set the flag.
        """
        source = inspect.getsource(VolnixApp._start_animator_bridge)
        # The filter-then-set sequence is load-bearing. We look for the
        # combined pattern: the system/animator/world_compiler return
        # followed somewhere below by the flag assignment.
        lines = source.splitlines()
        filter_idx = next(
            (i for i, line in enumerate(lines) if '"system", "animator", "world_compiler"' in line),
            None,
        )
        flag_set_idx = next(
            (
                i
                for i, line in enumerate(lines)
                if "_animator_has_activity_since_last_tick = True" in line
            ),
            None,
        )
        assert filter_idx is not None, (
            "expected actor-filter line with system/animator/world_compiler triple"
        )
        assert flag_set_idx is not None, (
            "expected flag-assignment line '_animator_has_activity_since_last_tick = True'"
        )
        assert flag_set_idx > filter_idx, (
            "activity-gate flag MUST be set AFTER the actor-filter early-return so "
            "system/animator/world_compiler events don't mark activity "
            "(tnl/animator-event-volume-reduction.tnl)"
        )

    def test_positive_dynamic_tick_loop_skips_when_flag_is_false(self) -> None:
        """TNL A: the loop body MUST check the flag, ``continue`` past
        tick() when False, and clear the flag BEFORE calling tick() so
        activity arriving during the tick counts toward the NEXT
        iteration."""
        source = inspect.getsource(VolnixApp._start_animator_bridge)
        # Must have the early-return guard:
        assert "if not self._animator_has_activity_since_last_tick:" in source, (
            "dynamic tick loop MUST gate tick() on _animator_has_activity_since_last_tick"
        )
        # Must clear the flag before firing:
        assert "self._animator_has_activity_since_last_tick = False" in source, (
            "loop MUST clear the flag before firing tick() so mid-tick activity "
            "counts toward the NEXT iteration"
        )
        # Structural ordering: the clear appears after the guard and
        # before ``await animator.tick`` in the same function body.
        lines = source.splitlines()
        guard_idx = next(
            i
            for i, line in enumerate(lines)
            if "if not self._animator_has_activity_since_last_tick:" in line
        )
        clear_idx = next(
            i
            for i, line in enumerate(lines)
            if "self._animator_has_activity_since_last_tick = False" in line
        )
        # The FIRST "await animator.tick" in the source belongs to the
        # subscriber's reactive path; we need the one INSIDE the
        # dynamic tick loop, which is the first such line AFTER the
        # flag clear.
        tick_idx = next(
            i
            for i, line in enumerate(lines[clear_idx + 1 :], start=clear_idx + 1)
            if "await animator.tick(datetime.now(UTC))" in line
        )
        assert guard_idx < clear_idx < tick_idx, (
            f"expected guard ({guard_idx}) → clear ({clear_idx}) → tick ({tick_idx}) ordering "
            f"in _start_animator_bridge"
        )
