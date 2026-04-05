"""Tests for ServiceCapture -- extract behavioral fingerprint from runs."""
from __future__ import annotations

from volnix.engines.feedback.capture import ServiceCapture


async def test_capture_from_event_log(mock_artifact_store, annotation_store):
    """Capture extracts operations and mutations from event log."""
    capture = ServiceCapture(mock_artifact_store, annotation_store)
    surface = await capture.capture("run-001", "twilio")

    assert surface.service_name == "twilio"
    assert surface.run_id == "run-001"

    # Should find twilio operations, not email ones
    op_names = [o.name for o in surface.operations_observed]
    assert "twilio_send_message" in op_names
    assert "twilio_list_messages" in op_names
    assert "email_send" not in op_names

    # twilio_send_message called 2 times
    send_op = next(o for o in surface.operations_observed if o.name == "twilio_send_message")
    assert send_op.call_count == 2
    assert "to" in send_op.parameter_keys
    assert "body" in send_op.parameter_keys
    assert "sid" in send_op.response_keys


async def test_capture_includes_annotations(mock_artifact_store, annotation_store):
    """Annotations for the run are included in the capture."""
    await annotation_store.add(
        "twilio", "Messages must have +E.164 format", "user", run_id="run-001"
    )
    await annotation_store.add("stripe", "Unrelated note", "user", run_id="run-001")

    capture = ServiceCapture(mock_artifact_store, annotation_store)
    surface = await capture.capture("run-001", "twilio")

    assert len(surface.annotations) == 1
    assert "E.164" in surface.annotations[0]["text"]
    assert len(surface.behavioral_rules) == 1


async def test_capture_empty_run(annotation_store):
    """Capture handles a run with no events gracefully."""
    from unittest.mock import AsyncMock

    empty_store = AsyncMock()
    empty_store.load_artifact = AsyncMock(return_value=[])

    capture = ServiceCapture(empty_store, annotation_store)
    surface = await capture.capture("run-empty", "twilio")

    assert surface.operations_observed == []
    assert surface.entity_mutations == []
    assert surface.error_patterns == []


async def test_capture_filters_by_service(mock_artifact_store, annotation_store):
    """Only events matching the service are included."""
    capture = ServiceCapture(mock_artifact_store, annotation_store)

    # Capture email — should only get email events
    email_surface = await capture.capture("run-001", "email")
    op_names = [o.name for o in email_surface.operations_observed]
    assert "email_send" in op_names
    assert "twilio_send_message" not in op_names
