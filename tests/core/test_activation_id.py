"""Phase 4C Step 7 — activation_id determinism tests.

Locks the Step-8 replay contract: when a session_id is present,
``generate_activation_id`` MUST return the same 12-char id for the
same (session, actor, tick, index) tuple across processes
(PYTHONHASHSEED-independent via uuid5). When no session is
active, falls back to uuid4 — matches pre-Step-7 behaviour so
non-session runs stay identical.

Negative ratio: 3/5 = 60%.
"""

from __future__ import annotations

from volnix.core.types import ActivationId, ActorId, SessionId, generate_activation_id


def test_negative_no_session_falls_back_to_uuid4() -> None:
    """Without a session_id, each call returns a unique value —
    preserves the pre-Step-7 uuid4 behaviour for non-session runs
    so existing tests keep passing."""
    aid1 = generate_activation_id(session_id=None, actor_id=ActorId("a"), tick=0)
    aid2 = generate_activation_id(session_id=None, actor_id=ActorId("a"), tick=0)
    assert aid1 != aid2
    assert isinstance(aid1, str)
    assert len(aid1) == 12


def test_positive_same_inputs_same_id() -> None:
    """With the same (session, actor, tick, activation_index),
    two calls return the same id. uuid5 is PYTHONHASHSEED-
    independent by spec — same-process repeatability is a proxy
    for cross-process stability (audit-fold M2)."""
    a = generate_activation_id(
        session_id=SessionId("sess-1"),
        actor_id=ActorId("actor-1"),
        tick=5,
        activation_index=0,
    )
    b = generate_activation_id(
        session_id=SessionId("sess-1"),
        actor_id=ActorId("actor-1"),
        tick=5,
        activation_index=0,
    )
    assert a == b


def test_negative_different_tick_different_id() -> None:
    """Changing just the tick produces a different id — locks
    that tick is part of the derivation key."""
    kwargs = {
        "session_id": SessionId("s"),
        "actor_id": ActorId("a"),
        "activation_index": 0,
    }
    assert generate_activation_id(tick=0, **kwargs) != generate_activation_id(tick=1, **kwargs)


def test_negative_different_activation_index_different_id() -> None:
    """Parallel activations at the same tick must not collide.
    Audit-fold H2: renamed ``sequence`` to ``activation_index``
    to distinguish from the per-utterance sequence column."""
    kwargs = {
        "session_id": SessionId("s"),
        "actor_id": ActorId("a"),
        "tick": 0,
    }
    assert generate_activation_id(activation_index=0, **kwargs) != generate_activation_id(
        activation_index=1, **kwargs
    )


def test_positive_activation_id_is_12_char_hex() -> None:
    """Format lock: 12 characters, lowercase hex."""
    aid = generate_activation_id(
        session_id=SessionId("s"),
        actor_id=ActorId("a"),
        tick=0,
        activation_index=0,
    )
    assert len(aid) == 12
    assert all(c in "0123456789abcdef" for c in aid)
    # ActivationId NewType is zero-runtime but the returned value
    # is str at runtime; type-checkers see ActivationId.
    assert isinstance(aid, str)
    _: ActivationId = aid  # type check only
