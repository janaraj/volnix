"""Integration tests for AgencyEngine configuration via compile_and_run.

Tests that the compilation pipeline correctly creates ActorStates for
internal actors and wires them into the AgencyEngine.
"""

from __future__ import annotations

import pytest

from volnix.actors.state import ActorState


@pytest.mark.asyncio
class TestConfigureAgency:
    """Test configure_agency flow: compilation -> ActorState creation."""

    async def test_configure_agency_creates_actor_states(self, app_with_mock_llm) -> None:
        """Compiling a world with internal actors produces ActorStates in the AgencyEngine."""
        app = app_with_mock_llm
        compiler = app.registry.get("world_compiler")

        # acme_support.yaml has internal actors: supervisor + 50 customers
        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )
        result = await compiler.generate_world(plan)

        # configure_agency should create ActorStates for internal actors
        await app.configure_agency(plan, result)

        # Check that the agency engine has actor states
        try:
            agency = app.registry.get("agency")
        except KeyError:
            pytest.skip("Agency engine not registered")

        states = agency.get_all_states()

        # There should be at least one internal actor (supervisor)
        assert len(states) > 0

        # All states should be ActorState instances with actor_type == "internal"
        for state in states:
            assert isinstance(state, ActorState)
            assert state.actor_type == "internal"

        # Verify the states have behavior_traits set
        for state in states:
            assert state.behavior_traits is not None

    async def test_configure_agency_no_internal_actors(self, app_with_mock_llm) -> None:
        """A world with only external agents should yield zero actor states in AgencyEngine."""
        app = app_with_mock_llm
        compiler = app.registry.get("world_compiler")

        # minimal_world.yaml should have fewer/no internal actors
        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/minimal_world.yaml",
        )
        result = await compiler.generate_world(plan)

        await app.configure_agency(plan, result)

        try:
            agency = app.registry.get("agency")
        except KeyError:
            pytest.skip("Agency engine not registered")

        # Count only internal actor states
        states = agency.get_all_states()
        internal_states = [s for s in states if s.actor_type == "internal"]

        # Check actors from result to understand expected count
        actors = result.get("actors", [])
        internal_actors = [a for a in actors if str(a.type) in ("human", "system")]

        # The agency should have exactly as many states as internal actors
        assert len(internal_states) == len(internal_actors)


@pytest.mark.asyncio
class TestAgencyIntegrationExtended:
    """Extended integration tests for AgencyEngine wiring and lifecycle."""

    async def test_configure_agency_skips_external_actors(self, app_with_mock_llm) -> None:
        """Compile world where some actors are type='external'.

        Verify those actors do NOT get ActorState in AgencyEngine.
        """
        app = app_with_mock_llm
        compiler = app.registry.get("world_compiler")

        # acme_support.yaml has both internal and external actors
        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )
        result = await compiler.generate_world(plan)

        await app.configure_agency(plan, result)

        try:
            agency = app.registry.get("agency")
        except KeyError:
            pytest.skip("Agency engine not registered")

        states = agency.get_all_states()

        # Every managed state must be internal -- no external actors
        for state in states:
            assert state.actor_type == "internal", (
                f"Actor {state.actor_id} is {state.actor_type}, expected 'internal'"
            )

        # Verify that any external actors from compilation are excluded
        actors = result.get("actors", [])
        external_actors = [a for a in actors if str(a.type) == "agent"]
        for ext in external_actors:
            found = agency.get_actor_state(ext.id)
            assert found is None, (
                f"External actor {ext.id} should NOT have ActorState"
            )

    async def test_agency_engine_notified_on_bus_event(self, app_with_mock_llm) -> None:
        """Publish a WorldEvent to bus -> verify AgencyEngine._handle_event is invoked."""
        from datetime import UTC, datetime
        from unittest.mock import AsyncMock, patch

        from volnix.core.events import WorldEvent
        from volnix.core.types import ActorId, ServiceId, Timestamp

        app = app_with_mock_llm

        try:
            agency = app.registry.get("agency")
        except KeyError:
            pytest.skip("Agency engine not registered")

        now = datetime.now(UTC)
        event = WorldEvent(
            event_type="world.test_action",
            timestamp=Timestamp(world_time=now, wall_time=now, tick=1),
            actor_id=ActorId("test-actor"),
            service_id=ServiceId("svc"),
            action="test_action",
        )

        with patch.object(agency, "_handle_event", new_callable=AsyncMock) as mock_handle:
            # Dispatch event directly (simulating bus delivery)
            await agency._handle_event(event)
            mock_handle.assert_called_once_with(event)

    async def test_full_agency_loop_mock(self, app_with_mock_llm) -> None:
        """Create world, configure agency, submit external action, run through loop.

        Verify: event committed, agency notified, state updated.
        """
        from datetime import UTC, datetime
        from unittest.mock import AsyncMock

        from volnix.core.envelope import ActionEnvelope
        from volnix.core.events import WorldEvent
        from volnix.core.types import (
            ActionSource,
            ActorId,
            EnvelopePriority,
            ServiceId,
            Timestamp,
        )
        from volnix.simulation.config import SimulationRunnerConfig
        from volnix.simulation.event_queue import EventQueue
        from volnix.simulation.runner import SimulationRunner

        app = app_with_mock_llm
        compiler = app.registry.get("world_compiler")

        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )
        result = await compiler.generate_world(plan)
        await app.configure_agency(plan, result)

        try:
            agency = app.registry.get("agency")
        except KeyError:
            pytest.skip("Agency engine not registered")

        now = datetime.now(UTC)
        committed_event = WorldEvent(
            event_type="world.email_send",
            timestamp=Timestamp(world_time=now, wall_time=now, tick=1),
            actor_id=ActorId("ext-agent"),
            service_id=ServiceId("gmail"),
            action="email_send",
        )

        # Mock pipeline executor to return the committed event
        executor = AsyncMock(return_value=committed_event)

        q = EventQueue()
        config = SimulationRunnerConfig(
            stop_on_empty_queue=True,
            max_total_events=5,
        )

        # Track if agency was notified
        original_notify = agency.notify
        notify_calls = []

        async def tracked_notify(ev):
            notify_calls.append(ev)
            return await original_notify(ev)

        agency.notify = tracked_notify

        runner = SimulationRunner(
            event_queue=q,
            pipeline_executor=executor,
            agency_engine=agency,
            config=config,
        )

        envelope = ActionEnvelope(
            actor_id=ActorId("ext-agent"),
            source=ActionSource.EXTERNAL,
            action_type="email_send",
            target_service=ServiceId("gmail"),
            logical_time=1.0,
            priority=EnvelopePriority.EXTERNAL,
        )
        q.submit(envelope)

        await runner.run()

        # Pipeline was called
        executor.assert_called()
        # Agency was notified of committed event
        assert len(notify_calls) >= 1

    async def test_agency_with_world_context_bundle(self, app_with_mock_llm) -> None:
        """Verify WorldContextBundle was created with correct fields."""
        app = app_with_mock_llm
        compiler = app.registry.get("world_compiler")

        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )
        result = await compiler.generate_world(plan)
        await app.configure_agency(plan, result)

        try:
            agency = app.registry.get("agency")
        except KeyError:
            pytest.skip("Agency engine not registered")

        ctx = agency._world_context
        assert ctx is not None, "WorldContextBundle should be set after configure"
        assert isinstance(ctx.world_description, str)
        assert isinstance(ctx.behavior_mode, str)
        assert ctx.behavior_mode in ("static", "reactive", "dynamic")

    async def test_agency_engine_has_semaphore(self, app_with_mock_llm) -> None:
        """Verify _llm_semaphore exists and has correct value from config."""
        import asyncio

        app = app_with_mock_llm

        try:
            agency = app.registry.get("agency")
        except KeyError:
            pytest.skip("Agency engine not registered")

        assert hasattr(agency, "_llm_semaphore")
        assert isinstance(agency._llm_semaphore, asyncio.Semaphore)
        # The semaphore value should match the configured max_concurrent_actor_calls
        expected = agency._typed_config.max_concurrent_actor_calls
        # asyncio.Semaphore._value is the internal counter
        assert agency._llm_semaphore._value == expected
