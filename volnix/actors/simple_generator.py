"""Heuristic actor generator -- no LLM required.

:class:`SimpleActorGenerator` satisfies the :class:`ActorPersonalityGenerator`
protocol using seeded RNG and configurable vocabulary from :class:`ActorConfig`.
"""

from __future__ import annotations

import random
from typing import Any

from volnix.actors.config import ActorConfig
from volnix.actors.definition import ActorDefinition
from volnix.actors.personality import FrictionProfile, Personality
from volnix.core.types import ActorId, ActorType
from volnix.reality.dimensions import SocialFrictionDimension, WorldConditions


class SimpleActorGenerator:
    """Heuristic personality generation.  Satisfies ActorPersonalityGenerator protocol."""

    def __init__(self, seed: int = 42, config: ActorConfig | None = None) -> None:
        self._rng = random.Random(seed)
        self._config = config or ActorConfig()

    # -- Protocol methods ----------------------------------------------------

    async def generate_personality(
        self,
        role: str,
        personality_hint: str,
        conditions: WorldConditions,
        domain_context: str = "",
    ) -> Personality:
        """Generate a personality using weighted random style selection."""
        # domain_context is unused in heuristic generator.
        # The D4 LLM generator will use it as prompt context.
        style = self._pick_style(conditions)
        return Personality(
            style=style,
            response_time=self._config.default_human_response_time,
            description=personality_hint or f"{style} {role}",
        )

    async def generate_friction_profile(
        self,
        category: str,
        intensity: int,
        sophistication: str,
        domain_context: str = "",
    ) -> FrictionProfile:
        """Generate a friction profile with behaviors from config vocabulary."""
        # domain_context is unused in heuristic generator.
        # The D4 LLM generator will use it as prompt context.
        behaviors = self._generate_behaviors(category, sophistication)
        return FrictionProfile(
            category=category,
            intensity=intensity,
            behaviors=behaviors,
            sophistication=sophistication,  # type: ignore[arg-type]
        )

    async def generate_batch(
        self,
        actor_specs: list[dict[str, Any]],
        conditions: WorldConditions,
        domain_context: str = "",
    ) -> list[ActorDefinition]:
        """Expand specs into full actor definitions with personalities and friction.

        1. Expand count (spec with count=50 -> 50 actors)
        2. Generate personality for each from hint + conditions
        3. Distribute friction profiles based on conditions.friction
        4. Assign unique ActorIds
        """
        actors: list[ActorDefinition] = []
        friction = conditions.friction

        for spec in actor_specs:
            _TYPE_MAP = {"external": "agent", "internal": "human"}
            role = spec["role"]
            raw_type = spec.get("type", "human")
            actor_type = ActorType(_TYPE_MAP.get(raw_type, raw_type))
            count = spec.get("count", 1)
            hint = spec.get("personality", "")
            permissions = spec.get("permissions", {})
            budget = spec.get("budget")
            team = spec.get("team")
            # Phase 4C Step 11 post-ship cleanup (audit C1): thread
            # ``activation_profile`` through so CharacterDefinition
            # consumers can opt a catalog character into the NPC
            # activation path. Also consume ``id`` / ``name`` as
            # known keys — they're catalog-scope metadata, not
            # actor identity (the generator mints its own actor_id
            # with count expansion), and shouldn't land in the
            # metadata bag as junk.
            activation_profile = spec.get("activation_profile")

            # Anything not in known keys goes to metadata; an
            # explicit ``metadata`` sub-dict on the spec is merged
            # in (Step-11 cleanup audit C1: prevents the nested
            # ``{"metadata": {"metadata": {...}}}`` shape that
            # CharacterDefinition.to_actor_spec() would otherwise
            # produce).
            known_keys = {
                "role",
                "type",
                "count",
                "personality",
                "permissions",
                "budget",
                "team",
                "visibility",
                "activation_profile",
                "id",
                "name",
                "metadata",
            }
            metadata = {k: v for k, v in spec.items() if k not in known_keys}
            explicit_meta = spec.get("metadata")
            if isinstance(explicit_meta, dict):
                metadata = {**metadata, **explicit_meta}

            # Determine friction distribution for non-agent actors
            if actor_type != ActorType.AGENT:
                friction_assignments = self._distribute_friction(count, friction)
            else:
                friction_assignments = []

            friction_idx = 0
            for _i in range(count):
                actor_id = ActorId(f"{role}-{format(self._rng.getrandbits(32), '08x')}")

                personality = await self.generate_personality(
                    role, hint, conditions, domain_context
                )

                friction_profile = None
                if friction_idx < len(friction_assignments):
                    cat, intensity = friction_assignments[friction_idx]
                    friction_profile = await self.generate_friction_profile(
                        cat, intensity, friction.sophistication, domain_context
                    )
                    friction_idx += 1

                actors.append(
                    ActorDefinition(
                        id=actor_id,
                        type=actor_type,
                        role=role,
                        team=team,
                        permissions=permissions,
                        budget=budget,
                        visibility=spec.get("visibility"),
                        personality=personality,
                        friction_profile=friction_profile,
                        metadata=metadata,
                        personality_hint=hint,
                        # Phase 4C Step 11 cleanup (audit C1): thread
                        # activation_profile from catalog spec through
                        # to ActorDefinition so a CharacterDefinition
                        # with ``activation_profile="consumer_user"``
                        # actually becomes an active NPC rather than
                        # a passive metadata entry.
                        activation_profile=activation_profile,
                    )
                )

        return actors

    # -- Private helpers -----------------------------------------------------

    def _distribute_friction(
        self, total: int, friction_dim: SocialFrictionDimension
    ) -> list[tuple[str, int]]:
        """Distribute friction profiles across actors.

        Friction categories are CUMULATIVE: hostile actors are a subset of
        deceptive actors, which are a subset of uncooperative actors.
        Example: hostile=8, deceptive=15, uncooperative=30 means:
          - 8% hostile (also deceptive and uncooperative)
          - 7% deceptive-only (also uncooperative)
          - 15% uncooperative-only
          - 70% cooperative (no friction)

        Returns ``(category, intensity)`` tuples for actors that get friction.
        Uses friction dimension intensity values as approximate percentages.
        Seeded RNG ensures reproducibility.
        """
        assignments: list[tuple[str, int]] = []

        hostile_n = round(total * friction_dim.hostile / 100)
        deceptive_n = round(total * friction_dim.deceptive / 100)
        uncoop_n = round(total * friction_dim.uncooperative / 100)

        # Avoid double-counting
        deceptive_n = max(0, deceptive_n - hostile_n)
        uncoop_n = max(0, uncoop_n - hostile_n - deceptive_n)

        for _ in range(hostile_n):
            assignments.append(("hostile", self._rng.randint(60, 100)))
        for _ in range(deceptive_n):
            assignments.append(("deceptive", self._rng.randint(30, 70)))
        for _ in range(uncoop_n):
            assignments.append(("uncooperative", self._rng.randint(15, 50)))

        self._rng.shuffle(assignments)
        return assignments[:total]

    def _pick_style(self, conditions: WorldConditions) -> str:
        """Weighted random style from config.style_weights."""
        styles = list(self._config.style_weights.keys())
        weights = list(self._config.style_weights.values())
        return self._rng.choices(styles, weights=weights, k=1)[0]

    def _generate_behaviors(self, category: str, sophistication: str) -> list[str]:
        """Pick N behaviors from config.friction_behaviors[category]."""
        vocab = self._config.friction_behaviors.get(category, [])
        if not vocab:
            return []
        # Higher sophistication -> more behaviors
        n = {"low": 1, "medium": 2, "high": 3}.get(sophistication, 2)
        n = min(n, len(vocab))
        return self._rng.sample(vocab, n)
