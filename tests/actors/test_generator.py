"""Tests for volnix.actors.simple_generator -- SimpleActorGenerator."""

from volnix.actors.definition import ActorDefinition
from volnix.actors.generator import ActorPersonalityGenerator
from volnix.actors.personality import FrictionProfile, Personality
from volnix.actors.simple_generator import SimpleActorGenerator
from volnix.reality.presets import load_preset


class TestSimpleActorGenerator:
    """Verify SimpleActorGenerator satisfies protocol and produces correct output."""

    def test_protocol_check(self) -> None:
        """SimpleActorGenerator satisfies the ActorPersonalityGenerator protocol."""
        gen = SimpleActorGenerator()
        assert isinstance(gen, ActorPersonalityGenerator)

    async def test_generate_personality(self) -> None:
        """generate_personality returns a valid Personality with a style."""
        gen = SimpleActorGenerator(seed=42)
        conditions = load_preset("messy")
        personality = await gen.generate_personality(
            role="customer",
            personality_hint="Frustrated user",
            conditions=conditions,
        )
        assert isinstance(personality, Personality)
        assert isinstance(personality.style, str)
        assert len(personality.style) > 0

    async def test_generate_personality_deterministic(self) -> None:
        """Same seed produces the same personality."""
        conditions = load_preset("messy")

        gen1 = SimpleActorGenerator(seed=99)
        p1 = await gen1.generate_personality("customer", "hint", conditions)

        gen2 = SimpleActorGenerator(seed=99)
        p2 = await gen2.generate_personality("customer", "hint", conditions)

        assert p1.style == p2.style
        assert p1.response_time == p2.response_time

    async def test_generate_friction_profile(self) -> None:
        """generate_friction_profile returns a valid FrictionProfile with behaviors."""
        gen = SimpleActorGenerator(seed=42)
        fp = await gen.generate_friction_profile(
            category="hostile",
            intensity=80,
            sophistication="high",
        )
        assert isinstance(fp, FrictionProfile)
        assert fp.category == "hostile"
        assert fp.intensity == 80
        assert isinstance(fp.behaviors, list)

    async def test_generate_batch_count_expansion(self) -> None:
        """A spec with count=50 produces exactly 50 ActorDefinition instances."""
        gen = SimpleActorGenerator(seed=42)
        conditions = load_preset("messy")
        actors = await gen.generate_batch(
            [{"role": "customer", "count": 50, "type": "human"}],
            conditions,
        )
        assert len(actors) == 50
        assert all(isinstance(a, ActorDefinition) for a in actors)
        assert all(a.role == "customer" for a in actors)

    async def test_generate_batch_friction_distribution(self) -> None:
        """Messy preset (~30% uncooperative) produces some actors with friction profiles."""
        gen = SimpleActorGenerator(seed=42)
        conditions = load_preset("messy")
        # messy friction: uncooperative=30, deceptive=15, hostile=8
        actors = await gen.generate_batch(
            [{"role": "customer", "count": 100, "type": "human"}],
            conditions,
        )
        with_friction = [a for a in actors if a.friction_profile is not None]
        # With 30% uncooperative, 15% deceptive, 8% hostile (after dedup adjustment),
        # we expect a significant portion to have friction profiles.
        # Exact count depends on the distribution algorithm, but should be > 0 and < 100.
        assert len(with_friction) > 0
        assert len(with_friction) < 100

    async def test_generate_batch_cooperative_world(self) -> None:
        """Ideal preset (everyone_helpful) produces zero friction profiles."""
        gen = SimpleActorGenerator(seed=42)
        conditions = load_preset("ideal")
        # ideal friction: uncooperative=0, deceptive=0, hostile=0
        actors = await gen.generate_batch(
            [{"role": "customer", "count": 20, "type": "human"}],
            conditions,
        )
        with_friction = [a for a in actors if a.friction_profile is not None]
        assert len(with_friction) == 0

    async def test_generate_batch_hostile_world(self) -> None:
        """Hostile preset (many_difficult_people) produces many friction profiles."""
        gen = SimpleActorGenerator(seed=42)
        conditions = load_preset("hostile")
        # hostile friction: uncooperative=55, deceptive=30, hostile=20
        actors = await gen.generate_batch(
            [{"role": "customer", "count": 50, "type": "human"}],
            conditions,
        )
        with_friction = [a for a in actors if a.friction_profile is not None]
        # With 55% uncooperative, 30% deceptive, 20% hostile, a large fraction
        # should have friction. Expect at least 10 (20% hostile alone = 10).
        assert len(with_friction) >= 10

    async def test_generate_batch_unique_ids(self) -> None:
        """All generated actors have unique IDs."""
        gen = SimpleActorGenerator(seed=42)
        conditions = load_preset("messy")
        actors = await gen.generate_batch(
            [{"role": "customer", "count": 50, "type": "human"}],
            conditions,
        )
        ids = [a.id for a in actors]
        assert len(ids) == len(set(ids))

    async def test_generate_batch_preserves_metadata(self) -> None:
        """Extra keys in actor spec (not in known keys) are preserved in metadata."""
        gen = SimpleActorGenerator(seed=42)
        conditions = load_preset("messy")
        actors = await gen.generate_batch(
            [
                {
                    "role": "customer",
                    "count": 3,
                    "type": "human",
                    "language": "en",
                    "priority": "vip",
                }
            ],
            conditions,
        )
        assert len(actors) == 3
        for actor in actors:
            assert actor.metadata.get("language") == "en"
            assert actor.metadata.get("priority") == "vip"
