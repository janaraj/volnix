"""Tests for volnix.kernel.categories -- category definitions and metadata."""

import pytest
from pydantic import ValidationError

from volnix.kernel.categories import CATEGORIES

EXPECTED_CATEGORY_NAMES = {
    "communication",
    "work_management",
    "money_transactions",
    "authority_approvals",
    "identity_auth",
    "storage_documents",
    "code_devops",
    "scheduling",
    "monitoring_observability",
    "social_media",
    "trading",
}


def test_all_categories():
    """CATEGORIES dict has exactly 11 entries."""
    assert len(CATEGORIES) == 11


def test_category_names():
    """All expected category names are present and nothing extra."""
    assert set(CATEGORIES.keys()) == EXPECTED_CATEGORY_NAMES


def test_category_has_primitives():
    """Every category defines a non-empty primitives list."""
    for name, cat in CATEGORIES.items():
        assert isinstance(cat.primitives, list), f"{name} primitives is not a list"
        assert len(cat.primitives) > 0, f"{name} has no primitives"


def test_category_has_examples():
    """Every category has at least one example service."""
    for name, cat in CATEGORIES.items():
        assert isinstance(cat.example_services, list), f"{name} example_services not a list"
        assert len(cat.example_services) > 0, f"{name} has no example_services"


def test_category_frozen():
    """SemanticCategory is frozen -- instances are immutable."""
    cat = CATEGORIES["communication"]
    with pytest.raises(ValidationError):
        cat.name = "hacked"
