# Plan D: Observer Actor Type + Governance Report for Mode 1

## Context

Two gaps combined:
1. **No observer actors** — the spec describes 200 trading actors + 4 researcher agents who can only observe. Today both are `type: internal` with identical access. No read-only enforcement.
2. **No governance report for Mode 1** — external agent testing should produce a packaged "report card" artifact. The Reporter engine has sub-components (scorecard, gaps, challenges, boundaries) but no combined output.

## What Already Exists (verified line numbers)

| What | Where | Status |
|---|---|---|
| `ActorType` enum | `core/types.py:122` | 3 values: AGENT, HUMAN, SYSTEM. No OBSERVER. |
| `PermissionEngine.execute()` | `permission/engine.py:59-198` | Checks read/write access to services |
| `ActorDefinition.type` | `actors/definition.py:24` | Accepts ActorType enum |
| `ScorecardComputer` | `reporter/scorecard.py` | Computes per-actor governance scores |
| `GapAnalyzer` | `reporter/capability_gaps.py` | Analyzes capability gap events |
| `WorldChallengeAnalyzer` | `reporter/world_challenges.py` | Analyzes world→agent challenges |
| `AgentBoundaryAnalyzer` | `reporter/agent_boundaries.py` | Analyzes agent→world boundaries |
| `generate_full_report()` | `reporter/engine.py:165` | Combines scorecard + gaps + condition report |
| `generate_condition_report()` | `reporter/engine.py:194` | Two-direction observation report |
| `_ALLOWED_ARTIFACT_TYPES` | `runs/artifacts.py:17` | 7 types including "deliverable" |
| `end_run()` | `app.py:1128` | Generates report + scorecard, saves artifacts |

---

## Part 1: Observer Actor Type

### Design

Add `OBSERVER` as a fourth value in `ActorType` enum. Observer actors can READ services but cannot WRITE. Enforced in the Permission Engine's `execute()` pipeline step — the same code path that already checks read/write access.

### Implementation

**`terrarium/core/types.py` line 122 — Extend ActorType:**

```python
class ActorType(enum.StrEnum):
    AGENT = "agent"
    HUMAN = "human"
    SYSTEM = "system"
    OBSERVER = "observer"  # NEW: read-only actor, can query but not mutate
```

**`terrarium/engines/permission/engine.py` — In `execute()` method:**

Insert at line ~108, BEFORE the existing write access check (line 111):

```python
        # Observer actors: read-only — deny all write actions
        actor_type = actor.type if hasattr(actor, "type") else ""
        if str(actor_type) == "observer":
            # Check if this is a read-only action
            action_lower = str(ctx.action).lower()
            read_prefixes = self._typed_config.observer_read_prefixes
            is_read = any(action_lower.startswith(p) for p in read_prefixes)
            if not is_read:
                event = PermissionDeniedEvent(
                    actor_id=ctx.actor_id,
                    service_id=ctx.service_id,
                    action=ctx.action,
                    reason=f"Observer actor cannot perform write action '{ctx.action}'",
                )
                return StepResult(
                    step_name=self.step_name,
                    verdict=StepVerdict.DENY,
                    message=f"Observer '{ctx.actor_id}' denied write: {ctx.action}",
                    events=[event],
                )
```

**`terrarium/engines/permission/config.py` — Add config field:**

```python
class PermissionConfig(BaseModel):
    cache_ttl_seconds: int = 300
    visibility_rule_entity_type: str = "visibility_rule"
    observer_read_prefixes: list[str] = [     # NEW
        "list", "get", "show", "search", "read", "query",
        "about", "hot", "new", "top", "best", "popular",
        "trending", "detail", "home_feed", "timeline",
        "followers", "following", "user_tweets", "user_submitted",
    ]
```

**`terrarium.toml` — Add to [permission]:**

```toml
[permission]
cache_ttl_seconds = 300
visibility_rule_entity_type = "visibility_rule"
observer_read_prefixes = [
    "list", "get", "show", "search", "read", "query",
    "about", "hot", "new", "top", "best", "popular",
    "trending", "detail", "home_feed", "timeline",
    "followers", "following", "user_tweets", "user_submitted",
]
```

**`terrarium/engines/agency/prompt_builder.py` — Observer instructions:**

In `build_individual_prompt()` at line ~130, after persona section:

```python
        # Observer mode instructions
        if actor.actor_type == "observer":
            sections.append(
                "### Observer Mode\n"
                "You are an OBSERVER. You can READ and ANALYZE data from services "
                "but you CANNOT create, update, or delete anything. Your role is "
                "to observe, analyze, and report findings."
            )
```

### YAML Example

```yaml
actors:
  - role: market-analyst
    type: observer
    personality: "Tracks order flow patterns, analyzes institutional behavior"

  - role: momentum-trader
    type: internal
    personality: "Buys momentum, sells reversals"
```

---

## Part 2: Governance Report (Mode 1 Output)

### Design

A `GovernanceReportGenerator` that packages existing sub-component outputs into one structured artifact. Uses EXISTING reporter sub-components — no new computation logic.

### Implementation

**New file: `terrarium/engines/reporter/governance_report.py`**

```python
"""Governance report generator — packages Mode 1 agent testing results.

Combines scorecard, capability gaps, world challenges, and agent
boundary analysis into one structured artifact. Uses EXISTING
reporter sub-components — no new computation, just packaging.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class GovernanceReportGenerator:
    """Produces the Mode 1 "report card" for external agent testing."""

    def __init__(
        self,
        scorecard_computer: Any,
        gap_analyzer: Any,
        challenge_analyzer: Any,
        boundary_analyzer: Any,
    ) -> None:
        self._scorecard = scorecard_computer
        self._gaps = gap_analyzer
        self._challenges = challenge_analyzer
        self._boundaries = boundary_analyzer

    async def generate(
        self,
        events: list[Any],
        actors: list[Any],
    ) -> dict[str, Any]:
        """Generate comprehensive governance report.

        Returns structured artifact combining all sub-component outputs.
        """
        scorecard = self._scorecard.compute(events, actors)
        gaps = self._gaps.analyze(events)
        gap_summary = self._gaps.get_gap_summary(events)
        challenges = self._challenges.analyze(events)
        boundaries = self._boundaries.analyze(events)

        # Extract external actor metrics
        external_actors = [
            a for a in actors
            if (a.get("type") if isinstance(a, dict) else getattr(a, "type", ""))
            in ("agent", "external")
        ]

        return {
            "type": "governance_report",
            "summary": {
                "total_actions": len([
                    e for e in events
                    if getattr(e, "event_type", "").startswith("world.")
                ]),
                "external_actors": len(external_actors),
                "overall_score": scorecard.get("collective", {}).get("overall_score"),
            },
            "scorecard": scorecard,
            "capability_gaps": {
                "gaps": gaps,
                "summary": gap_summary,
            },
            "world_challenges": challenges,
            "agent_boundaries": boundaries,
        }
```

**`terrarium/engines/reporter/engine.py` — Initialize and expose:**

In `_on_initialize()` at line ~56, after `self._boundary_analyzer`:

```python
        from terrarium.engines.reporter.governance_report import GovernanceReportGenerator
        self._governance_report = GovernanceReportGenerator(
            scorecard_computer=self._scorecard,
            gap_analyzer=self._gap_analyzer,
            challenge_analyzer=self._challenge_analyzer,
            boundary_analyzer=self._boundary_analyzer,
        )
```

Add method after `generate_condition_report()` at line ~200:

```python
    async def generate_governance_report(
        self, world_id: WorldId | None = None,
    ) -> dict[str, Any]:
        """Generate Mode 1 governance report for external agent testing."""
        events = await self._get_timeline()
        actors = self._get_actors()
        return await self._governance_report.generate(events, actors)
```

**`terrarium/app.py` — Generate in `end_run()`:**

In `end_run()` at line ~1160, after saving scorecard:

```python
        # Generate governance report for Mode 1 (external agent testing)
        actors_raw = run.get("world_def", {}).get("actors", [])
        has_external = any(
            (a.get("type") if isinstance(a, dict) else "")
            in ("agent", "external")
            for a in actors_raw
        )
        if has_external:
            try:
                gov_report = await reporter.generate_governance_report()
                await self._artifact_store.save(run_id, "governance_report", gov_report)
            except Exception as exc:
                logger.warning("Governance report generation failed: %s", exc)
```

**`terrarium/runs/artifacts.py` — Add artifact type:**

```python
_ALLOWED_ARTIFACT_TYPES = frozenset({
    "report", "scorecard", "event_log", "config", "metadata",
    "captured_surface", "deliverable", "governance_report",  # NEW
})
```

**`terrarium/engines/adapter/protocols/http_rest.py` — Add endpoint:**

```python
@app.get("/api/v1/runs/{run_id}/governance-report")
async def get_governance_report(run_id: str):
    """Get the governance report for a Mode 1 agent testing run."""
    from terrarium.core.types import RunId as _RId
    artifact = await gateway._app.artifact_store.load_artifact(
        _RId(run_id), "governance_report"
    )
    if artifact is None:
        from starlette.responses import JSONResponse
        return JSONResponse(
            status_code=404,
            content={"error": "No governance report for this run"},
        )
    return {"run_id": run_id, **artifact}
```

---

## Files to Create (3)

| # | File | What |
|---|---|---|
| 1 | `terrarium/engines/reporter/governance_report.py` | GovernanceReportGenerator |
| 2 | `tests/engines/permission/test_observer.py` | Observer permission tests |
| 3 | `tests/engines/reporter/test_governance_report.py` | Governance report tests |

## Files to Modify (6)

| # | File | Change |
|---|---|---|
| 4 | `terrarium/core/types.py:122` | Add `OBSERVER` to ActorType |
| 5 | `terrarium/engines/permission/engine.py:~108` | Observer read-only enforcement |
| 6 | `terrarium/engines/permission/config.py` | Add `observer_read_prefixes` |
| 7 | `terrarium/engines/agency/prompt_builder.py:~130` | Observer mode instructions |
| 8 | `terrarium/engines/reporter/engine.py:~56,~200` | Init + expose governance report |
| 9 | `terrarium/app.py:~1160` | Generate governance report in end_run() |
| 10 | `terrarium/runs/artifacts.py:17` | Add "governance_report" to allowed types |
| 11 | `terrarium/engines/adapter/protocols/http_rest.py` | Add `/governance-report` endpoint |
| 12 | `terrarium.toml` | Add `observer_read_prefixes` to [permission] |

## Test Harness

**`tests/engines/permission/test_observer.py`**

```python
"""Tests for observer actor type — read-only enforcement.

Harness tests catch regressions if new write actions are added
to packs without updating the observer prefix list.
"""

class TestObserverPermissions:
    async def test_observer_can_read(self):
        """Observer can call list/get/search/read actions."""
        ...

    async def test_observer_cannot_write(self):
        """Observer is denied create/update/delete actions."""
        ...

    async def test_observer_denied_event_published(self):
        """Observer denial produces PermissionDeniedEvent."""
        ...

    async def test_non_observer_unaffected(self):
        """Internal actor with same role is not restricted."""
        ...

class TestObserverHarness:
    def test_actor_type_has_observer(self):
        """ActorType enum must include OBSERVER."""
        from terrarium.core.types import ActorType
        assert hasattr(ActorType, "OBSERVER")
        assert ActorType.OBSERVER == "observer"

    def test_config_has_read_prefixes(self):
        """PermissionConfig must define observer_read_prefixes."""
        from terrarium.engines.permission.config import PermissionConfig
        config = PermissionConfig()
        assert isinstance(config.observer_read_prefixes, list)
        assert len(config.observer_read_prefixes) > 0

    def test_common_read_actions_in_prefixes(self):
        """Basic read prefixes must be present."""
        from terrarium.engines.permission.config import PermissionConfig
        config = PermissionConfig()
        required = {"list", "get", "search", "read", "query"}
        actual = set(config.observer_read_prefixes)
        assert required.issubset(actual), f"Missing: {required - actual}"
```

**`tests/engines/reporter/test_governance_report.py`**

```python
"""Tests for GovernanceReportGenerator."""

class TestGovernanceReport:
    async def test_report_has_required_sections(self):
        """Report must have: summary, scorecard, capability_gaps,
        world_challenges, agent_boundaries."""
        ...

    async def test_report_only_for_external_runs(self):
        """Governance report generated only when external actors present."""
        ...

    async def test_empty_events_produces_valid_report(self):
        """Empty event list produces report with zero metrics."""
        ...

class TestGovernanceReportHarness:
    def test_governance_report_in_artifact_types(self):
        """'governance_report' must be in _ALLOWED_ARTIFACT_TYPES."""
        from terrarium.runs.artifacts import _ALLOWED_ARTIFACT_TYPES
        assert "governance_report" in _ALLOWED_ARTIFACT_TYPES

    def test_reporter_has_governance_method(self):
        """ReportGeneratorEngine must have generate_governance_report()."""
        from terrarium.engines.reporter.engine import ReportGeneratorEngine
        assert hasattr(ReportGeneratorEngine, "generate_governance_report")
```

## What Does NOT Change
- Existing ActorType values (AGENT, HUMAN, SYSTEM) — unchanged
- Permission pipeline step for service-level access — unchanged
- Scorecard computation — reused, not modified
- Gap analysis — reused, not modified
- Challenge/boundary analysis — reused, not modified
- Internal actor behavior — unchanged
- External actor behavior — unchanged

## Verification
1. `uv run pytest tests/engines/permission/test_observer.py -v`
2. `uv run pytest tests/engines/reporter/test_governance_report.py -v`
3. `uv run pytest tests/ -q --ignore=tests/live` — no regressions
4. Live: world with observer + internal actors → observer read-only enforced
5. Live: world with external agent → `governance_report` artifact produced
6. Dashboard: `GET /api/v1/runs/{id}/governance-report` returns report
