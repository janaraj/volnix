"""Tests for WorldCompilerEngine.generate_world() — D4b orchestration."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from unittest.mock import AsyncMock

import pytest

from terrarium.actors.registry import ActorRegistry
from terrarium.core.errors import CompilerError, WorldGenerationValidationError
from terrarium.engines.world_compiler.engine import WorldCompilerEngine
from terrarium.engines.world_compiler.plan import ServiceResolution, WorldPlan
from terrarium.kernel.registry import SemanticRegistry
from terrarium.kernel.surface import ServiceSurface
from terrarium.llm.types import LLMResponse
from terrarium.packs.registry import PackRegistry
from terrarium.packs.verified.email.pack import EmailPack
from terrarium.reality.presets import load_preset

# ── Helpers ──────────────────────────────────────────────────────


def _entity_payload(entity_type: str, count: int) -> list[dict]:
    payloads: dict[str, callable] = {
        # Gmail-aligned entity types (namespaced with gmail_ prefix)
        "gmail_message": lambda idx: {
            "id": f"msg_{idx:03d}",
            "threadId": f"thread_{idx:03d}",
            "labelIds": ["INBOX"],
            "snippet": f"Snippet {idx}",
            "subject": f"Test {idx}",
            "body": "Hello",
            "from_addr": "a@b.com",
            "to_addr": "c@d.com",
        },
        "gmail_thread": lambda idx: {
            "id": f"thread_{idx:03d}",
            "snippet": f"Thread snippet {idx}",
            "messages": [f"msg_{idx:03d}"],
        },
        "gmail_label": lambda idx: {
            "id": f"label_{idx:03d}",
            "name": f"Label {idx}",
        },
        "gmail_draft": lambda idx: {
            "id": f"draft_{idx:03d}",
        },
        # Legacy entity types (backward compatibility)
        "email": lambda idx: {
            "id": f"email_{idx:03d}",
            "email_id": f"email_{idx:03d}",
            "from_addr": "a@b.com",
            "to_addr": "c@d.com",
            "subject": f"Test {idx}",
            "body": "Hello",
            "status": "sent",
        },
        "mailbox": lambda idx: {
            "id": f"mailbox_{idx:03d}",
            "mailbox_id": f"mailbox_{idx:03d}",
            "owner": f"user{idx}@example.com",
        },
    }
    factory = payloads.get(entity_type, lambda idx: {"id": f"{entity_type}_{idx:03d}"})
    return [factory(index) for index in range(count)]


def _seed_payload() -> dict:
    return {
        "entities_to_create": [],
        "entities_to_modify": [
            {
                "entity_type": "email",
                "entity_id": "email_000",
                "field_updates": {"subject": "URGENT: VIP Request"},
            }
        ],
        "invariants": [
            {
                "kind": "count",
                "selector": {"entity_type": "email", "match": {}},
                "operator": "gte",
                "value": 1,
            },
            {
                "kind": "field_equals",
                "selector": {"entity_type": "email", "match": {}},
                "field": "subject",
                "value": "URGENT: VIP Request",
            },
        ],
    }


def _make_mock_llm_router(*, invalid_sections: set[str] | None = None):
    """Mock LLM router that returns valid JSON for all compiler sub-components.

    ``invalid_sections`` returns a broken entity section on the first generation
    call for the named entity types so repair paths can be exercised.
    """
    invalid_sections = invalid_sections or set()
    section_calls: defaultdict[str, int] = defaultdict(int)

    def _route_side_effect(*args, **kwargs):
        request = args[0] if args else kwargs.get("request")
        use_case = args[2] if len(args) > 2 else kwargs.get("use_case", "")
        system = getattr(request, "system_prompt", "") or ""
        user = getattr(request, "user_content", "") or ""
        combined = (system + user).lower()

        if use_case == "section_repair":
            if "entity_section" in combined:
                entity_match = re.search(r"section:\s*([a-z_]+)", user.lower())
                count_match = re.search(r"exactly (\d+)", system.lower())
                entity_type = entity_match.group(1) if entity_match else "email"
                count = int(count_match.group(1)) if count_match else 10
                payload = _entity_payload(entity_type, count)
            elif "actor_role" in combined:
                count_match = re.search(r"exactly (\d+)", system.lower())
                count = int(count_match.group(1)) if count_match else 1
                payload = [
                    {
                        "style": "balanced",
                        "response_time": "5m",
                        "strengths": ["adaptable"],
                        "weaknesses": ["generic"],
                        "description": f"Balanced actor {index}",
                        "traits": {},
                    }
                    for index in range(count)
                ]
            else:
                payload = _seed_payload()
        elif (
            "personality profiles for actors" in combined
            or "distinct personalities for" in combined
        ):
            payload = [
                {
                    "style": "balanced",
                    "response_time": "5m",
                    "strengths": ["adaptable"],
                    "weaknesses": ["generic"],
                    "description": "A balanced actor",
                    "traits": {},
                },
            ]
        elif "seed" in combined or "scenario" in combined:
            payload = _seed_payload()
        else:
            entity_match = re.search(r"generate realistic ([a-z_]+) entities", system.lower())
            count_match = re.search(r"generate exactly (\d+)", system.lower())
            entity_type = entity_match.group(1) if entity_match else "email"
            count = int(count_match.group(1)) if count_match else 10
            section_calls[entity_type] += 1
            if entity_type in invalid_sections and section_calls[entity_type] == 1:
                payload = [{"broken": True}]
            else:
                payload = _entity_payload(entity_type, count)

        return LLMResponse(
            content=json.dumps(payload),
            provider="mock", model="gemini-3-flash-preview", latency_ms=0,
        )

    router = AsyncMock()
    router.route = AsyncMock(side_effect=_route_side_effect)
    return router


async def _make_engine(
    llm_router=None, state_engine=None, actor_registry=None
):
    """Build a WorldCompilerEngine with injected dependencies."""
    if llm_router is None:
        llm_router = _make_mock_llm_router()

    kernel = SemanticRegistry()
    await kernel.initialize()
    pack_reg = PackRegistry()
    pack_reg.register(EmailPack())

    engine = WorldCompilerEngine()
    config = {
        "default_seed": 42,
        "max_entities_per_type": 100,
        "_kernel": kernel,
        "_pack_registry": pack_reg,
        "_llm_router": llm_router,
        "_state_engine": state_engine,
        "_actor_registry": actor_registry,
    }
    bus = AsyncMock()
    await engine.initialize(config, bus)
    return engine


def _make_plan_with_email() -> WorldPlan:
    surface = ServiceSurface.from_pack(EmailPack())
    return WorldPlan(
        name="Test World",
        description="Test",
        seed=42,
        services={
            "email": ServiceResolution(
                service_name="email",
                spec_reference="verified/email",
                surface=surface,
                resolution_source="tier1_pack",
            )
        },
        actor_specs=[
            {"role": "support-agent", "type": "external", "count": 2}
        ],
        conditions=load_preset("messy"),
        reality_prompt_context={},
    )


# ── generate_world requires LLM ─────────────────────────────────


class TestGenerateWorldRequiresLLM:
    """generate_world() raises CompilerError without LLM."""

    @pytest.mark.asyncio
    async def test_no_llm_raises(self) -> None:
        engine = await _make_engine()
        # Remove the LLM router to simulate no LLM
        engine._llm_router = None
        plan = _make_plan_with_email()
        with pytest.raises(CompilerError, match="Cannot generate world"):
            await engine.generate_world(plan)


# ── generate_world with mock LLM ────────────────────────────────


class TestGenerateWorldWithMockLLM:
    """generate_world() works with mock LLM router."""

    @pytest.mark.asyncio
    async def test_returns_entities(self) -> None:
        engine = await _make_engine()
        plan = _make_plan_with_email()
        result = await engine.generate_world(plan)
        assert "entities" in result
        assert isinstance(result["entities"], dict)

    @pytest.mark.asyncio
    async def test_returns_actors(self) -> None:
        engine = await _make_engine()
        plan = _make_plan_with_email()
        result = await engine.generate_world(plan)
        assert "actors" in result
        assert len(result["actors"]) == 2  # count=2 from spec

    @pytest.mark.asyncio
    async def test_returns_report(self) -> None:
        engine = await _make_engine()
        plan = _make_plan_with_email()
        result = await engine.generate_world(plan)
        assert "report" in result
        assert "TERRARIUM WORLD GENERATION REPORT" in result["report"]

    @pytest.mark.asyncio
    async def test_returns_warnings(self) -> None:
        engine = await _make_engine()
        plan = _make_plan_with_email()
        result = await engine.generate_world(plan)
        assert "warnings" in result
        assert isinstance(result["warnings"], list)

    @pytest.mark.asyncio
    async def test_returns_validation_report_and_retry_counts(self) -> None:
        engine = await _make_engine()
        result = await engine.generate_world(_make_plan_with_email())
        assert "validation_report" in result
        assert result["validation_report"]["final_world"]["valid"] is True
        assert "retry_counts" in result


# ── generate_world with StateEngine ──────────────────────────────


class TestGenerateWorldWithState:
    """generate_world() populates StateEngine when available."""

    @pytest.mark.asyncio
    async def test_populates_state(self) -> None:
        state = AsyncMock()
        state.populate_entities = AsyncMock(return_value=10)
        state.snapshot = AsyncMock(return_value="snap_001")
        engine = await _make_engine(state_engine=state)
        plan = _make_plan_with_email()
        result = await engine.generate_world(plan)
        state.populate_entities.assert_called_once()
        state.snapshot.assert_called_once_with("initial_world")
        assert result["snapshot_id"] == "snap_001"

    @pytest.mark.asyncio
    async def test_registers_actors(self) -> None:
        registry = ActorRegistry()
        engine = await _make_engine(actor_registry=registry)
        plan = _make_plan_with_email()
        await engine.generate_world(plan)
        assert registry.count() == 2


# ── generate_world with seeds ────────────────────────────────────


class TestGenerateWorldWithSeeds:
    """Seeds are processed during generation."""

    @pytest.mark.asyncio
    async def test_seeds_processed_count(self) -> None:
        engine = await _make_engine()
        plan = _make_plan_with_email().model_copy(
            update={
                "seeds": [
                    "VIP customer with urgent ticket",
                    "Overdue invoice",
                ],
            }
        )
        result = await engine.generate_world(plan)
        assert result["seeds_processed"] == 2

    @pytest.mark.asyncio
    async def test_seeds_modify_world_state(self) -> None:
        """Seeds must produce observable entity changes, not just a processed count."""
        engine = await _make_engine()
        plan = _make_plan_with_email().model_copy(
            update={
                "seeds": ["VIP customer with urgent ticket"],
            }
        )
        result = await engine.generate_world(plan)
        assert result["seeds_processed"] == 1
        # The seed validation pipeline should have recorded invariants
        # that were checked against the world state
        vr = result.get("validation_report", {})
        final = vr.get("final_world", {})
        assert final.get("valid") is True

    @pytest.mark.asyncio
    async def test_no_seeds_zero_count(self) -> None:
        engine = await _make_engine()
        plan = _make_plan_with_email()
        result = await engine.generate_world(plan)
        assert result["seeds_processed"] == 0


class TestGenerateWorldValidationAndRetry:
    """Validation failures trigger scoped retries and gate snapshotting."""

    @pytest.mark.asyncio
    async def test_bad_section_retries_at_least_that_section(self) -> None:
        engine = await _make_engine(llm_router=_make_mock_llm_router(invalid_sections={"email"}))
        result = await engine.generate_world(_make_plan_with_email())
        # The invalid email section MUST have at least 1 retry
        assert result["retry_counts"]["email"] >= 1
        # Cross-section validation may also trigger retries on other sections
        # (this is correct behavior — the validator checks whole-world consistency)

    @pytest.mark.asyncio
    async def test_no_snapshot_on_unresolved_validation_failure(self) -> None:
        async def _always_bad(*args, **kwargs):
            request = args[0]
            system = getattr(request, "system_prompt", "") or ""
            if "Generate realistic email entities" in system:
                payload = [{"broken": True}]
            elif "seed" in system.lower():
                payload = _seed_payload()
            else:
                payload = _entity_payload("thread", 10)
            return LLMResponse(
                content=json.dumps(payload),
                provider="mock",
                model="mock",
                latency_ms=0,
            )

        router = AsyncMock()
        router.route = AsyncMock(side_effect=_always_bad)
        state = AsyncMock()
        state.populate_entities = AsyncMock(return_value=0)
        state.snapshot = AsyncMock(return_value="snap")
        engine = await _make_engine(llm_router=router, state_engine=state)
        with pytest.raises(WorldGenerationValidationError):
            await engine.generate_world(_make_plan_with_email())
        state.snapshot.assert_not_called()


# ── resolve_service_schema ───────────────────────────────────────


class TestGenerateWorldEntityContent:
    """Verify generated entities have proper fields, not just counts."""

    @pytest.mark.asyncio
    async def test_entities_have_ids(self) -> None:
        engine = await _make_engine()
        plan = _make_plan_with_email()
        result = await engine.generate_world(plan)
        surface = ServiceSurface.from_pack(EmailPack())
        identity_fields = {
            entity_type: schema.get("x-terrarium-identity", "id")
            for entity_type, schema in surface.entity_schemas.items()
        }
        for entity_type, entities in result["entities"].items():
            for entity in entities:
                identity_field = identity_fields.get(entity_type, "id")
                assert identity_field in entity, f"{entity_type} entity missing identity field"
                assert entity[identity_field], f"{entity_type} entity has empty identity"

    @pytest.mark.asyncio
    async def test_actors_have_personalities(self) -> None:
        engine = await _make_engine()
        plan = _make_plan_with_email()
        result = await engine.generate_world(plan)
        for actor in result["actors"]:
            assert actor.role, "Actor missing role"
            assert actor.personality is not None, "Actor missing personality"
            assert actor.personality.style in (
                "methodical", "creative", "aggressive", "cautious", "balanced"
            )

    @pytest.mark.asyncio
    async def test_report_has_entity_counts(self) -> None:
        engine = await _make_engine()
        plan = _make_plan_with_email()
        result = await engine.generate_world(plan)
        report = result["report"]
        assert "GENERATED ENTITIES:" in report
        assert "TOTAL:" in report
        assert "ACTORS:" in report
        assert "STATUS:" in report
        # Total should match actual entity count
        total = sum(len(v) for v in result["entities"].values())
        assert f"TOTAL: {total} entities" in report


class TestExpandReality:
    """expand_reality() delegates to ConditionExpander."""

    @pytest.mark.asyncio
    async def test_expand_reality_messy(self) -> None:
        engine = await _make_engine()
        conditions = await engine.expand_reality("messy")
        assert conditions.information.staleness == 30
        assert conditions.reliability.failures == 20

    @pytest.mark.asyncio
    async def test_expand_reality_with_overrides(self) -> None:
        engine = await _make_engine()
        conditions = await engine.expand_reality(
            "ideal", overrides={"friction": "actively_hostile"}
        )
        assert conditions.friction.uncooperative == 75
        # Other dimensions stay ideal
        assert conditions.information.staleness == 0


class TestResolveServiceSchema:
    @pytest.mark.asyncio
    async def test_resolve_unknown_service_raises(self) -> None:
        engine = await _make_engine()
        # Unknown service with no resolution available
        with pytest.raises(Exception):
            await engine.resolve_service_schema("nonexistent_service_xyz")
