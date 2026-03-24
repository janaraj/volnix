"""Tests for terrarium.runs.artifacts — run artifact persistence."""
import pytest

from terrarium.core.types import RunId
from terrarium.runs.artifacts import ArtifactStore
from terrarium.runs.config import RunConfig


def _make_store(tmp_path) -> ArtifactStore:
    return ArtifactStore(RunConfig(data_dir=str(tmp_path / "runs")))


@pytest.mark.asyncio
async def test_save_load_report_roundtrip(tmp_path):
    store = _make_store(tmp_path)
    run_id = RunId("run_test001")
    report = {"summary": "All good", "score": 95}
    await store.save_report(run_id, report)
    loaded = await store.load_artifact(run_id, "report")
    assert loaded == report


@pytest.mark.asyncio
async def test_save_load_scorecard_roundtrip(tmp_path):
    store = _make_store(tmp_path)
    run_id = RunId("run_test002")
    scorecard = {"collective": {"overall_score": 88.5, "policy_compliance": 92.0}}
    await store.save_scorecard(run_id, scorecard)
    loaded = await store.load_artifact(run_id, "scorecard")
    assert loaded == scorecard


@pytest.mark.asyncio
async def test_save_load_event_log_roundtrip(tmp_path):
    store = _make_store(tmp_path)
    run_id = RunId("run_test003")
    events = [
        {"event_type": "world.email_send", "actor_id": "agent-1"},
        {"event_type": "policy_block", "actor_id": "agent-1"},
    ]
    await store.save_event_log(run_id, events)
    loaded = await store.load_artifact(run_id, "event_log")
    assert loaded == events


@pytest.mark.asyncio
async def test_list_artifacts_returns_saved_types(tmp_path):
    store = _make_store(tmp_path)
    run_id = RunId("run_test004")
    await store.save_report(run_id, {"a": 1})
    await store.save_scorecard(run_id, {"b": 2})
    artifacts = await store.list_artifacts(run_id)
    types = [a["type"] for a in artifacts]
    assert "report" in types
    assert "scorecard" in types
    assert len(artifacts) == 2


@pytest.mark.asyncio
async def test_load_nonexistent_returns_none(tmp_path):
    store = _make_store(tmp_path)
    result = await store.load_artifact(RunId("nonexistent"), "report")
    assert result is None


@pytest.mark.asyncio
async def test_save_returns_file_path(tmp_path):
    store = _make_store(tmp_path)
    run_id = RunId("run_test005")
    path = await store.save_report(run_id, {"test": True})
    assert isinstance(path, str)
    from pathlib import Path
    assert Path(path).exists()
    assert path.endswith("report.json")


@pytest.mark.asyncio
async def test_save_config_roundtrip(tmp_path):
    store = _make_store(tmp_path)
    run_id = RunId("run_test_cfg")
    config = {"seed": 42, "mode": "governed", "reality": "messy"}
    await store.save_config(run_id, config)
    loaded = await store.load_artifact(run_id, "config")
    assert loaded == config


@pytest.mark.asyncio
async def test_path_traversal_rejected(tmp_path):
    store = _make_store(tmp_path)
    run_id = RunId("run_test_traversal")
    with pytest.raises(ValueError):
        await store.load_artifact(run_id, "../../etc/passwd")
