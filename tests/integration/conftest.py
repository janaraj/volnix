"""Shared fixtures for integration tests.

Bootstraps a full TerrariumApp with temporary databases so that E2E
tests exercise the real pipeline, real packs, real state engine, and
real bus/ledger -- no mocks except the LLM router (which requires a
real API key unavailable in the test environment).
"""
from __future__ import annotations

import json
import os

import pytest
from unittest.mock import AsyncMock

from terrarium.config.schema import TerrariumConfig
from terrarium.llm.types import LLMResponse
from terrarium.persistence.config import PersistenceConfig
from terrarium.engines.state.config import StateConfig


# ── Mock LLM helpers ─────────────────────────────────────────────


def _mock_llm_route_side_effect():
    """Return a side_effect callable for a mock LLM router.

    Inspects the (request, engine_name, use_case) arguments to return
    the right JSON payload for each compiler stage:

    - data_generator / default        -> entity generation
    - world_compiler / personality_generation -> personality JSON
    - world_compiler / seed_expansion  -> seed modification JSON
    """
    # Counters for unique IDs across calls
    _entity_counter = {"email": 0, "mailbox": 0, "thread": 0}

    # Reusable seed expansion payload (includes invariants required by
    # the validate-repair-retry pipeline).
    _seed_expansion_payload = {
        "entities_to_create": [],
        "entities_to_modify": [],
        "invariants": [
            {
                "kind": "count",
                "selector": {"entity_type": "email", "match": {}},
                "operator": "gte",
                "value": 1,
            }
        ],
    }

    async def _route(request, engine_name="", use_case="default"):
        # --- Entity generation ---
        if engine_name == "data_generator":
            user = request.user_content.lower()

            if "email" in user and "mailbox" not in user and "thread" not in user:
                count = _parse_count(user, 10)
                entities = []
                for i in range(count):
                    _entity_counter["email"] += 1
                    idx = _entity_counter["email"]
                    entities.append({
                        "id": f"e_{idx:03d}",
                        "email_id": f"e_{idx:03d}",
                        "from_addr": f"sender{idx}@acme.com",
                        "to_addr": f"recipient{idx}@test.com",
                        "subject": f"Support ticket #{idx}",
                        "body": f"Body of email {idx}. Please review your request.",
                        "status": ["draft", "sent", "delivered", "read"][idx % 4],
                        "thread_id": f"t_{(idx % 3) + 1:03d}",
                        "timestamp": f"2026-03-{10 + idx:02d}T09:00:00Z",
                    })
                return LLMResponse(
                    content=json.dumps(entities),
                    provider="mock", model="mock", latency_ms=0,
                )

            if "mailbox" in user:
                count = _parse_count(user, 5)
                entities = []
                for i in range(count):
                    _entity_counter["mailbox"] += 1
                    idx = _entity_counter["mailbox"]
                    entities.append({
                        "id": f"mb_{idx:03d}",
                        "mailbox_id": f"mb_{idx:03d}",
                        "owner": f"user{idx}@acme.com",
                        "display_name": f"User {idx}",
                        "unread_count": idx * 2,
                    })
                return LLMResponse(
                    content=json.dumps(entities),
                    provider="mock", model="mock", latency_ms=0,
                )

            if "thread" in user:
                count = _parse_count(user, 3)
                entities = []
                for i in range(count):
                    _entity_counter["thread"] += 1
                    idx = _entity_counter["thread"]
                    entities.append({
                        "id": f"t_{idx:03d}",
                        "thread_id": f"t_{idx:03d}",
                        "subject": f"Thread subject {idx}",
                        "participants": [f"user{idx}@acme.com", "support@acme.com"],
                        "message_count": idx + 1,
                    })
                return LLMResponse(
                    content=json.dumps(entities),
                    provider="mock", model="mock", latency_ms=0,
                )

            # Fallback for unknown entity types -- return minimal valid list
            return LLMResponse(
                content=json.dumps([{"id": "unknown_001", "status": "draft"}]),
                provider="mock", model="mock", latency_ms=0,
            )

        # --- Personality generation ---
        if use_case == "personality_generation":
            return LLMResponse(
                content=json.dumps({
                    "style": "balanced",
                    "response_time": "5m",
                    "strengths": ["organized", "detail-oriented"],
                    "weaknesses": ["cautious", "slow-to-act"],
                    "description": "A balanced professional who is thorough and methodical.",
                    "traits": {},
                }),
                provider="mock", model="mock", latency_ms=0,
            )

        # --- Seed expansion ---
        # The SEED_EXPANSION template routes with engine_name="world_compiler"
        # and use_case="default", so detect by prompt content as well.
        if use_case == "seed_expansion" or (
            engine_name == "world_compiler"
            and "seed scenario" in (request.user_content or "").lower()
        ):
            return LLMResponse(
                content=json.dumps(_seed_expansion_payload),
                provider="mock", model="mock", latency_ms=0,
            )

        # --- Section repair ---
        # The SECTION_REPAIR template routes with use_case="section_repair".
        # Return the seed expansion payload for seed repairs; for other
        # section kinds just echo back a minimal valid array.
        if use_case == "section_repair":
            user = (request.user_content or "").lower()
            if "seed" in user:
                return LLMResponse(
                    content=json.dumps(_seed_expansion_payload),
                    provider="mock", model="mock", latency_ms=0,
                )
            # Entity/actor repair — return empty array (parsed by caller)
            return LLMResponse(
                content=json.dumps([]),
                provider="mock", model="mock", latency_ms=0,
            )

        # --- Catch-all (e.g. NL parsing) ---
        return LLMResponse(
            content="{}",
            provider="mock", model="mock", latency_ms=0,
        )

    return _route


def _parse_count(text: str, default: int) -> int:
    """Extract the requested entity count from LLM request text."""
    import re
    m = re.search(r"generate\s+(\d+)", text)
    if m:
        return int(m.group(1))
    return default


def inject_mock_llm(app) -> AsyncMock:
    """Inject a mock LLM router into the app's world compiler engine.

    Call AFTER app.start() so the compiler engine is initialized.
    Returns the mock router for test assertions.
    """
    compiler = app.registry.get("world_compiler")
    mock_router = AsyncMock()
    mock_router.route = AsyncMock(side_effect=_mock_llm_route_side_effect())
    compiler._llm_router = mock_router
    compiler._config["_llm_router"] = mock_router
    return mock_router


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
async def app(tmp_path):
    """Fully bootstrapped TerrariumApp with tmp databases.

    Overrides persistence base_dir and state db_path so every test run
    uses isolated temporary storage.  Yields the running app and shuts
    it down on teardown.
    """
    from terrarium.app import TerrariumApp

    config = TerrariumConfig()
    # TerrariumConfig is frozen -- use model_copy to override fields
    config = config.model_copy(update={
        "persistence": PersistenceConfig(base_dir=str(tmp_path / "data")),
        "state": StateConfig(
            db_path=str(tmp_path / "state.db"),
            snapshot_dir=str(tmp_path / "snapshots"),
        ),
    })

    app = TerrariumApp(config)
    await app.start()
    yield app
    await app.stop()


@pytest.fixture
async def app_with_mock_llm(tmp_path):
    """TerrariumApp with a mock LLM router injected into the compiler.

    Use this fixture for tests that call generate_world() but do not
    have a real GOOGLE_API_KEY in the environment.
    """
    from terrarium.app import TerrariumApp

    config = TerrariumConfig()
    config = config.model_copy(update={
        "persistence": PersistenceConfig(base_dir=str(tmp_path / "data")),
        "state": StateConfig(
            db_path=str(tmp_path / "state.db"),
            snapshot_dir=str(tmp_path / "snapshots"),
        ),
    })

    app = TerrariumApp(config)
    await app.start()
    inject_mock_llm(app)
    yield app
    await app.stop()


@pytest.fixture
async def live_app(tmp_path):
    """TerrariumApp with a REAL LLM router — requires GOOGLE_API_KEY.

    Skips the test if no API key is available.  Use for integration
    tests that exercise the actual LLM pipeline.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        pytest.skip("GOOGLE_API_KEY not set — skipping live LLM test")

    from terrarium.app import TerrariumApp

    config = TerrariumConfig()
    config = config.model_copy(update={
        "persistence": PersistenceConfig(base_dir=str(tmp_path / "data")),
        "state": StateConfig(
            db_path=str(tmp_path / "state.db"),
            snapshot_dir=str(tmp_path / "snapshots"),
        ),
    })

    app = TerrariumApp(config)
    await app.start()
    yield app
    await app.stop()


# ── Helpers ──────────────────────────────────────────────────────────

def email_send_payload(
    from_addr: str = "alice@test.com",
    to_addr: str = "bob@test.com",
    subject: str = "Hello",
    body: str = "World",
) -> dict:
    """Convenience builder for email_send input_data."""
    return {
        "from_addr": from_addr,
        "to_addr": to_addr,
        "subject": subject,
        "body": body,
    }
