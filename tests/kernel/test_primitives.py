"""Tests for terrarium.kernel.primitives -- per-category primitive definitions."""

import pytest
from terrarium.kernel.primitives import SemanticPrimitive, get_primitives_for_category


def test_total_count():
    """There are 45 total primitives (9 categories x 5 each)."""
    from terrarium.kernel.categories import CATEGORIES

    total = 0
    for cat_name in CATEGORIES:
        prims = get_primitives_for_category(cat_name)
        total += len(prims)
    assert total == 45


def test_communication_primitives():
    """Communication category has the 5 canonical primitives."""
    prims = get_primitives_for_category("communication")
    names = [p.name for p in prims]
    assert names == ["channel", "thread", "message", "delivery", "visibility_rule"]


def test_money_primitives():
    """Money transactions category has the 5 canonical primitives."""
    prims = get_primitives_for_category("money_transactions")
    names = [p.name for p in prims]
    assert names == ["transaction", "authorization", "settlement", "reversal", "balance"]


def test_work_management_primitives():
    """Work management category has the 5 canonical primitives."""
    prims = get_primitives_for_category("work_management")
    names = [p.name for p in prims]
    assert names == ["work_item", "lifecycle", "assignment", "sla", "escalation"]


def test_get_for_category():
    """get_primitives_for_category returns correct list of SemanticPrimitive."""
    prims = get_primitives_for_category("identity_auth")
    assert len(prims) == 5
    for p in prims:
        assert isinstance(p, SemanticPrimitive)
        assert p.category == "identity_auth"


def test_unknown_category():
    """Unknown category returns empty list, not an error."""
    prims = get_primitives_for_category("nonexistent_category")
    assert prims == []
