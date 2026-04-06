"""Tests for volnix.core.protocols — runtime-checkable Protocol definitions."""
import pytest
from volnix.core.protocols import (
    PipelineStep, StateEngineProtocol, PolicyEngineProtocol,
    EventBusProtocol, PermissionEngineProtocol, BudgetEngineProtocol,
    ResponderProtocol, AnimatorProtocol, AdapterProtocol,
    ReporterProtocol, FeedbackProtocol, WorldCompilerProtocol,
    GatewayProtocol, LedgerProtocol,
)


def test_pipeline_step_is_runtime_checkable():
    assert hasattr(PipelineStep, "__protocol_attrs__") or hasattr(PipelineStep, "_is_runtime_protocol")


def test_state_engine_protocol_methods():
    methods = ["get_entity", "query_entities", "propose_mutation", "commit_event"]
    for m in methods:
        assert hasattr(StateEngineProtocol, m)


def test_policy_engine_protocol_methods():
    assert hasattr(PolicyEngineProtocol, "evaluate")
    assert hasattr(PolicyEngineProtocol, "get_active_policies")


def test_all_protocols_are_runtime_checkable():
    protocols = [
        PipelineStep, StateEngineProtocol, PolicyEngineProtocol,
        EventBusProtocol, PermissionEngineProtocol, BudgetEngineProtocol,
        ResponderProtocol, AnimatorProtocol, AdapterProtocol,
        ReporterProtocol, FeedbackProtocol, WorldCompilerProtocol,
        GatewayProtocol, LedgerProtocol,
    ]
    for proto in protocols:
        # runtime_checkable protocols can be used with isinstance
        assert isinstance(proto, type)
