"""Tests for TierPromoter -- fidelity tier promotion evaluation and execution."""

from __future__ import annotations

from volnix.engines.feedback.promotion import TierPromoter
from volnix.packs.profile_loader import ProfileLoader


async def test_evaluate_eligible(
    annotation_store, mock_profile_registry, feedback_config, make_captured_surface
):
    """Service meeting all criteria is eligible for promotion."""
    # Add required annotation
    await annotation_store.add("twilio", "Messages validated", "user")

    promoter = TierPromoter(
        annotation_store=annotation_store,
        profile_registry=mock_profile_registry,
        profile_loader=None,
        config=feedback_config,
    )

    captured = make_captured_surface()
    result = await promoter.evaluate_candidate("twilio", captured)

    assert result.eligible is True
    assert result.proposed_fidelity == "curated_profile"
    assert len(result.criteria_met) >= 3
    assert len(result.criteria_missing) == 0


async def test_evaluate_not_eligible_no_annotations(
    annotation_store, mock_profile_registry, feedback_config, make_captured_surface
):
    """Service without annotations is NOT eligible."""
    promoter = TierPromoter(
        annotation_store=annotation_store,
        profile_registry=mock_profile_registry,
        profile_loader=None,
        config=feedback_config,
    )

    captured = make_captured_surface()
    result = await promoter.evaluate_candidate("twilio", captured)

    assert result.eligible is False
    assert any("Annotations" in m for m in result.criteria_missing)


async def test_evaluate_not_eligible_few_operations(
    annotation_store, mock_profile_registry, feedback_config, make_captured_surface
):
    """Service with < 3 operations is NOT eligible."""
    await annotation_store.add("twilio", "Reviewed", "user")

    from volnix.engines.feedback.models import ObservedOperation

    captured = make_captured_surface(
        operations=[
            ObservedOperation(
                name="twilio_send",
                call_count=1,
                parameter_keys=[],
                response_keys=[],
            ),
        ]
    )

    promoter = TierPromoter(
        annotation_store=annotation_store,
        profile_registry=mock_profile_registry,
        profile_loader=None,
        config=feedback_config,
    )

    result = await promoter.evaluate_candidate("twilio", captured)
    assert result.eligible is False
    assert any("Operations" in m for m in result.criteria_missing)


async def test_promote_updates_fidelity(
    annotation_store, mock_profile_registry, make_profile, tmp_path
):
    """Promote changes fidelity_source and saves to disk."""
    loader = ProfileLoader(tmp_path / "profiles")
    promoter = TierPromoter(
        annotation_store=annotation_store,
        profile_registry=mock_profile_registry,
        profile_loader=loader,
    )

    profile = make_profile(fidelity_source="bootstrapped", version="0.1.0")
    result = await promoter.promote("twilio", profile)

    assert result.new_fidelity == "curated_profile"
    assert result.previous_fidelity == "bootstrapped"
    assert result.version == "1.0.0"  # 0.x → 1.0.0

    # Verify saved to disk
    reloaded = loader.load("twilio")
    assert reloaded is not None
    assert reloaded.fidelity_source == "curated_profile"
    assert reloaded.version == "1.0.0"


async def test_get_promotion_candidates(annotation_store, mock_profile_registry, make_profile):
    """Lists bootstrapped services as promotion candidates."""
    # Register a bootstrapped profile
    profile = make_profile(service_name="twilio", fidelity_source="bootstrapped")
    mock_profile_registry.register(profile)

    # Register a curated profile (should NOT appear)
    curated = make_profile(service_name="jira", fidelity_source="curated_profile")
    mock_profile_registry.register(curated)

    # Add annotation for twilio
    await annotation_store.add("twilio", "Reviewed", "user")

    promoter = TierPromoter(
        annotation_store=annotation_store,
        profile_registry=mock_profile_registry,
        profile_loader=None,
    )

    candidates = await promoter.get_promotion_candidates()
    assert len(candidates) == 1
    assert candidates[0]["service_name"] == "twilio"
    assert candidates[0]["annotation_count"] == 1


async def test_evaluate_high_error_rate(
    annotation_store,
    mock_profile_registry,
    feedback_config,
    make_captured_surface,
):
    """M7: Service with high error rate is NOT eligible."""
    await annotation_store.add("twilio", "Reviewed", "user")

    from volnix.engines.feedback.models import ObservedOperation

    captured = make_captured_surface(
        operations=[
            ObservedOperation(
                name="twilio_send",
                call_count=10,
                parameter_keys=["to"],
                response_keys=["sid"],
                error_count=8,  # 8/10 = 80% error rate on this op
            ),
            ObservedOperation(
                name="twilio_list",
                call_count=5,
                parameter_keys=[],
                response_keys=["msgs"],
                error_count=3,  # total: 11/20 = 55% > 30%
            ),
            ObservedOperation(
                name="twilio_get",
                call_count=5,
                parameter_keys=["sid"],
                response_keys=["body"],
            ),
        ]
    )

    promoter = TierPromoter(
        annotation_store=annotation_store,
        profile_registry=mock_profile_registry,
        profile_loader=None,
        config=feedback_config,
    )

    result = await promoter.evaluate_candidate("twilio", captured)
    assert result.eligible is False
    assert any("Error rate" in m for m in result.criteria_missing)


def test_increment_version_0x():
    """M8: 0.x.x promotes to 1.0.0."""
    assert TierPromoter._increment_version("0.1.0") == "1.0.0"
    assert TierPromoter._increment_version("0.99.5") == "1.0.0"


def test_increment_version_1x():
    """M8: 1.x.x increments minor."""
    assert TierPromoter._increment_version("1.2.3") == "1.3.0"
    assert TierPromoter._increment_version("1.99.99") == "1.100.0"


def test_increment_version_malformed():
    """M8: Malformed versions fall back to 1.0.0."""
    assert TierPromoter._increment_version("bad") == "1.0.0"
    assert TierPromoter._increment_version("1.2") == "1.0.0"
    assert TierPromoter._increment_version("a.b.c") == "1.0.0"
