"""Tests for volnix.ledger.export -- JSON, CSV, and replay export."""

import json

import pytest

from volnix.core.types import ActorId
from volnix.ledger.config import LedgerConfig
from volnix.ledger.entries import (
    LLMCallEntry,
    PipelineStepEntry,
)
from volnix.ledger.export import LedgerExporter
from volnix.ledger.ledger import Ledger
from volnix.ledger.query import LedgerQuery
from volnix.persistence.sqlite import SQLiteDatabase


@pytest.fixture
async def db(tmp_path):
    """Create a temporary SQLite database."""
    database = SQLiteDatabase(str(tmp_path / "export_test.db"))
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
async def ledger(db):
    """Create and initialize a Ledger."""
    config = LedgerConfig()
    led = Ledger(config, db)
    await led.initialize()
    return led


@pytest.fixture
def exporter(ledger):
    """Create a LedgerExporter wrapping the ledger."""
    return LedgerExporter(ledger)


def _make_pipeline_entry(**kwargs):
    defaults = {
        "step_name": "check",
        "request_id": "r1",
        "actor_id": ActorId("a1"),
        "action": "read",
        "verdict": "allow",
    }
    defaults.update(kwargs)
    return PipelineStepEntry(**defaults)


def _make_llm_entry(**kwargs):
    defaults = {
        "provider": "openai",
        "model": "gpt-4",
        "engine_name": "reasoning",
    }
    defaults.update(kwargs)
    return LLMCallEntry(**defaults)


async def test_export_json(ledger, exporter, tmp_path):
    """export_json should write entries to a JSON file."""
    await ledger.append(_make_pipeline_entry())
    await ledger.append(_make_pipeline_entry(step_name="step2"))

    output = str(tmp_path / "out.json")
    count = await exporter.export_json(LedgerQuery(), output)
    assert count == 2

    data = json.loads(open(output).read())
    assert len(data) == 2
    assert data[0]["entry_type"] == "pipeline_step"


async def test_export_json_empty(exporter, tmp_path):
    """export_json with no entries should write an empty list."""
    output = str(tmp_path / "empty.json")
    count = await exporter.export_json(LedgerQuery(), output)
    assert count == 0

    data = json.loads(open(output).read())
    assert data == []


async def test_export_csv(ledger, exporter, tmp_path):
    """export_csv should write entries as CSV rows."""
    await ledger.append(_make_pipeline_entry())
    await ledger.append(_make_pipeline_entry(step_name="step2"))

    output = str(tmp_path / "out.csv")
    count = await exporter.export_csv(LedgerQuery(), output)
    assert count == 2

    lines = open(output).readlines()
    assert len(lines) == 3  # header + 2 data rows
    assert "entry_type" in lines[0]


async def test_export_csv_empty(ledger, exporter, tmp_path):
    """export_csv with no entries should produce an empty file."""
    output = str(tmp_path / "empty.csv")
    count = await exporter.export_csv(LedgerQuery(), output)
    assert count == 0

    content = open(output).read()
    assert content == ""


async def test_export_replay(ledger, exporter, tmp_path):
    """export_replay should write one JSON line per entry."""
    await ledger.append(_make_pipeline_entry())
    await ledger.append(_make_llm_entry())

    output = str(tmp_path / "replay.jsonl")
    count = await exporter.export_replay(LedgerQuery(), output)
    assert count == 2

    lines = open(output).readlines()
    assert len(lines) == 2


async def test_export_replay_parseable(ledger, exporter, tmp_path):
    """Each line from export_replay should be valid JSON."""
    await ledger.append(_make_pipeline_entry())
    await ledger.append(_make_llm_entry())

    output = str(tmp_path / "replay2.jsonl")
    await exporter.export_replay(LedgerQuery(), output)

    for line in open(output).readlines():
        parsed = json.loads(line.strip())
        assert "entry_type" in parsed


async def test_export_json_with_filter(ledger, exporter, tmp_path):
    """export_json with a type filter should only export matching entries."""
    await ledger.append(_make_pipeline_entry())
    await ledger.append(_make_llm_entry())
    await ledger.append(_make_pipeline_entry(step_name="step2"))

    output = str(tmp_path / "filtered.json")
    count = await exporter.export_json(LedgerQuery(entry_type="pipeline_step"), output)
    assert count == 2

    data = json.loads(open(output).read())
    assert all(d["entry_type"] == "pipeline_step" for d in data)


async def test_export_preserves_entry_types(ledger, exporter, tmp_path):
    """Exported JSON should preserve the concrete entry_type values."""
    await ledger.append(_make_pipeline_entry())
    await ledger.append(_make_llm_entry())

    output = str(tmp_path / "types.json")
    await exporter.export_json(LedgerQuery(), output)

    data = json.loads(open(output).read())
    types = {d["entry_type"] for d in data}
    assert types == {"pipeline_step", "llm_call"}
