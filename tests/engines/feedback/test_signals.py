"""Tests for Signal Framework -- local signal aggregation."""
from __future__ import annotations

from unittest.mock import AsyncMock

from terrarium.engines.feedback.signals import (
    SIGNAL_REGISTRY,
    ServiceUsageSignal,
    SignalAggregator,
    SignalContext,
)


def _make_context(
    runs: list | None = None,
    event_logs: dict | None = None,
) -> SignalContext:
    """Create a SignalContext with test data."""
    return SignalContext(
        runs=runs or [
            {
                "run_id": "run-001",
                "world_def": {
                    "name": "Support Team",
                    "services": {"gmail": "verified/gmail", "twilio": "profiled/twilio"},
                },
            },
            {
                "run_id": "run-002",
                "world_def": {
                    "name": "Support Team",
                    "services": {"gmail": "verified/gmail", "jira": "profiled/jira"},
                },
            },
            {
                "run_id": "run-003",
                "world_def": {
                    "name": "E-Commerce",
                    "services": {"stripe": "verified/stripe"},
                },
            },
        ],
        event_logs=event_logs or {
            "run-001": [
                {"event_type": "world.twilio_send", "service_id": "twilio"},
                {"event_type": "world.email_send", "service_id": "gmail"},
                {"event_type": "capability.gap", "requested_tool": "slack_post"},
            ],
            "run-002": [
                {"event_type": "world.email_send", "service_id": "gmail"},
                {"event_type": "capability.gap", "requested_tool": "slack_post"},
                {"event_type": "world.jira_create", "service_id": "jira", "error": "timeout"},
            ],
        },
        annotation_counts={"twilio": 2, "jira": 1},
        profile_fidelities={
            "twilio": "bootstrapped",
            "jira": "curated_profile",
            "email": "verified",
        },
    )


async def test_service_usage_signal():
    """ServiceUsageSignal counts service mentions across runs."""
    ctx = _make_context()
    signal = ServiceUsageSignal()
    result = await signal.collect(ctx)

    assert result.signal_name == "service_usage"
    assert len(result.entries) > 0

    # gmail appears in 2 runs
    gmail_entry = next(
        (e for e in result.entries if e["service_name"] == "gmail"),
        None,
    )
    assert gmail_entry is not None
    assert gmail_entry["run_count"] == 2


async def test_capability_gap_signal():
    """CapabilityGapSignal aggregates missing tool requests."""
    from terrarium.engines.feedback.signals import CapabilityGapSignal

    ctx = _make_context()
    signal = CapabilityGapSignal()
    result = await signal.collect(ctx)

    assert result.signal_name == "capability_gaps"
    # slack_post requested in 2 runs
    slack_entry = next(
        (e for e in result.entries if e["tool_name"] == "slack_post"),
        None,
    )
    assert slack_entry is not None
    assert slack_entry["request_count"] == 2


async def test_template_insight_signal():
    """TemplateInsightSignal counts template reuse."""
    from terrarium.engines.feedback.signals import TemplateInsightSignal

    ctx = _make_context()
    signal = TemplateInsightSignal()
    result = await signal.collect(ctx)

    # "Support Team" used 2 times
    support_entry = next(
        (e for e in result.entries if e["template_name"] == "Support Team"),
        None,
    )
    assert support_entry is not None
    assert support_entry["run_count"] == 2


async def test_aggregator_runs_all_collectors():
    """SignalAggregator runs all registered collectors."""
    run_manager = AsyncMock()
    run_manager.list_runs = AsyncMock(return_value=[
        {"run_id": "r1", "world_def": {"name": "Test", "services": {"email": "x"}}},
    ])

    artifact_store = AsyncMock()
    artifact_store.load_artifact = AsyncMock(return_value=[])

    aggregator = SignalAggregator(
        run_manager=run_manager,
        artifact_store=artifact_store,
        annotation_store=None,
        profile_registry=None,
        max_runs=10,
    )

    signals = await aggregator.compute()

    assert signals.total_runs == 1
    assert len(signals.signals) == len(SIGNAL_REGISTRY)
    for name in SIGNAL_REGISTRY:
        assert name in signals.signals


async def test_aggregator_filters_by_enabled_signals():
    """Only enabled signals are computed."""
    run_manager = AsyncMock()
    run_manager.list_runs = AsyncMock(return_value=[])

    aggregator = SignalAggregator(
        run_manager=run_manager,
        artifact_store=AsyncMock(),
        annotation_store=None,
        profile_registry=None,
    )

    signals = await aggregator.compute(
        enabled_signals=["service_usage"]
    )

    assert "service_usage" in signals.signals
    assert "capability_gaps" not in signals.signals


async def test_empty_runs():
    """Signals handle empty run history gracefully."""
    run_manager = AsyncMock()
    run_manager.list_runs = AsyncMock(return_value=[])

    aggregator = SignalAggregator(
        run_manager=run_manager,
        artifact_store=AsyncMock(),
        annotation_store=None,
        profile_registry=None,
    )

    signals = await aggregator.compute()

    assert signals.total_runs == 0
    for result in signals.signals.values():
        assert result.entries == []


async def test_bootstrap_failure_signal():
    """M6: BootstrapFailureSignal finds bootstrapped services with errors."""
    from terrarium.engines.feedback.signals import BootstrapFailureSignal

    ctx = _make_context(
        event_logs={
            "run-001": [
                {"service_id": "twilio", "error": "timeout"},
                {"service_id": "twilio"},
                {"service_id": "twilio", "error": "connection refused"},
            ],
        },
    )
    # Override fidelity to bootstrapped for twilio
    ctx = SignalContext(
        runs=ctx.runs,
        event_logs=ctx.event_logs,
        annotation_counts=ctx.annotation_counts,
        profile_fidelities={"twilio": "bootstrapped"},
    )

    signal = BootstrapFailureSignal()
    result = await signal.collect(ctx)

    assert result.signal_name == "bootstrap_failures"
    assert len(result.entries) == 1
    assert result.entries[0]["service_name"] == "twilio"
    assert result.entries[0]["error_rate"] > 0.5  # 2/3 errors


def test_signal_registry_has_four_collectors():
    """Registry has all 4 built-in collectors."""
    assert len(SIGNAL_REGISTRY) == 4
    assert "service_usage" in SIGNAL_REGISTRY
    assert "bootstrap_failures" in SIGNAL_REGISTRY
    assert "capability_gaps" in SIGNAL_REGISTRY
    assert "template_insights" in SIGNAL_REGISTRY
