"""Tests for volnix.actors.registry -- ActorRegistry with generic query()."""

import pytest

from volnix.core.types import ActorId, ActorType
from volnix.core.errors import ActorNotFoundError, DuplicateActorError
from volnix.actors.definition import ActorDefinition
from volnix.actors.personality import FrictionProfile
from volnix.actors.registry import ActorRegistry


def _make_actor(
    id: str = "a1",
    role: str = "customer",
    type: ActorType = ActorType.HUMAN,
    team: str | None = None,
    friction: FrictionProfile | None = None,
) -> ActorDefinition:
    """Helper to create test ActorDefinition instances."""
    return ActorDefinition(
        id=ActorId(id),
        type=type,
        role=role,
        team=team,
        friction_profile=friction,
    )


class TestActorRegistry:
    """Verify ActorRegistry registration, retrieval, and query."""

    def test_register_and_get(self) -> None:
        """Registering an actor makes it retrievable by ID."""
        reg = ActorRegistry()
        actor = _make_actor(id="a1")
        reg.register(actor)
        result = reg.get(ActorId("a1"))
        assert result.id == ActorId("a1")
        assert result.role == "customer"

    def test_duplicate_raises(self) -> None:
        """Registering an actor with duplicate ID raises DuplicateActorError."""
        reg = ActorRegistry()
        actor = _make_actor(id="a1")
        reg.register(actor)
        with pytest.raises(DuplicateActorError):
            reg.register(actor)

    def test_not_found_raises(self) -> None:
        """Getting a non-existent actor raises ActorNotFoundError."""
        reg = ActorRegistry()
        with pytest.raises(ActorNotFoundError):
            reg.get(ActorId("nonexistent"))

    def test_get_or_none(self) -> None:
        """get_or_none returns None for missing actors instead of raising."""
        reg = ActorRegistry()
        result = reg.get_or_none(ActorId("nonexistent"))
        assert result is None

        actor = _make_actor(id="a1")
        reg.register(actor)
        result = reg.get_or_none(ActorId("a1"))
        assert result is not None
        assert result.id == ActorId("a1")

    def test_query_by_role(self) -> None:
        """query(role=...) filters actors by role."""
        reg = ActorRegistry()
        reg.register(_make_actor(id="c1", role="customer"))
        reg.register(_make_actor(id="c2", role="customer"))
        reg.register(_make_actor(id="a1", role="support-agent", type=ActorType.AGENT))

        results = reg.query(role="customer")
        assert len(results) == 2
        assert all(a.role == "customer" for a in results)

    def test_query_by_type(self) -> None:
        """query(type=...) filters actors by ActorType."""
        reg = ActorRegistry()
        reg.register(_make_actor(id="h1", type=ActorType.HUMAN))
        reg.register(_make_actor(id="h2", type=ActorType.HUMAN))
        reg.register(_make_actor(id="a1", role="agent", type=ActorType.AGENT))

        results = reg.query(type=ActorType.HUMAN)
        assert len(results) == 2
        assert all(a.type == ActorType.HUMAN for a in results)

    def test_query_by_team(self) -> None:
        """query(team=...) filters actors by team."""
        reg = ActorRegistry()
        reg.register(_make_actor(id="s1", role="support-agent", team="support"))
        reg.register(_make_actor(id="s2", role="support-agent", team="support"))
        reg.register(_make_actor(id="f1", role="reviewer", team="finance"))

        results = reg.query(team="support")
        assert len(results) == 2
        assert all(a.team == "support" for a in results)

    def test_query_has_friction(self) -> None:
        """query(has_friction=True) returns only actors with friction profiles."""
        reg = ActorRegistry()
        fp = FrictionProfile(category="uncooperative", intensity=40)
        reg.register(_make_actor(id="c1", friction=fp))
        reg.register(_make_actor(id="c2"))  # no friction
        reg.register(_make_actor(id="c3"))  # no friction

        with_friction = reg.query(has_friction=True)
        assert len(with_friction) == 1
        assert with_friction[0].id == ActorId("c1")

        without_friction = reg.query(has_friction=False)
        assert len(without_friction) == 2

    def test_query_friction_category(self) -> None:
        """query(friction_category=...) filters by friction category."""
        reg = ActorRegistry()
        reg.register(_make_actor(id="c1", friction=FrictionProfile(category="hostile", intensity=80)))
        reg.register(_make_actor(id="c2", friction=FrictionProfile(category="uncooperative", intensity=30)))
        reg.register(_make_actor(id="c3"))  # no friction

        hostile = reg.query(friction_category="hostile")
        assert len(hostile) == 1
        assert hostile[0].id == ActorId("c1")

    def test_query_multiple_filters(self) -> None:
        """query() with multiple filters uses AND logic."""
        reg = ActorRegistry()
        fp = FrictionProfile(category="hostile", intensity=80)
        reg.register(_make_actor(id="c1", role="customer", friction=fp))
        reg.register(_make_actor(id="c2", role="customer"))
        reg.register(_make_actor(id="a1", role="support-agent", type=ActorType.AGENT))

        results = reg.query(role="customer", has_friction=True)
        assert len(results) == 1
        assert results[0].id == ActorId("c1")

    def test_query_no_filters(self) -> None:
        """query() with no filters returns all actors."""
        reg = ActorRegistry()
        reg.register(_make_actor(id="a1"))
        reg.register(_make_actor(id="a2"))
        reg.register(_make_actor(id="a3"))

        results = reg.query()
        assert len(results) == 3

    def test_query_no_results(self) -> None:
        """query() returns empty list when no actors match."""
        reg = ActorRegistry()
        reg.register(_make_actor(id="c1", role="customer"))

        results = reg.query(role="nonexistent-role")
        assert results == []

    def test_register_batch(self) -> None:
        """register_batch registers multiple actors at once."""
        reg = ActorRegistry()
        actors = [
            _make_actor(id="a1", role="customer"),
            _make_actor(id="a2", role="customer"),
            _make_actor(id="a3", role="support-agent", type=ActorType.AGENT),
        ]
        reg.register_batch(actors)
        assert reg.count() == 3

    def test_list_actors(self) -> None:
        """list_actors returns all registered actors."""
        reg = ActorRegistry()
        reg.register(_make_actor(id="a1"))
        reg.register(_make_actor(id="a2"))

        actors = reg.list_actors()
        assert len(actors) == 2
        ids = {a.id for a in actors}
        assert ActorId("a1") in ids
        assert ActorId("a2") in ids

    def test_count(self) -> None:
        """count() returns total number of registered actors."""
        reg = ActorRegistry()
        assert reg.count() == 0
        reg.register(_make_actor(id="a1"))
        assert reg.count() == 1
        reg.register(_make_actor(id="a2"))
        assert reg.count() == 2

    def test_has_actor(self) -> None:
        """has_actor returns True for registered actors, False otherwise."""
        reg = ActorRegistry()
        reg.register(_make_actor(id="a1"))
        assert reg.has_actor(ActorId("a1")) is True
        assert reg.has_actor(ActorId("nonexistent")) is False

    def test_summary(self) -> None:
        """summary() returns metadata with counts by type, role, and friction."""
        reg = ActorRegistry()
        fp = FrictionProfile(category="hostile", intensity=80)
        reg.register(_make_actor(id="c1", role="customer", friction=fp))
        reg.register(_make_actor(id="c2", role="customer"))
        reg.register(_make_actor(id="a1", role="support-agent", type=ActorType.AGENT))

        s = reg.summary()
        assert s["total"] == 3
        assert s["by_role"]["customer"] == 2
        assert s["by_role"]["support-agent"] == 1
        assert s["by_type"]["human"] == 2
        assert s["by_type"]["agent"] == 1
        assert s["friction_count"] == 1
        assert s["friction_by_category"]["hostile"] == 1

    def test_query_unknown_filter_raises(self) -> None:
        """query() with unknown filter keys raises ValueError."""
        reg = ActorRegistry()
        reg.register(_make_actor(id="a1"))
        with pytest.raises(ValueError, match="Unknown query"):
            reg.query(nonexistent="foo")
