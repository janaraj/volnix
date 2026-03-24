"""Tests for ReplayLog and ReplayEntry."""

from __future__ import annotations

from pathlib import Path

from terrarium.actors.replay import ReplayEntry, ReplayLog


def _make_entry(**kwargs) -> ReplayEntry:
    """Helper to create a ReplayEntry with defaults."""
    defaults = {
        "logical_time": 1.0,
        "envelope_id": "env-001",
        "actor_id": "actor-1",
        "activation_reason": "event_affected",
        "activation_tier": 2,
    }
    defaults.update(kwargs)
    return ReplayEntry(**defaults)


class TestReplayEntry:
    """Tests for the ReplayEntry frozen model."""

    def test_entry_creation(self) -> None:
        """ReplayEntry can be created with required fields."""
        entry = _make_entry()
        assert entry.logical_time == 1.0
        assert entry.actor_id == "actor-1"
        assert entry.llm_prompt is None
        assert entry.llm_output is None

    def test_entry_with_llm_fields(self) -> None:
        """ReplayEntry stores LLM prompt and output."""
        entry = _make_entry(
            llm_prompt="What should actor-1 do?",
            llm_output='{"action_type": "email_send"}',
        )
        assert entry.llm_prompt == "What should actor-1 do?"
        assert entry.llm_output == '{"action_type": "email_send"}'

    def test_entry_serialization_roundtrip(self) -> None:
        """ReplayEntry serializes to JSON and deserializes back identically."""
        entry = _make_entry(
            llm_prompt="test prompt",
            llm_output="test output",
            pipeline_result_event_id="evt-001",
            actor_state_after={"frustration": 0.5, "urgency": 0.8},
        )
        json_str = entry.model_dump_json()
        restored = ReplayEntry.model_validate_json(json_str)
        assert restored == entry

    def test_entry_is_frozen(self) -> None:
        """ReplayEntry is immutable."""
        entry = _make_entry()
        try:
            entry.logical_time = 2.0  # type: ignore[misc]
            assert False, "Should have raised"
        except (AttributeError, TypeError, ValueError):
            pass


class TestReplayLog:
    """Tests for the ReplayLog record/replay functionality."""

    async def test_record_entry(self) -> None:
        """record() appends entries to the in-memory list."""
        log = ReplayLog()
        entry = _make_entry()
        await log.record(entry)
        assert len(log.get_entries()) == 1
        assert log.get_entries()[0] == entry

    async def test_record_multiple(self) -> None:
        """Multiple entries are recorded in order."""
        log = ReplayLog()
        e1 = _make_entry(logical_time=1.0, actor_id="a1")
        e2 = _make_entry(logical_time=2.0, actor_id="a2")
        await log.record(e1)
        await log.record(e2)
        entries = log.get_entries()
        assert len(entries) == 2
        assert entries[0].logical_time == 1.0
        assert entries[1].logical_time == 2.0

    def test_replay_mode_off_by_default(self) -> None:
        """ReplayLog starts in recording mode (replay_mode is False)."""
        log = ReplayLog()
        assert log.replay_mode() is False

    def test_enable_replay(self) -> None:
        """enable_replay switches to replay mode and indexes entries."""
        log = ReplayLog()
        entries = [
            _make_entry(logical_time=1.0, actor_id="a1", llm_output="output1"),
            _make_entry(logical_time=2.0, actor_id="a2", llm_output="output2"),
        ]
        log.enable_replay(entries)
        assert log.replay_mode() is True
        assert len(log.get_entries()) == 2

    async def test_get_recorded_output(self) -> None:
        """get_recorded_output returns LLM output for matching time/actor."""
        log = ReplayLog()
        entries = [
            _make_entry(logical_time=1.0, actor_id="a1", llm_output="do_email"),
            _make_entry(logical_time=2.0, actor_id="a2", llm_output="do_chat"),
        ]
        log.enable_replay(entries)

        result = await log.get_recorded_output(1.0, "a1")
        assert result == "do_email"

        result = await log.get_recorded_output(2.0, "a2")
        assert result == "do_chat"

    async def test_get_recorded_output_missing(self) -> None:
        """get_recorded_output returns None for unrecorded time/actor combo."""
        log = ReplayLog()
        log.enable_replay([])
        result = await log.get_recorded_output(99.0, "nonexistent")
        assert result is None

    async def test_record_to_file(self, tmp_path: Path) -> None:
        """record() writes JSON lines to file when path is set."""
        filepath = tmp_path / "replay.jsonl"
        log = ReplayLog(path=filepath)

        e1 = _make_entry(logical_time=1.0, actor_id="a1")
        e2 = _make_entry(logical_time=2.0, actor_id="a2")
        await log.record(e1)
        await log.record(e2)

        # Verify file was written
        assert filepath.exists()
        lines = filepath.read_text().strip().split("\n")
        assert len(lines) == 2

        # Verify JSON roundtrip from file
        restored = ReplayEntry.model_validate_json(lines[0])
        assert restored.actor_id == "a1"

    def test_clear(self) -> None:
        """clear() removes all entries and resets replay mode."""
        log = ReplayLog()
        entries = [_make_entry(llm_output="out")]
        log.enable_replay(entries)
        assert log.replay_mode() is True
        assert len(log.get_entries()) == 1

        log.clear()
        assert log.replay_mode() is False
        assert len(log.get_entries()) == 0

    def test_get_entries_returns_copy(self) -> None:
        """get_entries() returns a copy, not a reference to the internal list."""
        log = ReplayLog()
        entries = log.get_entries()
        assert entries == []
        # Mutating the returned list should not affect the log
        entries.append(_make_entry())
        assert len(log.get_entries()) == 0

    async def test_enable_replay_skips_none_llm_output(self) -> None:
        """enable_replay only indexes entries that have non-None llm_output."""
        log = ReplayLog()
        entries = [
            _make_entry(logical_time=1.0, actor_id="a1", llm_output=None),
            _make_entry(logical_time=2.0, actor_id="a2", llm_output="output2"),
        ]
        log.enable_replay(entries)

        result = await log.get_recorded_output(1.0, "a1")
        assert result is None  # was None, not indexed

        result = await log.get_recorded_output(2.0, "a2")
        assert result == "output2"
