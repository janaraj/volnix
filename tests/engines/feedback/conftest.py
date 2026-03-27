"""Shared test fixtures for feedback engine tests.

Provides reusable database connections, stores, factories, and
mock objects that all feedback test files depend on.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from terrarium.engines.feedback.annotations import AnnotationStore
from terrarium.engines.feedback.config import FeedbackConfig
from terrarium.engines.feedback.models import (
    CapturedSurface,
    ObservedError,
    ObservedMutation,
    ObservedOperation,
)
from terrarium.packs.profile_schema import (
    ProfileEntity,
    ProfileOperation,
    ProfileStateMachine,
    ServiceProfileData,
)
from terrarium.persistence.sqlite import SQLiteDatabase


@pytest.fixture
async def annotation_db(tmp_path):
    """Temporary SQLite database for annotation tests."""
    db = SQLiteDatabase(str(tmp_path / "annotations.db"))
    await db.connect()
    yield db
    await db.close()


@pytest.fixture
async def annotation_store(annotation_db):
    """Initialized AnnotationStore with temp database."""
    store = AnnotationStore(annotation_db)
    await store.initialize()
    return store


@pytest.fixture
def feedback_config():
    """Default FeedbackConfig for testing."""
    return FeedbackConfig(
        promotion_min_annotations=1,
    )


@pytest.fixture
def make_captured_surface():
    """Factory for CapturedSurface with sensible defaults."""

    def _make(
        service_name: str = "twilio",
        run_id: str = "run-001",
        operations: list[ObservedOperation] | None = None,
        mutations: list[ObservedMutation] | None = None,
        errors: list[ObservedError] | None = None,
        annotations: list[dict[str, Any]] | None = None,
        **overrides: Any,
    ) -> CapturedSurface:
        defaults = {
            "service_name": service_name,
            "run_id": run_id,
            "captured_at": datetime.now(UTC).isoformat(),
            "operations_observed": operations or [
                ObservedOperation(
                    name=f"{service_name}_send_message",
                    call_count=5,
                    parameter_keys=["to", "body"],
                    response_keys=["sid", "status"],
                ),
                ObservedOperation(
                    name=f"{service_name}_list_messages",
                    call_count=3,
                    parameter_keys=[],
                    response_keys=["messages", "total"],
                ),
                ObservedOperation(
                    name=f"{service_name}_get_message",
                    call_count=2,
                    parameter_keys=["sid"],
                    response_keys=["sid", "body", "status"],
                ),
            ],
            "entity_mutations": mutations or [
                ObservedMutation(entity_type="message", operation="create", count=5),
            ],
            "error_patterns": errors or [],
            "annotations": annotations or [],
            "behavioral_rules": [],
            "source_profile": service_name,
            "fidelity_source": "bootstrapped",
        }
        defaults.update(overrides)
        return CapturedSurface(**defaults)

    return _make


@pytest.fixture
def make_profile():
    """Factory for ServiceProfileData with bootstrapped fidelity."""

    def _make(
        service_name: str = "twilio",
        fidelity_source: str = "bootstrapped",
        **overrides: Any,
    ) -> ServiceProfileData:
        defaults = {
            "profile_name": service_name,
            "service_name": service_name,
            "category": "communications",
            "version": "0.1.0",
            "fidelity_source": fidelity_source,
            "operations": [
                ProfileOperation(
                    name=f"{service_name}_send_message",
                    service=service_name,
                    description="Send a message",
                    http_method="POST",
                    http_path=f"/v1/{service_name}/messages",
                    parameters={"to": {"type": "string"}, "body": {"type": "string"}},
                    required_params=["to", "body"],
                    response_schema={
                        "type": "object",
                        "properties": {"sid": {"type": "string"}, "status": {"type": "string"}},
                    },
                    creates_entity="message",
                ),
                ProfileOperation(
                    name=f"{service_name}_list_messages",
                    service=service_name,
                    description="List messages",
                    http_method="GET",
                    http_path=f"/v1/{service_name}/messages",
                    is_read_only=True,
                ),
                ProfileOperation(
                    name=f"{service_name}_get_message",
                    service=service_name,
                    description="Get a message by SID",
                    http_method="GET",
                    http_path=f"/v1/{service_name}/messages/{{sid}}",
                    parameters={"sid": {"type": "string"}},
                    required_params=["sid"],
                    is_read_only=True,
                ),
            ],
            "entities": [
                ProfileEntity(
                    name="message",
                    identity_field="sid",
                    fields={
                        "sid": {"type": "string"},
                        "body": {"type": "string"},
                        "status": {"type": "string"},
                    },
                    required=["sid", "body"],
                ),
            ],
            "state_machines": [
                ProfileStateMachine(
                    entity_type="message",
                    field="status",
                    transitions={"queued": ["sent", "failed"], "sent": ["delivered"]},
                ),
            ],
            "responder_prompt": f"You are simulating the {service_name} API.",
        }
        defaults.update(overrides)
        return ServiceProfileData(**defaults)

    return _make


@pytest.fixture
def mock_artifact_store():
    """Mock ArtifactStore returning sample event log data."""
    store = AsyncMock()

    sample_events = [
        {
            "event_type": "world.twilio_send_message",
            "service_id": "twilio",
            "action": "twilio_send_message",
            "input_data": {"to": "+1555123", "body": "Hello"},
            "response_body": {"sid": "SM001", "status": "queued"},
        },
        {
            "event_type": "world.twilio_send_message",
            "service_id": "twilio",
            "action": "twilio_send_message",
            "input_data": {"to": "+1555456", "body": "World"},
            "response_body": {"sid": "SM002", "status": "queued"},
        },
        {
            "event_type": "world.twilio_list_messages",
            "service_id": "twilio",
            "action": "twilio_list_messages",
            "input_data": {},
            "response_body": {"messages": [], "total": 2},
        },
        {
            "event_type": "world.email_send",
            "service_id": "gmail",
            "action": "email_send",
            "input_data": {"to": "a@b.com"},
            "response_body": {"id": "msg-001"},
        },
    ]

    store.load_artifact = AsyncMock(return_value=sample_events)
    store.save_artifact = AsyncMock()
    return store


@pytest.fixture
def mock_profile_registry(make_profile):
    """Mock ProfileRegistry with register/get/list methods."""
    registry = AsyncMock()
    profiles: dict[str, ServiceProfileData] = {}

    def _register(profile):
        profiles[profile.service_name] = profile

    def _get(name):
        return profiles.get(name)

    def _list():
        return list(profiles.values())

    def _has(name):
        return name in profiles

    registry.register = _register
    registry.get_profile = _get
    registry.list_profiles = _list
    registry.has_profile = _has

    return registry
