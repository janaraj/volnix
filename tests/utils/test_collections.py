"""Tests for volnix.utils.collections."""

from volnix.utils.collections import dedup_entity_collection, dedup_entity_dicts


class TestDedupEntityDicts:
    """Tests for dedup_entity_dicts."""

    def test_no_duplicates_passthrough(self):
        entities = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]
        result = dedup_entity_dicts(entities)
        assert result == entities

    def test_empty_list(self):
        assert dedup_entity_dicts([]) == []

    def test_last_wins_default(self):
        entities = [
            {"id": "a", "name": "first"},
            {"id": "b", "name": "B"},
            {"id": "a", "name": "second"},
        ]
        result = dedup_entity_dicts(entities)
        assert len(result) == 2
        assert result[0]["name"] == "second"
        assert result[1]["name"] == "B"

    def test_first_wins(self):
        entities = [
            {"id": "a", "name": "first"},
            {"id": "a", "name": "second"},
        ]
        result = dedup_entity_dicts(entities, strategy="first_wins")
        assert len(result) == 1
        assert result[0]["name"] == "first"

    def test_custom_key(self):
        entities = [
            {"email": "x@y.com", "name": "first"},
            {"email": "x@y.com", "name": "second"},
        ]
        result = dedup_entity_dicts(entities, key="email")
        assert len(result) == 1
        assert result[0]["name"] == "second"

    def test_missing_key_preserved(self):
        entities = [
            {"id": "a", "name": "A"},
            {"name": "no-id"},
            {"id": "a", "name": "A2"},
        ]
        result = dedup_entity_dicts(entities)
        assert len(result) == 2
        assert result[0]["name"] == "A2"
        assert result[1]["name"] == "no-id"

    def test_preserves_order(self):
        entities = [
            {"id": "c"},
            {"id": "a"},
            {"id": "b"},
        ]
        result = dedup_entity_dicts(entities)
        assert [e["id"] for e in result] == ["c", "a", "b"]

    def test_numeric_id_coerced_to_string(self):
        entities = [{"id": 1, "v": "first"}, {"id": 1, "v": "second"}]
        result = dedup_entity_dicts(entities)
        assert len(result) == 1
        assert result[0]["v"] == "second"

    def test_multiple_duplicates(self):
        entities = [
            {"id": "a", "v": 1},
            {"id": "b", "v": 2},
            {"id": "a", "v": 3},
            {"id": "b", "v": 4},
            {"id": "a", "v": 5},
        ]
        result = dedup_entity_dicts(entities)
        assert len(result) == 2
        assert result[0]["v"] == 5
        assert result[1]["v"] == 4


class TestDedupEntityCollection:
    """Tests for dedup_entity_collection."""

    def test_dedup_across_types(self):
        collection = {
            "channel": [
                {"id": "C1", "name": "general"},
                {"id": "C1", "name": "general-updated"},
            ],
            "message": [
                {"id": "M1"},
                {"id": "M2"},
            ],
        }
        result = dedup_entity_collection(collection)
        assert len(result["channel"]) == 1
        assert result["channel"][0]["name"] == "general-updated"
        assert len(result["message"]) == 2

    def test_empty_collection(self):
        assert dedup_entity_collection({}) == {}

    def test_no_duplicates_passthrough(self):
        collection = {
            "user": [{"id": "U1"}, {"id": "U2"}],
        }
        result = dedup_entity_collection(collection)
        assert result == collection

    def test_custom_key_propagated(self):
        collection = {
            "item": [
                {"sku": "ABC", "v": 1},
                {"sku": "ABC", "v": 2},
            ],
        }
        result = dedup_entity_collection(collection, key="sku")
        assert len(result["item"]) == 1
        assert result["item"][0]["v"] == 2
