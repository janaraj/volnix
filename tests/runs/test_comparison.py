"""Tests for volnix.runs.comparison — run-to-run comparison and scoring."""
import pytest

from volnix.core.types import RunId
from volnix.runs.artifacts import ArtifactStore
from volnix.runs.comparison import RunComparator
from volnix.runs.config import RunConfig


def _make_comparator(tmp_path) -> tuple[RunComparator, ArtifactStore]:
    store = ArtifactStore(RunConfig(data_dir=str(tmp_path / "runs")))
    return RunComparator(store), store


async def _seed_run(
    store: ArtifactStore, run_id: str, scorecard: dict,
    events: list, report: dict | None = None,
):
    """Save artifacts for a run so comparator can load them."""
    import json
    from pathlib import Path
    rid = RunId(run_id)
    # Save metadata so labels resolve
    run_dir = Path(store._data_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "metadata.json").write_text(json.dumps({"run_id": run_id, "tag": run_id}))
    await store.save_scorecard(rid, scorecard)
    await store.save_event_log(rid, events)
    if report:
        await store.save_report(rid, report)


@pytest.mark.asyncio
async def test_compare_scores_with_deltas(tmp_path):
    comparator, store = _make_comparator(tmp_path)
    card_a = {"collective": {"overall_score": 90, "policy_compliance": 95}}
    card_b = {"collective": {"overall_score": 80, "policy_compliance": 70}}
    await _seed_run(store, "run_a", card_a, [])
    await _seed_run(store, "run_b", card_b, [])
    result = await comparator.compare_scores([RunId("run_a"), RunId("run_b")])
    metrics = result["metrics"]
    # Should extract metrics from inside the collective section
    assert "overall_score" in metrics
    assert "policy_compliance" in metrics
    # Verify deltas are computed correctly
    overall = metrics["overall_score"]
    assert "deltas" in overall
    delta_key = "run_a→run_b"
    assert overall["deltas"][delta_key] == -10  # 80 - 90
    assert overall["values"]["run_a"] == 90
    assert overall["values"]["run_b"] == 80
    compliance = metrics["policy_compliance"]
    assert compliance["deltas"][delta_key] == -25  # 70 - 95


@pytest.mark.asyncio
async def test_compare_events_by_type(tmp_path):
    comparator, store = _make_comparator(tmp_path)
    events_a = [
        {"event_type": "world.email_send"},
        {"event_type": "world.email_send"},
        {"event_type": "policy_block"},
    ]
    events_b = [{"event_type": "world.email_send"}, {"event_type": "permission_denied"}]
    await _seed_run(store, "run_a", {}, events_a)
    await _seed_run(store, "run_b", {}, events_b)
    result = await comparator.compare_events([RunId("run_a"), RunId("run_b")])
    assert result["totals"]["run_a"] == 3
    assert result["totals"]["run_b"] == 2
    assert "world.email_send" in result["by_type"]


@pytest.mark.asyncio
async def test_compare_governed_ungoverned_governance_metrics(tmp_path):
    comparator, store = _make_comparator(tmp_path)
    gov_events = [
        {"event_type": "world.email_send"},
        {"event_type": "policy_block", "actor_id": "a1"},
        {"event_type": "policy_hold", "actor_id": "a1"},
        {"event_type": "budget_exhausted", "actor_id": "a1"},
    ]
    ungov_events = [
        {"event_type": "world.email_send"},
        {"event_type": "world.email_send"},
        {"event_type": "permission_denied", "actor_id": "a1"},
    ]
    await _seed_run(store, "gov", {"collective": {"overall_score": 94}}, gov_events)
    await _seed_run(store, "ungov", {"collective": {"overall_score": 78}}, ungov_events)
    result = await comparator.compare_governed_ungoverned(RunId("gov"), RunId("ungov"))
    gm = result["governance_metrics"]
    assert gm["blocked_actions"]["gov"] == 1
    assert gm["blocked_actions"]["ungov"] == 0
    assert gm["approval_requests"]["gov"] == 1
    assert gm["unauthorized_access"]["ungov"] == 1
    assert "governed_run_id" in result


@pytest.mark.asyncio
async def test_format_comparison_produces_table(tmp_path):
    comparator, store = _make_comparator(tmp_path)
    await _seed_run(store, "run_x", {"collective": {"score": 90}}, [])
    await _seed_run(store, "run_y", {"collective": {"score": 80}}, [])
    comparison = await comparator.compare([RunId("run_x"), RunId("run_y")])
    table = comparator.format_comparison(comparison)
    assert "Run Comparison" in table
    assert "Scores" in table


@pytest.mark.asyncio
async def test_compare_missing_scorecard_handled(tmp_path):
    comparator, store = _make_comparator(tmp_path)
    # Only seed metadata, no scorecard
    import json
    from pathlib import Path
    for rid in ["run_m", "run_n"]:
        run_dir = Path(store._data_dir) / rid
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "metadata.json").write_text(json.dumps({"run_id": rid, "tag": rid}))
    result = await comparator.compare_scores([RunId("run_m"), RunId("run_n")])
    # Should not crash — returns empty metrics
    assert "metrics" in result


@pytest.mark.asyncio
async def test_compare_entity_states(tmp_path):
    comparator, store = _make_comparator(tmp_path)
    report_a = {"entities": {"email": [{"id": "1"}, {"id": "2"}], "thread": [{"id": "3"}]}}
    report_b = {"entities": {"email": [{"id": "1"}], "thread": [{"id": "3"}, {"id": "4"}]}}
    await _seed_run(store, "run_e1", {}, [], report_a)
    await _seed_run(store, "run_e2", {}, [], report_b)
    result = await comparator.compare_entity_states([RunId("run_e1"), RunId("run_e2")])
    assert result["by_type"]["email"]["run_e1"] == 2
    assert result["by_type"]["email"]["run_e2"] == 1
    assert result["by_type"]["thread"]["run_e2"] == 2


@pytest.mark.asyncio
async def test_compare_full_orchestration(tmp_path):
    comparator, store = _make_comparator(tmp_path)
    card_a = {"collective": {"overall_score": 90}}
    card_b = {"collective": {"overall_score": 75}}
    events_a = [{"event_type": "world.action"}, {"event_type": "policy_block"}]
    events_b = [{"event_type": "world.action"}]
    report_a = {"entities": {"email": [{"id": "1"}]}}
    report_b = {"entities": {"email": [{"id": "1"}, {"id": "2"}]}}
    await _seed_run(store, "run_a", card_a, events_a, report_a)
    await _seed_run(store, "run_b", card_b, events_b, report_b)
    result = await comparator.compare([RunId("run_a"), RunId("run_b")])
    assert "run_ids" in result
    assert result["run_ids"] == ["run_a", "run_b"]
    assert "labels" in result
    assert "scores" in result
    assert "events" in result
    assert "entity_states" in result
