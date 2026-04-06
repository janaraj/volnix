"""Tests for PackCompiler -- generate Tier 1 pack scaffold from profile."""

from __future__ import annotations

from pathlib import Path

from volnix.engines.feedback.pack_compiler import PackCompiler


async def test_compile_generates_files(make_profile, tmp_path):
    """Compile creates the standard 5-file pack structure."""
    profile = make_profile(service_name="twilio")
    compiler = PackCompiler()
    result = await compiler.compile(profile, output_dir=tmp_path)

    assert result.service_name == "twilio"
    assert len(result.files_generated) == 5

    pack_dir = Path(result.output_dir)
    assert (pack_dir / "__init__.py").exists()
    assert (pack_dir / "pack.py").exists()
    assert (pack_dir / "schemas.py").exists()
    assert (pack_dir / "handlers.py").exists()
    assert (pack_dir / "state_machines.py").exists()


async def test_compile_handlers_match_operations(make_profile, tmp_path):
    """Each operation in the profile gets a handler stub."""
    profile = make_profile(service_name="twilio")
    compiler = PackCompiler()
    result = await compiler.compile(profile, output_dir=tmp_path)

    assert result.handler_stubs == len(profile.operations)

    handlers_content = (Path(result.output_dir) / "handlers.py").read_text()
    for op in profile.operations:
        assert f"handle_{op.name}" in handlers_content


async def test_compile_schemas_from_entities(make_profile, tmp_path):
    """Entity schemas appear in schemas.py."""
    profile = make_profile(service_name="twilio")
    compiler = PackCompiler()
    result = await compiler.compile(profile, output_dir=tmp_path)

    schemas_content = (Path(result.output_dir) / "schemas.py").read_text()
    assert "MESSAGE_ENTITY_SCHEMA" in schemas_content
    assert '"sid"' in schemas_content


async def test_compile_empty_operations(make_profile, tmp_path):
    """M6 fix: empty operations list generates valid Python."""
    profile = make_profile(service_name="empty", operations=[])
    compiler = PackCompiler()
    result = await compiler.compile(profile, output_dir=tmp_path)

    pack_content = (Path(result.output_dir) / "pack.py").read_text()
    # Should not have trailing dangling import
    assert "from .handlers import ," not in pack_content
    # Should be valid Python
    compile(pack_content, "pack.py", "exec")
