"""Tests for volnix.kernel.registry -- SemanticRegistry async initialization and lookups."""

import pytest

from volnix.kernel.registry import SemanticRegistry


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
    assert len(cats) == 11
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
    assert len(cats) == 11
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


class TestKernelPackAutoSync:
    """Tests for auto-sync of discovered packs into the kernel.

    Simulates the app.py startup logic that registers pack categories
    into the kernel so adding a new verified pack doesn't require
    manually editing services.toml.
    """

    async def test_pack_auto_registers_into_kernel(self, registry):
        """A pack with a valid category is auto-registered if not already present."""
        # Simulate a new pack not in services.toml
        assert not registry.has_service("acme_crm")

        # Simulate the auto-sync logic from app.py
        pack_list = [{"pack_name": "acme_crm", "category": "money_transactions"}]
        for pack_info in pack_list:
            svc = pack_info["pack_name"]
            cat = pack_info["category"]
            if cat and registry.has_category(cat) and not registry.has_service(svc):
                registry.register_service(svc, cat)

        # Now kernel knows about acme_crm
        assert registry.has_service("acme_crm")
        assert registry.get_category("acme_crm") == "money_transactions"

    async def test_existing_service_not_overwritten(self, registry):
        """A pack that's already in services.toml is not re-registered."""
        # stripe is already in services.toml as money_transactions
        assert registry.get_category("stripe") == "money_transactions"

        # Simulate auto-sync — should skip because already present
        pack_list = [{"pack_name": "stripe", "category": "communication"}]
        for pack_info in pack_list:
            svc = pack_info["pack_name"]
            cat = pack_info["category"]
            if cat and registry.has_category(cat) and not registry.has_service(svc):
                registry.register_service(svc, cat)

        # stripe still maps to money_transactions (not overwritten to communication)
        assert registry.get_category("stripe") == "money_transactions"

    async def test_pack_with_invalid_category_skipped(self, registry):
        """A pack declaring a non-existent category is silently skipped."""
        pack_list = [{"pack_name": "mystery_svc", "category": "nonexistent_category"}]
        for pack_info in pack_list:
            svc = pack_info["pack_name"]
            cat = pack_info["category"]
            if cat and registry.has_category(cat) and not registry.has_service(svc):
                registry.register_service(svc, cat)

        assert not registry.has_service("mystery_svc")

    async def test_pack_with_empty_category_skipped(self, registry):
        """A pack with empty category string is skipped."""
        pack_list = [{"pack_name": "no_cat_svc", "category": ""}]
        for pack_info in pack_list:
            svc = pack_info["pack_name"]
            cat = pack_info["category"]
            if cat and registry.has_category(cat) and not registry.has_service(svc):
                registry.register_service(svc, cat)

        assert not registry.has_service("no_cat_svc")

    async def test_multiple_packs_auto_registered(self, registry):
        """Multiple new packs are all registered in one pass."""
        pack_list = [
            {"pack_name": "acme_crm", "category": "money_transactions"},
            {"pack_name": "acme_tasks", "category": "work_management"},
            {"pack_name": "telegram", "category": "communication"},
        ]
        for pack_info in pack_list:
            svc = pack_info["pack_name"]
            cat = pack_info["category"]
            if cat and registry.has_category(cat) and not registry.has_service(svc):
                registry.register_service(svc, cat)

        assert registry.get_category("acme_crm") == "money_transactions"
        assert registry.get_category("acme_tasks") == "work_management"
        assert registry.get_category("telegram") == "communication"
