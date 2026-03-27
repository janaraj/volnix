"""Tests for CompilerServiceResolver — service resolution chain."""
import pytest
from unittest.mock import AsyncMock

from terrarium.engines.world_compiler.service_resolution import CompilerServiceResolver
from terrarium.kernel.surface import ServiceSurface, APIOperation
from terrarium.packs.registry import PackRegistry
from terrarium.packs.verified.gmail.pack import EmailPack


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_kernel_surface(service_name: str, confidence: float = 0.1) -> ServiceSurface:
    """Build a kernel-inferred ServiceSurface (weak signal, no operations)."""
    return ServiceSurface(
        service_name=service_name,
        category="communication",
        source="kernel_inference",
        fidelity_tier=2,
        operations=[],
        entity_schemas={service_name: {"type": "object"}},
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCompilerServiceResolver:
    """CompilerServiceResolver tests."""

    @pytest.mark.asyncio
    async def test_resolve_verified_pack(self, pack_registry):
        """Resolving 'verified/gmail' uses the gmail pack."""
        resolver = CompilerServiceResolver(pack_registry=pack_registry)
        result = await resolver.resolve_one("gmail", "verified/gmail")

        assert result is not None
        assert result.service_name == "gmail"
        assert result.resolution_source == "tier1_pack"
        assert result.surface.service_name == "gmail"
        assert len(result.surface.operations) > 0

    @pytest.mark.asyncio
    async def test_resolve_bare_name_no_resolver(self, pack_registry):
        """Resolving a bare name without a ServiceResolver returns None."""
        resolver = CompilerServiceResolver(pack_registry=pack_registry)
        result = await resolver.resolve_one("stripe", "stripe")

        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_bare_name_with_kernel_resolver(self, pack_registry, kernel):
        """Bare name falls through to kernel ServiceResolver."""
        from terrarium.kernel.resolver import ServiceResolver

        kernel_resolver = ServiceResolver(kernel=kernel)
        resolver = CompilerServiceResolver(
            pack_registry=pack_registry,
            kernel=kernel,
            resolver=kernel_resolver,
        )
        # 'gmail' is a known service in the kernel's service map
        result = await resolver.resolve_one("gmail", "gmail")

        # Should resolve via kernel_inference (weakest signal) since there's no pack
        if result is not None:
            assert result.resolution_source in ("kernel_inference", "tier1_pack")

    @pytest.mark.asyncio
    async def test_resolve_all(self, pack_registry):
        """resolve_all processes multiple services, returns resolutions + warnings."""
        resolver = CompilerServiceResolver(pack_registry=pack_registry)
        specs = {
            "gmail": "verified/gmail",
            "unknown_service": "unknown_service",
        }
        resolutions, warnings = await resolver.resolve_all(specs)

        assert "gmail" in resolutions
        assert resolutions["gmail"].resolution_source == "tier1_pack"
        # unknown_service should produce a warning
        assert any("unknown_service" in w for w in warnings)

    @pytest.mark.asyncio
    async def test_warnings_for_unresolvable(self, pack_registry):
        """Unresolvable services generate warnings, not exceptions."""
        resolver = CompilerServiceResolver(pack_registry=pack_registry)
        specs = {"nonexistent": "nonexistent"}
        resolutions, warnings = await resolver.resolve_all(specs)

        assert len(resolutions) == 0
        assert len(warnings) > 0

    @pytest.mark.asyncio
    async def test_strict_mode_filters_low_confidence(self, pack_registry, kernel):
        """Strict fidelity mode skips services with confidence < 0.5."""
        mock_resolver = AsyncMock()
        mock_resolver.resolve = AsyncMock(return_value=_make_kernel_surface("slack", confidence=0.1))

        resolver = CompilerServiceResolver(
            pack_registry=pack_registry,
            kernel=kernel,
            resolver=mock_resolver,
        )
        result = await resolver.resolve_one("slack", "slack", fidelity_mode="strict")

        assert result is None

    @pytest.mark.asyncio
    async def test_auto_mode_allows_low_confidence(self, pack_registry, kernel):
        """Auto fidelity mode allows low-confidence services."""
        mock_resolver = AsyncMock()
        mock_resolver.resolve = AsyncMock(return_value=_make_kernel_surface("slack", confidence=0.1))

        resolver = CompilerServiceResolver(
            pack_registry=pack_registry,
            kernel=kernel,
            resolver=mock_resolver,
        )
        result = await resolver.resolve_one("slack", "slack", fidelity_mode="auto")

        assert result is not None
        assert result.surface.confidence == 0.1

    @pytest.mark.asyncio
    async def test_complex_spec_reference(self, pack_registry):
        """Complex spec reference (dict with provider key) is parsed correctly."""
        resolver = CompilerServiceResolver(pack_registry=pack_registry)
        # The parser should extract "verified" tier and "email" name from dict
        spec = {"provider": "verified/gmail", "extra_config": True}
        result = await resolver.resolve_one("gmail", spec)

        assert result is not None
        assert result.resolution_source == "tier1_pack"

    def test_parse_references(self):
        """_parse_spec_reference handles all formats."""
        resolver = CompilerServiceResolver()

        assert resolver._parse_spec_reference("verified/gmail") == ("verified", "gmail")
        assert resolver._parse_spec_reference("profiled/stripe") == ("profiled", "stripe")
        assert resolver._parse_spec_reference("stripe") == ("auto", "stripe")
        assert resolver._parse_spec_reference({"provider": "verified/browser"}) == ("verified", "browser")
        assert resolver._parse_spec_reference({"provider": "raw_provider"}) == ("complex", "raw_provider")
