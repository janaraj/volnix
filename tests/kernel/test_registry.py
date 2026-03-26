"""Tests for terrarium.kernel.registry -- SemanticRegistry async initialization and lookups."""

import pytest
from terrarium.kernel.registry import SemanticRegistry


@pytest.fixture
async def registry():
    """Create and initialize a SemanticRegistry."""
    reg = SemanticRegistry()
    await reg.initialize()
    return reg


async def test_initialize(registry):
    """Registry loads 9 categories and all services from TOML."""
    cats = registry.list_categories()
    svcs = registry.list_services()
    assert len(cats) == 10
    assert len(svcs) >= 33  # services.toml has at least 33 services


async def test_get_category_stripe(registry):
    """stripe maps to money_transactions."""
    assert registry.get_category("stripe") == "money_transactions"


async def test_get_category_slack(registry):
    """slack maps to communication."""
    assert registry.get_category("slack") == "communication"


async def test_get_category_unknown(registry):
    """Nonexistent service returns None."""
    assert registry.get_category("nonexistent") is None


async def test_get_category_case_insensitive(registry):
    """Service lookup is case-insensitive."""
    assert registry.get_category("Stripe") == "money_transactions"
    assert registry.get_category("SLACK") == "communication"


async def test_get_primitives(registry):
    """get_primitives returns 5 primitive dicts for money_transactions."""
    prims = registry.get_primitives("money_transactions")
    assert len(prims) == 5
    names = [p["name"] for p in prims]
    assert "transaction" in names
    assert "balance" in names


async def test_get_primitives_unknown(registry):
    """Unknown category returns empty list."""
    prims = registry.get_primitives("nonexistent")
    assert prims == []


async def test_get_service_mapping(registry):
    """get_service_mapping returns full metadata dict."""
    mapping = registry.get_service_mapping("stripe")
    assert mapping is not None
    assert mapping["service"] == "stripe"
    assert mapping["category"] == "money_transactions"
    assert "category_description" in mapping
    assert "primitives" in mapping
    assert "transaction" in mapping["primitives"]


async def test_list_categories(registry):
    """list_categories returns 9 sorted names."""
    cats = registry.list_categories()
    assert len(cats) == 10
    assert cats == sorted(cats)
    assert "communication" in cats
    assert "money_transactions" in cats


async def test_list_all_services(registry):
    """list_services with no filter returns all services."""
    svcs = registry.list_services()
    assert len(svcs) >= 33
    assert "stripe" in svcs
    assert "slack" in svcs
    assert "github" in svcs


async def test_list_by_category(registry):
    """list_services filtered by category returns correct subset."""
    svcs = registry.list_services(category="money_transactions")
    assert "stripe" in svcs
    assert "paypal" in svcs
    # Should not include services from other categories
    assert "slack" not in svcs
    assert "github" not in svcs


async def test_register_service(registry):
    """Dynamically registered service becomes queryable."""
    registry.register_service("my_payment_app", "money_transactions")
    assert registry.get_category("my_payment_app") == "money_transactions"
    assert "my_payment_app" in registry.list_services()
    assert "my_payment_app" in registry.list_services(category="money_transactions")


async def test_register_unknown_category(registry):
    """Registering a service with unknown category raises ValueError."""
    with pytest.raises(ValueError, match="Unknown category"):
        registry.register_service("bad_service", "nonexistent_category")


async def test_has_service_and_category(registry):
    """has_service and has_category return correct booleans."""
    assert registry.has_service("stripe") is True
    assert registry.has_service("nonexistent") is False
    assert registry.has_category("communication") is True
    assert registry.has_category("nonexistent") is False
