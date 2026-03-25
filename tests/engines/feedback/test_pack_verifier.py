"""Tests for PackVerifier -- validate Tier 1 pack structure."""
from __future__ import annotations

from terrarium.engines.feedback.pack_compiler import PackCompiler
from terrarium.engines.feedback.pack_verifier import PackVerifier


async def test_verify_compiled_pack(make_profile, tmp_path):
    """A freshly compiled pack should pass structure + handler checks."""
    profile = make_profile(service_name="twilio")
    compiler = PackCompiler()
    result = await compiler.compile(profile, output_dir=tmp_path)

    verifier = PackVerifier()
    verification = await verifier.verify(result.output_dir)

    assert verification.service_name == "twilio"
    structure_check = next(
        c for c in verification.checks if c.name == "structure"
    )
    assert structure_check.passed is True
    handler_check = next(
        c for c in verification.checks if c.name == "handlers"
    )
    assert handler_check.passed is True
    # Tools and entities should now be real checks (M4 fix)
    tools_check = next(
        c for c in verification.checks if c.name == "tools"
    )
    assert tools_check.passed is True
    entities_check = next(
        c for c in verification.checks if c.name == "entities"
    )
    assert entities_check.passed is True


async def test_verify_missing_files(tmp_path):
    """Pack with missing files fails structure check."""
    pack_dir = tmp_path / "broken_pack"
    pack_dir.mkdir()
    (pack_dir / "pack.py").write_text("# incomplete")

    verifier = PackVerifier()
    result = await verifier.verify(pack_dir)

    assert result.passed is False
    assert any("Missing files" in e for e in result.errors)


async def test_verify_stub_handlers_warn(make_profile, tmp_path):
    """Compiled pack with NotImplementedError stubs produces warnings."""
    profile = make_profile(service_name="twilio")
    compiler = PackCompiler()
    compiled = await compiler.compile(profile, output_dir=tmp_path)

    verifier = PackVerifier()
    result = await verifier.verify(compiled.output_dir)

    # Stubs are warnings, not errors (M12 fix: AST-based detection)
    stub_check = next(
        c for c in result.checks if c.name == "no_stubs"
    )
    assert stub_check.passed is False
    assert any("NotImplementedError" in w for w in result.warnings)


async def test_verify_existing_email_pack():
    """Verify the real email pack passes all checks."""
    from pathlib import Path

    pack_dir = (
        Path(__file__).resolve().parents[3]
        / "terrarium"
        / "packs"
        / "verified"
        / "email"
    )
    if not pack_dir.exists():
        return  # Skip if not available

    verifier = PackVerifier()
    result = await verifier.verify(pack_dir)

    assert result.passed is True
    assert len(result.errors) == 0
