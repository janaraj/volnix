"""Live CLI tests for collaboration scenarios.

Runs real worlds through `volnix run` CLI command.
Verifies results via dashboard API endpoints.
Results persist to data/runs/ for frontend viewing.

Run with:
    uv run pytest tests/live/test_collaboration_cli.py -v -s --timeout=600
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import httpx
import pytest

VOLNIX_CMD = ["uv", "run", "volnix"]
DASHBOARD_URL = "http://127.0.0.1:8200"
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "worlds" / "collaboration"


def _run_world(yaml_name: str, tag: str, behavior: str = "dynamic", timeout: int = 300) -> subprocess.CompletedProcess:
    """Run a world YAML through the volnix CLI."""
    yaml_path = FIXTURES_DIR / yaml_name
    assert yaml_path.exists(), f"Fixture not found: {yaml_path}"

    result = subprocess.run(
        [
            *VOLNIX_CMD,
            "run",
            str(yaml_path),
            "--behavior", behavior,
            "--tag", tag,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    print(f"\n{'='*60}")
    print(f"WORLD: {yaml_name}  |  TAG: {tag}")
    print(f"{'='*60}")
    print(f"STDOUT:\n{result.stdout}")
    if result.stderr:
        print(f"STDERR:\n{result.stderr}")
    print(f"Return code: {result.returncode}")
    return result


async def _check_dashboard(tag: str) -> None:
    """Optionally verify run results via dashboard API."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{DASHBOARD_URL}/api/v1/runs")
            if resp.status_code != 200:
                print(f"Dashboard returned {resp.status_code}, skipping checks")
                return

            runs = resp.json()
            our_run = next(
                (r for r in runs.get("runs", []) if r.get("tag") == tag),
                None,
            )
            if not our_run:
                print(f"Run with tag '{tag}' not found in dashboard")
                return

            run_id = our_run["run_id"]
            print(f"Found run in dashboard: {run_id}")

            # Check messages
            msg_resp = await client.get(f"{DASHBOARD_URL}/api/v1/runs/{run_id}/messages")
            if msg_resp.status_code == 200:
                messages = msg_resp.json()
                print(f"Messages ({len(messages.get('messages', []))} total): "
                      f"{json.dumps(messages, indent=2)[:500]}")

            # Check deliverable
            del_resp = await client.get(f"{DASHBOARD_URL}/api/v1/runs/{run_id}/deliverable")
            if del_resp.status_code == 200:
                deliverable = del_resp.json()
                print(f"Deliverable: {json.dumps(deliverable, indent=2)[:500]}")
            else:
                print(f"No deliverable (status {del_resp.status_code})")

    except (httpx.ConnectError, httpx.ConnectTimeout):
        print("Dashboard not running, skipping API checks")
    except Exception as e:
        print(f"Dashboard check failed: {e}")


class TestSynthesisCLI:
    """Run climate research world through CLI and verify."""

    @pytest.mark.asyncio
    async def test_climate_research_via_cli(self):
        """Synthesis scenario: 4 researchers investigate jet stream anomalies."""
        tag = "collab-synthesis-test"
        result = _run_world("climate_research.yaml", tag)
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        await _check_dashboard(tag)


class TestDecisionCLI:
    """Run feature decision world through CLI and verify."""

    @pytest.mark.asyncio
    async def test_feature_decision_via_cli(self):
        """Decision scenario: product team chooses between dark mode, API v2, mobile app."""
        tag = "collab-decision-test"
        result = _run_world("feature_decision.yaml", tag)
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        await _check_dashboard(tag)


class TestPredictionCLI:
    """Run market prediction world through CLI and verify."""

    @pytest.mark.asyncio
    async def test_market_prediction_via_cli(self):
        """Prediction scenario: analysts predict S&P 500 direction."""
        tag = "collab-prediction-test"
        result = _run_world("market_prediction.yaml", tag)
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        await _check_dashboard(tag)


class TestBrainstormCLI:
    """Run campaign brainstorm world through CLI and verify."""

    @pytest.mark.asyncio
    async def test_campaign_brainstorm_via_cli(self):
        """Brainstorm scenario: creative team generates launch campaign ideas."""
        tag = "collab-brainstorm-test"
        result = _run_world("campaign_brainstorm.yaml", tag)
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        await _check_dashboard(tag)


class TestRecommendationCLI:
    """Run support triage world through CLI and verify."""

    @pytest.mark.asyncio
    async def test_support_triage_via_cli(self):
        """Recommendation scenario: support team triages post-outage ticket backlog."""
        tag = "collab-recommendation-test"
        result = _run_world("support_triage.yaml", tag)
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        await _check_dashboard(tag)


class TestAssessmentCLI:
    """Run security assessment world through CLI and verify."""

    @pytest.mark.asyncio
    async def test_security_assessment_via_cli(self):
        """Assessment scenario: security team evaluates company posture."""
        tag = "collab-assessment-test"
        result = _run_world("security_assessment.yaml", tag)
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        await _check_dashboard(tag)


class TestAllCollaborationScenarios:
    """Run all 6 scenarios sequentially for a full integration sweep."""

    SCENARIOS = [
        ("climate_research.yaml", "collab-all-synthesis"),
        ("feature_decision.yaml", "collab-all-decision"),
        ("market_prediction.yaml", "collab-all-prediction"),
        ("campaign_brainstorm.yaml", "collab-all-brainstorm"),
        ("support_triage.yaml", "collab-all-recommendation"),
        ("security_assessment.yaml", "collab-all-assessment"),
    ]

    @pytest.mark.asyncio
    async def test_all_scenarios(self):
        """Run all 6 collaboration worlds and verify each succeeds."""
        results = {}
        for yaml_name, tag in self.SCENARIOS:
            result = _run_world(yaml_name, tag)
            results[yaml_name] = result.returncode
            if result.returncode == 0:
                await _check_dashboard(tag)

        # Report summary
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        for yaml_name, code in results.items():
            status = "PASS" if code == 0 else "FAIL"
            print(f"  [{status}] {yaml_name}")

        failed = [name for name, code in results.items() if code != 0]
        assert not failed, f"Failed scenarios: {failed}"
