"""Shared fixtures for integration tests.

Bootstraps a full VolnixApp with temporary databases so that E2E
tests exercise the real pipeline, real packs, real state engine, and
real bus/ledger -- no mocks except the LLM router (which requires a
real API key unavailable in the test environment).
"""
from __future__ import annotations

import json
import os

import pytest
from unittest.mock import AsyncMock

from volnix.config.schema import VolnixConfig
from volnix.llm.types import LLMResponse
from volnix.persistence.config import PersistenceConfig
from volnix.engines.state.config import StateConfig


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
    _entity_counter = {
        "email": 0, "mailbox": 0, "thread": 0,
        "gmail_message": 0, "gmail_thread": 0, "gmail_label": 0, "gmail_draft": 0,
    }

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
            system = (request.system_prompt or "").lower()

            # Detect entity type from the system prompt ("Generate realistic X entities")
            import re as _re
            _et_match = _re.search(r"generate realistic (\w+) entities", system)
            detected_type = _et_match.group(1) if _et_match else None

            # Gmail-aligned message entities (email pack — namespaced as gmail_message)
            if detected_type == "gmail_message":
                count = _parse_count(user, 10)
                entities = []
                for i in range(count):
                    _entity_counter.setdefault("gmail_message", 0)
                    _entity_counter["gmail_message"] += 1
                    idx = _entity_counter["gmail_message"]
                    body_text = f"Body of message {idx}. Please review your request."
                    entities.append({
                        "id": f"msg_{idx:03d}",
                        "threadId": f"thread_{(idx % 3) + 1:03d}",
                        "labelIds": [["INBOX", "UNREAD"], ["INBOX"], ["SENT"], ["INBOX"]][idx % 4],
                        "snippet": body_text[:50],
                        "subject": f"Support ticket #{idx}",
                        "body": body_text,
                        "from_addr": f"sender{idx}@acme.com",
                        "to_addr": f"recipient{idx}@test.com",
                        "internalDate": f"2026-03-{10 + idx:02d}T09:00:00Z",
                        "sizeEstimate": len(body_text),
                    })
                return LLMResponse(
                    content=json.dumps(entities),
                    provider="mock", model="mock", latency_ms=0,
                )

            # Gmail-aligned thread entities (email pack — namespaced as gmail_thread)
            if detected_type == "gmail_thread":
                count = _parse_count(user, 3)
                entities = []
                for i in range(count):
                    _entity_counter.setdefault("gmail_thread", 0)
                    _entity_counter["gmail_thread"] += 1
                    idx = _entity_counter["gmail_thread"]
                    entities.append({
                        "id": f"thread_{idx:03d}",
                        "snippet": f"Thread snippet {idx}",
                        "messages": [f"msg_{idx:03d}"],
                        "historyId": f"hist_{idx:03d}",
                    })
                return LLMResponse(
                    content=json.dumps(entities),
                    provider="mock", model="mock", latency_ms=0,
                )

            # Legacy email entities
            if detected_type == "email" or (
                "email" in user and "mailbox" not in user
                and detected_type not in (
                    "gmail_message", "gmail_thread", "gmail_label", "gmail_draft",
                    "message", "thread", "label", "draft",
                )
            ):
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

            if detected_type == "mailbox" or ("mailbox" in user and detected_type is None):
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

            # Legacy thread entities (chat pack or old email pack — thread_id/subject schema)
            if detected_type == "thread" or ("thread" in user and detected_type is None):
                count = _parse_count(user, 3)
                entities = []
                for i in range(count):
                    _entity_counter.setdefault("thread", 0)
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

            # Fallback for unknown entity types — generate schema-compatible entities
            # Parse entity type from prompt and generate matching fields
            count = _parse_count(user, 5)
            entity_type = detected_type or _extract_entity_type(user)
            entities = _generate_generic_entities(entity_type, count, _entity_counter)
            return LLMResponse(
                content=json.dumps(entities),
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


def _extract_entity_type(text: str) -> str:
    """Extract entity type from LLM generation prompt."""
    import re
    m = re.search(r"generate\s+\d+\s+(\w+)\s+entities", text)
    if m:
        return m.group(1)
    # Try simpler pattern (check longer names first to avoid partial matches)
    for etype in (
        "gmail_message", "gmail_thread", "gmail_label", "gmail_draft",
        "issue_comment", "pull_request", "pr_file",
        "payment_intent",
        "channel", "message", "user", "ticket", "comment", "group",
        "organization", "charge", "customer", "refund", "invoice", "dispute",
        "repository", "issue", "review", "commit",
        "event", "calendar", "attendee", "label", "draft",
    ):
        if etype in text:
            return etype
    return "unknown"


def _generate_generic_entities(
    entity_type: str, count: int, counters: dict,
) -> list[dict]:
    """Generate schema-compatible entities for any entity type."""
    counters.setdefault(entity_type, 0)
    entities: list[dict] = []
    # Entity templates with required fields matching real pack schemas
    templates: dict[str, callable] = {
        # Gmail-aligned entity types (email pack)
        "gmail_message": lambda idx: {
            "id": f"msg_{idx:03d}",
            "threadId": f"thread_{(idx % 3) + 1:03d}",
            "labelIds": [["INBOX", "UNREAD"], ["INBOX"], ["SENT"], ["INBOX"]][idx % 4],
            "snippet": f"Message snippet {idx}",
            "subject": f"Support ticket #{idx}",
            "body": f"Body of message {idx}.",
            "from_addr": f"sender{idx}@acme.com",
            "to_addr": f"recipient{idx}@test.com",
            "internalDate": f"2026-03-{10 + idx:02d}T09:00:00Z",
            "sizeEstimate": 50,
        },
        "gmail_thread": lambda idx: {
            "id": f"thread_{idx:03d}",
            "snippet": f"Thread snippet {idx}",
            "messages": [f"msg_{idx:03d}"],
            "historyId": f"hist_{idx:03d}",
        },
        "gmail_label": lambda idx: {
            "id": (
                f"label_{idx:03d}" if idx > 5
                else ["INBOX", "SENT", "DRAFT", "TRASH", "SPAM", "STARRED"][idx - 1]
            ),
            "name": (
                f"Label {idx}" if idx > 5
                else ["INBOX", "SENT", "DRAFT", "TRASH", "SPAM", "STARRED"][idx - 1]
            ),
            "type": "user" if idx > 5 else "system",
        },
        "gmail_draft": lambda idx: {
            "id": f"draft_{idx:03d}",
            "to": f"user{idx}@test.com",
            "subject": f"Draft {idx}",
            "body": f"Body {idx}",
        },
        # Chat pack entity types
        "channel": lambda idx: {
            "id": f"C{idx:03d}", "name": f"channel-{idx}",
            "is_channel": True, "is_private": False, "is_archived": False,
            "topic": {"value": ""}, "purpose": {"value": ""},
            "num_members": idx + 2, "created": 1700000000 + idx,
        },
        "message": lambda idx: {
            "id": f"170000{idx:04d}.{idx:06d}",
            "ts": f"170000{idx:04d}.{idx:06d}",
            "channel": "C001", "user": "U001",
            "text": f"Message {idx}", "type": "message",
            "reply_count": 0, "reactions": [],
        },
        "user": lambda idx: {
            "id": f"U{idx:03d}", "name": f"user{idx}",
            "real_name": f"User {idx}", "display_name": f"user{idx}",
            "email": f"user{idx}@acme.com", "is_bot": False, "is_admin": False,
            "status_text": "", "status_emoji": "",
            "role": ["end-user", "agent", "admin"][idx % 3],
            "active": True,
            "created_at": f"2026-01-{idx:02d}T00:00:00Z",
        },
        "ticket": lambda idx: {
            "id": f"ticket_{idx:03d}", "subject": f"Ticket {idx}",
            "description": f"Issue {idx}", "status": "open",
            "priority": "normal", "requester_id": "U001",
            "created_at": f"2026-03-{10+idx:02d}T09:00:00Z",
            "updated_at": f"2026-03-{10+idx:02d}T09:00:00Z",
        },
        "comment": lambda idx: {
            "id": f"comment_{idx:03d}", "ticket_id": f"ticket_001",
            "author_id": "U001", "body": f"Comment {idx}",
            "public": True, "created_at": f"2026-03-{10+idx:02d}T09:00:00Z",
        },
        "group": lambda idx: {
            "id": f"group_{idx:03d}", "name": f"Group {idx}",
            "created_at": f"2026-01-01T00:00:00Z",
        },
        "label": lambda idx: {
            "id": f"label_{idx:03d}" if idx > 5 else ["INBOX", "SENT", "DRAFT", "TRASH", "SPAM", "STARRED"][idx - 1],
            "name": f"Label {idx}" if idx > 5 else ["INBOX", "SENT", "DRAFT", "TRASH", "SPAM", "STARRED"][idx - 1],
            "type": "user" if idx > 5 else "system",
        },
        "draft": lambda idx: {
            "id": f"draft_{idx:03d}",
            "message": {"to": f"user{idx}@test.com", "subject": f"Draft {idx}", "body": f"Body {idx}"},
        },
        "payment_intent": lambda idx: {
            "id": f"pi_{idx:03d}", "amount": (idx + 1) * 1000,
            "currency": "usd", "status": "succeeded",
            "created": 1700000000 + idx,
        },
        "customer": lambda idx: {
            "id": f"cus_{idx:03d}", "name": f"Customer {idx}",
            "email": f"customer{idx}@test.com", "created": 1700000000 + idx,
        },
        "charge": lambda idx: {
            "id": f"ch_{idx:03d}", "amount": (idx + 1) * 1000,
            "currency": "usd", "paid": True, "captured": True,
            "refunded": False, "disputed": False, "created": 1700000000 + idx,
        },
        "refund": lambda idx: {
            "id": f"re_{idx:03d}", "amount": 500,
            "charge": f"ch_{idx:03d}", "currency": "usd",
            "status": "succeeded", "created": 1700000000 + idx,
        },
        "checkout_session": lambda idx: {
            "id": f"cs_{idx:03d}", "mode": "payment",
            "status": "complete", "payment_status": "paid",
            "url": f"https://checkout.stripe.com/c/pay/cs_{idx:03d}",
            "customer": f"cus_{(idx % 5) + 1:03d}",
        },
        "subscription": lambda idx: {
            "id": f"sub_{idx:03d}", "customer": f"cus_{(idx % 5) + 1:03d}",
            "status": "active", "current_period_end": 1800000000 + idx,
            "cancel_at_period_end": False,
        },
        "transaction": lambda idx: {
            "id": f"txn_{idx:03d}", "amount": (idx + 1) * 100,
            "currency": "usd", "status": "available",
            "payment_intent": f"pi_{(idx % 5) + 1:03d}",
        },
        "authorization": lambda idx: {
            "id": f"auth_{idx:03d}", "payment_intent": f"pi_{(idx % 5) + 1:03d}",
            "amount": (idx + 1) * 1000, "status": "closed",
        },
        "settlement": lambda idx: {
            "id": f"sett_{idx:03d}", "payment_intent": f"pi_{(idx % 5) + 1:03d}",
            "amount": (idx + 1) * 1000, "status": "settled",
        },
        "reversal": lambda idx: {
            "id": f"rev_{idx:03d}", "amount": 500,
            "status": "succeeded", "charge": f"ch_{(idx % 5) + 1:03d}",
            "payment_intent": f"pi_{(idx % 5) + 1:03d}",
        },
        "balance": lambda idx: {
            "id": f"bal_{idx:03d}", "available": (idx + 1) * 10000,
            "pending": idx * 500, "currency": "usd",
        },
        "web_site": lambda idx: {
            "id": f"site_{idx:03d}", "domain": f"site{idx}.acme.com",
            "name": f"Site {idx}", "site_type": "internal_dashboard",
            "created_at": f"2026-01-{idx + 1:02d}T00:00:00Z",
        },
        "web_session": lambda idx: {
            "id": f"sess_{idx:03d}", "actor_id": f"agent-{idx}",
            "status": "active",
            "created_at": f"2026-03-{10 + idx:02d}T09:00:00Z",
        },
        "web_page": lambda idx: {
            "id": f"page_{idx:03d}", "site_id": f"site_{(idx % 3) + 1:03d}",
            "domain": f"site{(idx % 3) + 1}.acme.com",
            "path": f"/page-{idx}", "title": f"Page {idx}",
            "page_type": ["entity_view", "article", "landing"][idx % 3],
            "status": "published",
            "content_source": "compiled",
            "created_at": f"2026-01-{idx + 1:02d}T00:00:00Z",
        },
        "repository": lambda idx: {
            "id": f"repo_{idx:03d}", "name": f"repo-{idx}",
            "full_name": f"org/repo-{idx}", "owner": {"login": "org", "type": "Organization"},
            "private": False, "default_branch": "main",
            "created_at": f"2026-01-{idx+1:02d}T00:00:00Z",
            "updated_at": f"2026-03-{idx+1:02d}T00:00:00Z",
        },
        "issue": lambda idx: {
            "number": idx, "title": f"Issue {idx}", "body": f"Body {idx}",
            "state": "open", "labels": [], "assignees": [],
            "user": {"login": "dev1"}, "comments": 0,
            "created_at": f"2026-03-{idx+1:02d}T00:00:00Z",
            "updated_at": f"2026-03-{idx+1:02d}T00:00:00Z",
            "locked": False,
        },
        "pull_request": lambda idx: {
            "number": 100 + idx, "title": f"PR {idx}", "body": f"PR body {idx}",
            "state": "open", "head": {"ref": f"feature-{idx}", "sha": f"abc{idx}"},
            "base": {"ref": "main", "sha": "def0"},
            "user": {"login": "dev1"}, "mergeable": True, "merged": False,
            "created_at": f"2026-03-{idx+1:02d}T00:00:00Z",
            "updated_at": f"2026-03-{idx+1:02d}T00:00:00Z",
        },
        "commit": lambda idx: {
            "sha": f"sha{idx:08d}", "message": f"Commit {idx}",
            "author": {"name": "Dev", "email": "dev@test.com", "date": f"2026-03-{idx+1:02d}T00:00:00Z"},
            "committer": {"name": "Dev", "email": "dev@test.com", "date": f"2026-03-{idx+1:02d}T00:00:00Z"},
        },
        "event": lambda idx: {
            "id": f"evt_{idx:03d}", "summary": f"Event {idx}",
            "status": "confirmed",
            "start": {"dateTime": f"2026-03-{10+idx:02d}T09:00:00Z"},
            "end": {"dateTime": f"2026-03-{10+idx:02d}T10:00:00Z"},
            "created": f"2026-01-01T00:00:00Z",
            "updated": f"2026-01-01T00:00:00Z",
        },
        "calendar": lambda idx: {
            "id": f"cal_{idx:03d}", "summary": f"Calendar {idx}",
            "timeZone": "America/New_York",
        },
        "attendee": lambda idx: {
            "id": f"att_{idx:03d}", "event_id": f"evt_001",
            "email": f"attendee{idx}@test.com", "responseStatus": "needsAction",
        },
        "invoice": lambda idx: {
            "id": f"in_{idx:03d}", "customer": "cus_001",
            "amount_due": (idx + 1) * 500, "currency": "usd",
            "status": "draft", "created": 1700000000 + idx,
        },
        "dispute": lambda idx: {
            "id": f"dp_{idx:03d}", "charge": f"ch_{idx:03d}",
            "amount": 1000, "currency": "usd",
            "status": "needs_response", "created": 1700000000 + idx,
        },
        "organization": lambda idx: {
            "id": f"org_{idx:03d}", "name": f"Organization {idx}",
            "domain_names": [f"org{idx}.com"],
            "created_at": f"2026-01-01T00:00:00Z",
            "updated_at": f"2026-01-01T00:00:00Z",
        },
        "review": lambda idx: {
            "id": f"review_{idx:03d}", "pull_number": 100 + idx,
            "user": {"login": f"reviewer{idx}"},
            "state": "COMMENTED", "body": f"Review comment {idx}",
            "submitted_at": f"2026-03-{idx+1:02d}T00:00:00Z",
            "commit_id": f"sha{idx:08d}",
        },
        "issue_comment": lambda idx: {
            "id": f"ic_{idx:03d}", "issue_number": idx,
            "user": {"login": "dev1"},
            "body": f"Comment {idx}",
            "created_at": f"2026-03-{idx+1:02d}T00:00:00Z",
            "updated_at": f"2026-03-{idx+1:02d}T00:00:00Z",
        },
        "pr_file": lambda idx: {
            "sha": f"filesha{idx:08d}",
            "filename": f"src/file{idx}.py",
            "status": "modified",
            "additions": idx * 5,
            "deletions": idx * 2,
            "changes": idx * 7,
        },
    }
    factory = templates.get(entity_type, lambda idx: {"id": f"{entity_type}_{idx:03d}"})
    for _ in range(count):
        counters[entity_type] += 1
        entities.append(factory(counters[entity_type]))
    return entities


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
    """Fully bootstrapped VolnixApp with tmp databases.

    Overrides persistence base_dir and state db_path so every test run
    uses isolated temporary storage.  Yields the running app and shuts
    it down on teardown.
    """
    from volnix.app import VolnixApp

    config = VolnixConfig()
    # VolnixConfig is frozen -- use model_copy to override fields
    config = config.model_copy(update={
        "persistence": PersistenceConfig(base_dir=str(tmp_path / "data")),
        "state": StateConfig(
            db_path=str(tmp_path / "state.db"),
            snapshot_dir=str(tmp_path / "snapshots"),
        ),
    })

    app = VolnixApp(config)
    await app.start()
    yield app
    await app.stop()


@pytest.fixture
async def app_with_mock_llm(tmp_path):
    """VolnixApp with a mock LLM router injected into the compiler.

    Use this fixture for tests that call generate_world() but do not
    have a real GOOGLE_API_KEY in the environment.
    """
    from volnix.app import VolnixApp

    config = VolnixConfig()
    config = config.model_copy(update={
        "persistence": PersistenceConfig(base_dir=str(tmp_path / "data")),
        "state": StateConfig(
            db_path=str(tmp_path / "state.db"),
            snapshot_dir=str(tmp_path / "snapshots"),
        ),
    })

    app = VolnixApp(config)
    await app.start()
    inject_mock_llm(app)
    yield app
    await app.stop()


@pytest.fixture
async def live_app(tmp_path):
    """VolnixApp with a REAL LLM router — requires GOOGLE_API_KEY.

    Skips the test if no API key is available.  Use for integration
    tests that exercise the actual LLM pipeline.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        pytest.skip("GOOGLE_API_KEY not set — skipping live LLM test")

    from volnix.app import VolnixApp

    config = VolnixConfig()
    config = config.model_copy(update={
        "persistence": PersistenceConfig(base_dir=str(tmp_path / "data")),
        "state": StateConfig(
            db_path=str(tmp_path / "state.db"),
            snapshot_dir=str(tmp_path / "snapshots"),
        ),
    })

    app = VolnixApp(config)
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
