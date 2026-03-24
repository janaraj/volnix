"""Architecture guards for world compiler validation boundaries."""

from __future__ import annotations

import pytest

from tests.architecture.helpers import PRODUCT_ROOT

pytestmark = pytest.mark.architecture


def _read(path: str) -> str:
    return (PRODUCT_ROOT / path).read_text()


def test_data_generator_does_not_reintroduce_random_repair_logic():
    source = _read("engines/world_compiler/data_generator.py")
    assert "import random" not in source
    assert "_cross_link" not in source


def test_engine_snapshots_only_after_final_validation():
    source = _read("engines/world_compiler/engine.py")
    start = source.index("async def generate_world")
    end = source.index("async def _generate_validated_entity_section")
    body = source[start:end]
    assert body.rfind("validate_world(") < body.rfind('snapshot("initial_world")')


def test_compiler_validation_does_not_infer_refs_or_temporal_fields_from_names():
    guarded_paths = [
        PRODUCT_ROOT / "engines/world_compiler/engine.py",
        PRODUCT_ROOT / "engines/world_compiler/validator.py",
        PRODUCT_ROOT / "validation/schema_contracts.py",
    ]
    for path in guarded_paths:
        source = path.read_text()
        assert 'endswith("_id")' not in source
        assert "created_at" not in source
        assert "updated_at" not in source
