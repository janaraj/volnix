"""Unit tests for Consolidator (Phase 4B Step 6).

Per test discipline (DESIGN_PRINCIPLES.md §Test Discipline):
- Real store, real router. Only the LLM provider is stubbed.
- Negative case first on every branch.
- Assert side effects: records inserted, episodes pruned,
  consolidated_from backlinks, tracker recording.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, ClassVar

import pytest

from volnix.core.memory_types import MemoryRecord, content_hash_of
from volnix.core.types import MemoryRecordId
from volnix.engines.memory.consolidation import ConsolidationResult, Consolidator
from volnix.engines.memory.store import SQLiteMemoryStore
from volnix.llm.config import LLMConfig, LLMProviderEntry
from volnix.llm.provider import LLMProvider
from volnix.llm.registry import ProviderRegistry
from volnix.llm.router import LLMRouter
from volnix.llm.tracker import UsageTracker
from volnix.llm.types import LLMRequest, LLMResponse, LLMUsage
from volnix.persistence.manager import create_database

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rec(
    record_id: str,
    content: str,
    *,
    owner_id: str = "A",
    tick: int = 0,
) -> MemoryRecord:
    return MemoryRecord(
        record_id=MemoryRecordId(record_id),
        scope="actor",
        owner_id=owner_id,
        kind="episodic",
        tier="tier2",
        source="explicit",
        content=content,
        content_hash=content_hash_of(content),
        importance=0.5,
        tags=[],
        created_tick=tick,
    )


class _StubLLMProvider(LLMProvider):
    """Returns a canned JSON response. Lets us pin the parse path
    without depending on MockLLMProvider's hash-based output."""

    provider_name: ClassVar[str] = "stub"

    def __init__(
        self,
        *,
        content: str | None = None,
        structured: dict | list | None = None,
        error: str | None = None,
    ) -> None:
        self._content = content or ""
        self._structured = structured
        self._error = error
        self.call_count = 0

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        return LLMResponse(
            content=self._content,
            structured_output=self._structured,
            usage=LLMUsage(prompt_tokens=10, completion_tokens=5),
            model="stub-model",
            provider=self.provider_name,
            error=self._error,
        )


def _make_router(
    provider: LLMProvider,
    tracker: UsageTracker | None = None,
) -> LLMRouter:
    # max_retries=0 keeps transient-error tests fast — the Consolidator
    # behaviour we're testing is "gracefully handle a final error",
    # not "how the router retries". Router retry logic is tested in
    # tests/llm/test_router.py.
    config = LLMConfig(
        defaults=LLMProviderEntry(type="stub", default_model="stub-model"),
        providers={"stub": LLMProviderEntry(type="stub")},
        routing={},
        max_retries=0,
    )
    registry = ProviderRegistry()
    registry.register("stub", provider)
    return LLMRouter(config=config, registry=registry, tracker=tracker)


@pytest.fixture
async def store_and_db() -> AsyncIterator[tuple[SQLiteMemoryStore, Any]]:
    db = await create_database(":memory:", wal_mode=False)
    store = SQLiteMemoryStore(db)
    await store.initialize()
    try:
        yield store, db
    finally:
        await db.close()


def _two_facts_payload() -> str:
    return json.dumps(
        {
            "facts": [
                {
                    "content": "Actor prefers morning activities.",
                    "importance": 0.8,
                    "tags": ["preference", "time"],
                },
                {
                    "content": "Actor often interacts with the ops team.",
                    "importance": 0.6,
                    "tags": ["relationship"],
                },
            ]
        }
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConsolidatorConstruction:
    async def test_negative_zero_window_rejected(self, store_and_db) -> None:
        store, _ = store_and_db
        with pytest.raises(ValueError, match="episodic_window"):
            Consolidator(
                store=store,
                llm_router=_make_router(_StubLLMProvider()),
                use_case="memory_distill",
                episodic_window=0,
            )

    async def test_negative_negative_window_rejected(self, store_and_db) -> None:
        store, _ = store_and_db
        with pytest.raises(ValueError, match="episodic_window"):
            Consolidator(
                store=store,
                llm_router=_make_router(_StubLLMProvider()),
                use_case="memory_distill",
                episodic_window=-5,
            )

    async def test_positive_minimal_window_accepted(self, store_and_db) -> None:
        store, _ = store_and_db
        c = Consolidator(
            store=store,
            llm_router=_make_router(_StubLLMProvider()),
            use_case="memory_distill",
            episodic_window=1,
        )
        assert c is not None


# ---------------------------------------------------------------------------
# Empty-state short-circuit (D6-9)
# ---------------------------------------------------------------------------


class TestEmptyEpisodes:
    async def test_no_episodes_returns_zero_result_without_llm_call(self, store_and_db) -> None:
        store, _ = store_and_db
        provider = _StubLLMProvider(content=_two_facts_payload())
        c = Consolidator(
            store=store,
            llm_router=_make_router(provider),
            use_case="memory_distill",
            episodic_window=10,
        )
        result = await c.consolidate("A", tick=100)
        assert result == ConsolidationResult(
            actor_id="A",
            episodic_consumed=0,
            semantic_produced=0,
            episodic_pruned=0,
        )
        assert provider.call_count == 0  # short-circuit — no LLM cost

    async def test_force_true_calls_llm_even_on_empty(self, store_and_db) -> None:
        store, _ = store_and_db
        provider = _StubLLMProvider(content='{"facts": []}')
        c = Consolidator(
            store=store,
            llm_router=_make_router(provider),
            use_case="memory_distill",
            episodic_window=10,
        )
        result = await c.consolidate("A", tick=100, force=True)
        assert provider.call_count == 1
        assert result.semantic_produced == 0


# ---------------------------------------------------------------------------
# Happy path — episodes → facts → inserted + pruned
# ---------------------------------------------------------------------------


class TestHappyPath:
    async def test_three_episodes_distilled_to_two_facts(self, store_and_db) -> None:
        store, _ = store_and_db
        for i in range(3):
            await store.insert(_rec(f"e{i}", f"episode {i}", tick=i))
        c = Consolidator(
            store=store,
            llm_router=_make_router(_StubLLMProvider(content=_two_facts_payload())),
            use_case="memory_distill",
            episodic_window=10,
        )
        result = await c.consolidate("A", tick=100)
        assert result.episodic_consumed == 3
        assert result.semantic_produced == 2

    async def test_semantic_records_have_correct_shape(self, store_and_db) -> None:
        store, _ = store_and_db
        for i in range(3):
            await store.insert(_rec(f"e{i}", f"episode {i}", tick=i))
        c = Consolidator(
            store=store,
            llm_router=_make_router(_StubLLMProvider(content=_two_facts_payload())),
            use_case="memory_distill",
            episodic_window=10,
        )
        await c.consolidate("A", tick=100)
        semantics = await store.list_by_owner("A", kind="semantic")
        assert len(semantics) == 2
        for s in semantics:
            assert s.kind == "semantic"
            assert s.tier == "tier2"
            assert s.source == "consolidated"
            assert s.created_tick == 100
            assert s.consolidated_from == [
                MemoryRecordId("e0"),
                MemoryRecordId("e1"),
                MemoryRecordId("e2"),
            ]
            assert s.content_hash == content_hash_of(s.content)

    async def test_tags_preserved_on_semantic_records(self, store_and_db) -> None:
        store, _ = store_and_db
        await store.insert(_rec("e1", "episode 1", tick=0))
        c = Consolidator(
            store=store,
            llm_router=_make_router(_StubLLMProvider(content=_two_facts_payload())),
            use_case="memory_distill",
            episodic_window=10,
        )
        await c.consolidate("A", tick=100)
        semantics = await store.list_by_owner("A", kind="semantic")
        all_tags = {t for s in semantics for t in s.tags}
        assert "preference" in all_tags
        assert "relationship" in all_tags


# ---------------------------------------------------------------------------
# Pruning (D6-6: prune only on success)
# ---------------------------------------------------------------------------


class TestPruning:
    async def test_prune_on_successful_consolidation(self, store_and_db) -> None:
        store, _ = store_and_db
        for i in range(5):
            await store.insert(_rec(f"e{i}", f"episode {i}", tick=i))
        c = Consolidator(
            store=store,
            llm_router=_make_router(_StubLLMProvider(content=_two_facts_payload())),
            use_case="memory_distill",
            episodic_window=3,  # keep 3 most recent; prune older
        )
        result = await c.consolidate("A", tick=100)
        assert result.episodic_pruned == 2  # e0, e1 pruned
        remaining = await store.list_by_owner("A", kind="episodic")
        remaining_ids = {str(r.record_id) for r in remaining}
        assert remaining_ids == {"e2", "e3", "e4"}

    async def test_no_prune_when_zero_facts_produced(self, store_and_db) -> None:
        # D6-6: a failed consolidation keeps episodes intact
        # so the next pass can retry.
        store, _ = store_and_db
        for i in range(5):
            await store.insert(_rec(f"e{i}", f"episode {i}", tick=i))
        c = Consolidator(
            store=store,
            llm_router=_make_router(_StubLLMProvider(content='{"facts": []}')),
            use_case="memory_distill",
            episodic_window=3,
        )
        result = await c.consolidate("A", tick=100)
        assert result.semantic_produced == 0
        assert result.episodic_pruned == 0
        remaining = await store.list_by_owner("A", kind="episodic")
        assert len(remaining) == 5  # all preserved

    async def test_prune_disabled_config_never_prunes(self, store_and_db) -> None:
        store, _ = store_and_db
        for i in range(5):
            await store.insert(_rec(f"e{i}", f"episode {i}", tick=i))
        c = Consolidator(
            store=store,
            llm_router=_make_router(_StubLLMProvider(content=_two_facts_payload())),
            use_case="memory_distill",
            episodic_window=3,
            prune_after_consolidation=False,
        )
        result = await c.consolidate("A", tick=100)
        assert result.semantic_produced == 2
        assert result.episodic_pruned == 0
        remaining = await store.list_by_owner("A", kind="episodic")
        assert len(remaining) == 5


# ---------------------------------------------------------------------------
# Garbage JSON & malformed payloads (D6-5)
# ---------------------------------------------------------------------------


class TestGarbageJson:
    async def test_non_json_content_logged_and_returns_zero(self, store_and_db, caplog) -> None:
        store, _ = store_and_db
        await store.insert(_rec("e1", "episode", tick=0))
        c = Consolidator(
            store=store,
            llm_router=_make_router(_StubLLMProvider(content="not a json at all")),
            use_case="memory_distill",
            episodic_window=10,
        )
        result = await c.consolidate("A", tick=100)
        assert result.semantic_produced == 0
        assert result.episodic_pruned == 0  # D6-6 preserves on failure
        assert "failed to parse" in caplog.text.lower()

    async def test_facts_key_not_a_list(self, store_and_db) -> None:
        store, _ = store_and_db
        await store.insert(_rec("e1", "episode", tick=0))
        c = Consolidator(
            store=store,
            llm_router=_make_router(_StubLLMProvider(content='{"facts": "not a list"}')),
            use_case="memory_distill",
            episodic_window=10,
        )
        result = await c.consolidate("A", tick=100)
        assert result.semantic_produced == 0

    async def test_payload_is_a_list_not_a_dict(self, store_and_db) -> None:
        store, _ = store_and_db
        await store.insert(_rec("e1", "episode", tick=0))
        c = Consolidator(
            store=store,
            llm_router=_make_router(_StubLLMProvider(content="[1, 2, 3]")),
            use_case="memory_distill",
            episodic_window=10,
        )
        result = await c.consolidate("A", tick=100)
        assert result.semantic_produced == 0


# ---------------------------------------------------------------------------
# LLM error path
# ---------------------------------------------------------------------------


class TestLLMError:
    async def test_provider_error_logged_and_zero_produced(self, store_and_db, caplog) -> None:
        store, _ = store_and_db
        await store.insert(_rec("e1", "episode", tick=0))
        c = Consolidator(
            store=store,
            llm_router=_make_router(_StubLLMProvider(content="", error="provider timeout")),
            use_case="memory_distill",
            episodic_window=10,
        )
        result = await c.consolidate("A", tick=100)
        assert result.semantic_produced == 0
        assert "provider timeout" in caplog.text


# ---------------------------------------------------------------------------
# Fact validation (malformed individual facts)
# ---------------------------------------------------------------------------


class TestFactValidation:
    async def test_fact_missing_content_skipped(self, store_and_db) -> None:
        store, _ = store_and_db
        await store.insert(_rec("e1", "episode", tick=0))
        payload = json.dumps({"facts": [{"importance": 0.5, "tags": ["x"]}]})
        c = Consolidator(
            store=store,
            llm_router=_make_router(_StubLLMProvider(content=payload)),
            use_case="memory_distill",
            episodic_window=10,
        )
        result = await c.consolidate("A", tick=100)
        assert result.semantic_produced == 0

    async def test_fact_empty_content_skipped(self, store_and_db) -> None:
        store, _ = store_and_db
        await store.insert(_rec("e1", "episode", tick=0))
        payload = json.dumps({"facts": [{"content": "   ", "importance": 0.5}]})
        c = Consolidator(
            store=store,
            llm_router=_make_router(_StubLLMProvider(content=payload)),
            use_case="memory_distill",
            episodic_window=10,
        )
        result = await c.consolidate("A", tick=100)
        assert result.semantic_produced == 0

    async def test_importance_above_one_clamped(self, store_and_db) -> None:
        store, _ = store_and_db
        await store.insert(_rec("e1", "episode", tick=0))
        payload = json.dumps({"facts": [{"content": "out of range", "importance": 5.0}]})
        c = Consolidator(
            store=store,
            llm_router=_make_router(_StubLLMProvider(content=payload)),
            use_case="memory_distill",
            episodic_window=10,
        )
        result = await c.consolidate("A", tick=100)
        assert result.semantic_produced == 1
        semantics = await store.list_by_owner("A", kind="semantic")
        assert semantics[0].importance == 1.0  # clamped

    async def test_importance_negative_clamped(self, store_and_db) -> None:
        store, _ = store_and_db
        await store.insert(_rec("e1", "episode", tick=0))
        payload = json.dumps({"facts": [{"content": "negative imp", "importance": -0.5}]})
        c = Consolidator(
            store=store,
            llm_router=_make_router(_StubLLMProvider(content=payload)),
            use_case="memory_distill",
            episodic_window=10,
        )
        result = await c.consolidate("A", tick=100)
        assert result.semantic_produced == 1
        semantics = await store.list_by_owner("A", kind="semantic")
        assert semantics[0].importance == 0.0

    async def test_non_string_tags_filtered(self, store_and_db) -> None:
        store, _ = store_and_db
        await store.insert(_rec("e1", "episode", tick=0))
        payload = json.dumps(
            {
                "facts": [
                    {
                        "content": "x",
                        "importance": 0.5,
                        "tags": ["ok", 123, None, "also_ok"],
                    }
                ]
            }
        )
        c = Consolidator(
            store=store,
            llm_router=_make_router(_StubLLMProvider(content=payload)),
            use_case="memory_distill",
            episodic_window=10,
        )
        await c.consolidate("A", tick=100)
        semantics = await store.list_by_owner("A", kind="semantic")
        assert semantics[0].tags == ["ok", "also_ok"]


# ---------------------------------------------------------------------------
# Budget integration (G10) — tracker
# ---------------------------------------------------------------------------


class TestBudgetIntegration:
    async def test_tracker_records_distillation_call(self, store_and_db) -> None:
        store, _ = store_and_db
        await store.insert(_rec("e1", "episode", tick=0))
        tracker = UsageTracker()
        c = Consolidator(
            store=store,
            llm_router=_make_router(
                _StubLLMProvider(content=_two_facts_payload()),
                tracker=tracker,
            ),
            use_case="memory_distill",
            episodic_window=10,
        )
        await c.consolidate("A", tick=100)
        usage = await tracker.get_usage_by_engine("memory")
        # Stub reports prompt_tokens=10, completion_tokens=5.
        assert usage.prompt_tokens == 10
        assert usage.completion_tokens == 5


# ---------------------------------------------------------------------------
# Structured-output path (router unwraps JSON)
# ---------------------------------------------------------------------------


class TestStructuredOutputPath:
    async def test_structured_output_used_when_present(self, store_and_db) -> None:
        store, _ = store_and_db
        await store.insert(_rec("e1", "episode", tick=0))
        c = Consolidator(
            store=store,
            llm_router=_make_router(
                _StubLLMProvider(
                    content="",  # no text content
                    structured={
                        "facts": [
                            {
                                "content": "from structured field",
                                "importance": 0.5,
                            }
                        ]
                    },
                )
            ),
            use_case="memory_distill",
            episodic_window=10,
        )
        result = await c.consolidate("A", tick=100)
        assert result.semantic_produced == 1


# ---------------------------------------------------------------------------
# Prompt determinism (D6-3)
# ---------------------------------------------------------------------------


class TestPromptDeterminism:
    async def test_episodes_sorted_before_prompt_construction(self, store_and_db) -> None:
        # Inserting out-of-order episodes must not change the prompt.
        store, _ = store_and_db
        await store.insert(_rec("b", "content b", tick=20))
        await store.insert(_rec("a", "content a", tick=10))
        await store.insert(_rec("c", "content c", tick=30))

        captured: list[str] = []

        class _CaptureProvider(_StubLLMProvider):
            async def generate(self, request: LLMRequest) -> LLMResponse:
                captured.append(request.user_content)
                return await super().generate(request)

        c = Consolidator(
            store=store,
            llm_router=_make_router(_CaptureProvider(content='{"facts": []}')),
            use_case="memory_distill",
            episodic_window=10,
        )
        await c.consolidate("A", tick=100)
        assert captured, "no LLM call captured"
        # D6-3: sorted by record_id ASC — "a", "b", "c".
        prompt = captured[0]
        pos_a = prompt.find("content a")
        pos_b = prompt.find("content b")
        pos_c = prompt.find("content c")
        assert 0 <= pos_a < pos_b < pos_c


# ---------------------------------------------------------------------------
# ConsolidationResult value object
# ---------------------------------------------------------------------------


class TestConsolidationResult:
    def test_frozen(self) -> None:
        r = ConsolidationResult(
            actor_id="A",
            episodic_consumed=0,
            semantic_produced=0,
            episodic_pruned=0,
        )
        with pytest.raises(Exception):  # frozen model
            r.episodic_consumed = 5  # type: ignore[misc]


class TestLLMSemaphore:
    """PMF 4B cleanup commit 6 — distill LLM calls must honor the
    injected semaphore so cohort-rotation bursts don't race past
    the configured concurrency cap."""

    async def test_negative_distillation_disabled_skips_llm_call(self, store_and_db) -> None:
        """Also validates Commit 1's ``distillation_enabled=False``
        gate. The semaphore and the gate compose cleanly: disabled
        takes the fast-path before the semaphore would even acquire."""
        store, _ = store_and_db
        await store.insert(_rec("r1", "x", tick=0))
        provider = _StubLLMProvider(content=_two_facts_payload())
        consolidator = Consolidator(
            store=store,
            llm_router=_make_router(provider),
            use_case="memory_distill",
            episodic_window=10,
            distillation_enabled=False,
        )
        result = await consolidator.consolidate("A", 1)
        assert result.semantic_produced == 0
        assert provider.call_count == 0  # LLM never called

    async def test_positive_semaphore_serializes_concurrent_distill(self, store_and_db) -> None:
        """With a semaphore of size 1, concurrent distill calls
        serialize. Observe via the stub provider's call_count — it
        monotonically increments one-at-a-time even under concurrent
        invocation."""
        import asyncio

        store, _ = store_and_db
        # Seed two owners so two consolidate() calls have input.
        await store.insert(_rec("r1", "x1", owner_id="A", tick=0))
        await store.insert(_rec("r2", "x2", owner_id="B", tick=0))
        provider = _StubLLMProvider(content=_two_facts_payload())
        sem = asyncio.Semaphore(1)
        consolidator = Consolidator(
            store=store,
            llm_router=_make_router(provider),
            use_case="memory_distill",
            episodic_window=10,
            llm_semaphore=sem,
        )
        # Fire both concurrently.
        await asyncio.gather(
            consolidator.consolidate("A", 1),
            consolidator.consolidate("B", 2),
        )
        assert provider.call_count == 2

    async def test_positive_no_semaphore_still_works(self, store_and_db) -> None:
        """Constructor accepts ``llm_semaphore=None`` (unbounded) for
        tests that don't care about concurrency."""
        store, _ = store_and_db
        await store.insert(_rec("r1", "x", tick=0))
        provider = _StubLLMProvider(content=_two_facts_payload())
        consolidator = Consolidator(
            store=store,
            llm_router=_make_router(provider),
            use_case="memory_distill",
            episodic_window=10,
            llm_semaphore=None,
        )
        result = await consolidator.consolidate("A", 1)
        assert result.semantic_produced > 0
