"""Tests for external agent slot binding."""

from __future__ import annotations

from terrarium.actors.slot_binding import SlotBinding
from terrarium.core.types import ActorId


class TestSlotBinding:
    """Tests for SlotBinding in-memory slot manager."""

    def test_claim_slot_success(self) -> None:
        """An agent can claim an unclaimed slot."""
        sb = SlotBinding()
        result = sb.claim_slot(ActorId("agent-1"), "session-abc")
        assert result is True
        assert sb.is_slot_claimed(ActorId("agent-1"))
        assert sb.connected_count() == 1

    def test_claim_same_slot_twice_fails(self) -> None:
        """A different session cannot claim a slot already claimed by another."""
        sb = SlotBinding()
        sb.claim_slot(ActorId("agent-1"), "session-abc")
        result = sb.claim_slot(ActorId("agent-1"), "session-xyz")
        assert result is False
        # Original binding should remain
        assert sb.get_session_for_actor(ActorId("agent-1")) == "session-abc"

    def test_reconnect_same_session(self) -> None:
        """The same session can re-claim its own slot (reconnect)."""
        sb = SlotBinding()
        sb.claim_slot(ActorId("agent-1"), "session-abc")
        result = sb.claim_slot(ActorId("agent-1"), "session-abc")
        assert result is True
        assert sb.connected_count() == 1

    def test_release_slot(self) -> None:
        """Releasing a slot frees it for another session."""
        sb = SlotBinding()
        sb.claim_slot(ActorId("agent-1"), "session-abc")
        released = sb.release_slot("session-abc")
        assert released == ActorId("agent-1")
        assert not sb.is_slot_claimed(ActorId("agent-1"))
        assert sb.connected_count() == 0

        # Now another session can claim it
        result = sb.claim_slot(ActorId("agent-1"), "session-xyz")
        assert result is True

    def test_release_nonexistent_session(self) -> None:
        """Releasing a session that doesn't exist returns None."""
        sb = SlotBinding()
        released = sb.release_slot("nonexistent")
        assert released is None

    def test_max_agents_limit(self) -> None:
        """Cannot claim more slots than max_agents."""
        sb = SlotBinding(max_agents=2)
        assert sb.claim_slot(ActorId("a1"), "s1") is True
        assert sb.claim_slot(ActorId("a2"), "s2") is True
        assert sb.claim_slot(ActorId("a3"), "s3") is False
        assert sb.connected_count() == 2

    def test_get_actor_for_session(self) -> None:
        """get_actor_for_session returns the actor bound to a session."""
        sb = SlotBinding()
        sb.claim_slot(ActorId("agent-1"), "session-abc")
        assert sb.get_actor_for_session("session-abc") == ActorId("agent-1")
        assert sb.get_actor_for_session("unknown") is None

    def test_get_session_for_actor(self) -> None:
        """get_session_for_actor returns the session bound to an actor."""
        sb = SlotBinding()
        sb.claim_slot(ActorId("agent-1"), "session-abc")
        assert sb.get_session_for_actor(ActorId("agent-1")) == "session-abc"
        assert sb.get_session_for_actor(ActorId("unknown")) is None

    def test_list_connected(self) -> None:
        """list_connected returns all currently connected actor_ids."""
        sb = SlotBinding()
        sb.claim_slot(ActorId("a1"), "s1")
        sb.claim_slot(ActorId("a2"), "s2")
        connected = sb.list_connected()
        assert len(connected) == 2
        ids = {str(a) for a in connected}
        assert "a1" in ids
        assert "a2" in ids

    def test_list_connected_empty(self) -> None:
        """list_connected returns empty list when no agents are connected."""
        sb = SlotBinding()
        assert sb.list_connected() == []

    def test_release_then_reclaim_by_different_session(self) -> None:
        """After release, a different session can claim the same slot."""
        sb = SlotBinding()
        sb.claim_slot(ActorId("agent-1"), "session-abc")
        sb.release_slot("session-abc")

        result = sb.claim_slot(ActorId("agent-1"), "session-xyz")
        assert result is True
        assert sb.get_session_for_actor(ActorId("agent-1")) == "session-xyz"

    def test_max_agents_after_release(self) -> None:
        """Releasing a slot frees capacity for new connections."""
        sb = SlotBinding(max_agents=1)
        sb.claim_slot(ActorId("a1"), "s1")
        assert sb.claim_slot(ActorId("a2"), "s2") is False

        sb.release_slot("s1")
        assert sb.claim_slot(ActorId("a2"), "s2") is True
