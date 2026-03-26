"""Tests for DriftDetector -- drift detection framework."""
from __future__ import annotations

from unittest.mock import AsyncMock

from terrarium.engines.feedback.drift import (
    DriftDetector,
    OpenAPIDriftSource,
    _diff_operations,
    _extract_operations_from_markdown,
)


def test_diff_operations_added():
    """New ops in external that aren't in profile."""
    added, removed = _diff_operations(
        {"op_a", "op_b"}, {"op_a", "op_b", "op_c"}
    )
    assert added == ["op_c"]
    assert removed == []


def test_diff_operations_removed():
    """Ops in profile that aren't in external."""
    added, removed = _diff_operations(
        {"op_a", "op_b", "op_c"}, {"op_a"}
    )
    assert added == []
    assert removed == ["op_b", "op_c"]


def test_diff_operations_no_drift():
    """Same ops in both."""
    added, removed = _diff_operations({"op_a"}, {"op_a"})
    assert added == []
    assert removed == []


def test_extract_operations_from_markdown():
    """Extract HTTP method + path from markdown."""
    md = """
    ## Endpoints
    - GET /v1/messages
    - POST /v1/messages
    - DELETE /v1/messages/{id}
    Some text here.
    """
    ops = _extract_operations_from_markdown(md)
    assert "GET /v1/messages" in ops
    assert "POST /v1/messages" in ops
    assert len(ops) >= 3


async def test_openapi_drift_source_detects_version_change(
    make_profile,
):
    """OpenAPI source detects version mismatch."""
    profile = make_profile(version="1.0.0")

    provider = AsyncMock()
    provider.supports = AsyncMock(return_value=True)
    provider.fetch = AsyncMock(return_value={
        "version": "2.0.0",
        "operations": [
            {"name": "twilio_send_message"},
            {"name": "twilio_list_messages"},
            {"name": "twilio_get_message"},
        ],
    })

    source = OpenAPIDriftSource(provider)
    report = await source.check(profile)

    assert report is not None
    assert report.has_drift is True
    assert "2.0.0" in report.summary


async def test_detector_runs_all_sources(make_profile):
    """DriftDetector runs all registered sources."""
    profile = make_profile()

    # One source finds drift, one doesn't
    hub = AsyncMock()
    hub.is_available = AsyncMock(return_value=False)  # unavailable

    openapi = AsyncMock()
    openapi.supports = AsyncMock(return_value=True)
    openapi.fetch = AsyncMock(return_value={
        "version": "2.0.0",
        "operations": [{"name": "new_op"}],
    })

    detector = DriftDetector(providers={
        "context_hub": hub,
        "openapi": openapi,
    })
    reports = await detector.check(profile)

    # Only OpenAPI source should produce a report
    assert len(reports) == 1
    assert reports[0].source == "openapi"
