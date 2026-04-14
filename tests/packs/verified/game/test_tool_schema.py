"""Tests for the dynamic negotiation tool schema builder (NF1).

The builder takes a list of :class:`NegotiationField` and returns 4
raw action dicts for the game tool pack. When the list is empty it
returns the static fallback (``deal_id`` + ``message``); otherwise
it builds typed required parameters for propose/counter.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from volnix.engines.game.definition import NegotiationField
from volnix.packs.verified.game.tool_schema import build_negotiation_tools

# ---------------------------------------------------------------------------
# Static fallback (empty fields list)
# ---------------------------------------------------------------------------


class TestStaticFallback:
    def test_empty_fields_returns_static_fallback(self):
        tools = build_negotiation_tools([])
        assert len(tools) == 4
        names = {t["name"] for t in tools}
        assert names == {
            "negotiate_propose",
            "negotiate_counter",
            "negotiate_accept",
            "negotiate_reject",
        }
        for t in tools:
            props = t["parameters"]["properties"]
            assert set(props.keys()) == {"deal_id", "message"}
            assert t["parameters"]["required"] == ["deal_id"]

    def test_static_fallback_is_independent_copy(self):
        """Caller mutation must not leak into module-level cached state."""
        tools_a = build_negotiation_tools([])
        tools_a[0]["name"] = "mutated"
        tools_b = build_negotiation_tools([])
        assert tools_b[0]["name"] == "negotiate_propose"

    def test_static_fallback_service_is_game(self):
        for t in build_negotiation_tools([]):
            assert t["service"] == "game"

    def test_static_fallback_uses_additional_properties_true(self):
        """Pre-NF1 behavior: LLM can send arbitrary extra keys as 'terms'."""
        tools = build_negotiation_tools([])
        for t in tools:
            assert t["parameters"]["additionalProperties"] is True


# ---------------------------------------------------------------------------
# Typed build (non-empty fields)
# ---------------------------------------------------------------------------


def _q3_steel_fields() -> list[NegotiationField]:
    """The four Q3 Steel negotiation fields for reuse across tests."""
    return [
        NegotiationField(name="price", type="number", description="USD per ton"),
        NegotiationField(name="delivery_weeks", type="integer", description="weeks"),
        NegotiationField(name="payment_days", type="integer", description="NET days"),
        NegotiationField(name="warranty_months", type="integer", description="months"),
    ]


class TestTypedBuild:
    def test_all_four_tools_returned(self):
        tools = build_negotiation_tools(_q3_steel_fields())
        names = [t["name"] for t in tools]
        assert names == [
            "negotiate_propose",
            "negotiate_counter",
            "negotiate_accept",
            "negotiate_reject",
        ]

    def test_single_field_produces_typed_parameter(self):
        tools = build_negotiation_tools(
            [NegotiationField(name="price", type="number", description="x")]
        )
        propose = next(t for t in tools if t["name"] == "negotiate_propose")
        props = propose["parameters"]["properties"]
        assert props["price"]["type"] == "number"
        assert props["price"]["description"] == "x"

    def test_required_fields_include_all_declared(self):
        tools = build_negotiation_tools(_q3_steel_fields())
        propose = next(t for t in tools if t["name"] == "negotiate_propose")
        required = set(propose["parameters"]["required"])
        assert required == {
            "deal_id",
            "price",
            "delivery_weeks",
            "payment_days",
            "warranty_months",
        }

    def test_counter_has_same_required_as_propose(self):
        tools = build_negotiation_tools(_q3_steel_fields())
        propose = next(t for t in tools if t["name"] == "negotiate_propose")
        counter = next(t for t in tools if t["name"] == "negotiate_counter")
        assert set(propose["parameters"]["required"]) == set(counter["parameters"]["required"])

    def test_accept_reject_do_not_include_field_params(self):
        tools = build_negotiation_tools(_q3_steel_fields())
        for tname in ("negotiate_accept", "negotiate_reject"):
            t = next(t for t in tools if t["name"] == tname)
            props = set(t["parameters"]["properties"].keys())
            assert props == {"deal_id", "message"}
            assert t["parameters"]["required"] == ["deal_id"]

    def test_message_is_optional_on_propose(self):
        tools = build_negotiation_tools(_q3_steel_fields())
        propose = next(t for t in tools if t["name"] == "negotiate_propose")
        assert "message" in propose["parameters"]["properties"]
        assert "message" not in propose["parameters"]["required"]

    def test_description_mentions_declared_fields(self):
        tools = build_negotiation_tools(_q3_steel_fields())
        propose = next(t for t in tools if t["name"] == "negotiate_propose")
        for field_name in ("price", "delivery_weeks", "payment_days", "warranty_months"):
            assert field_name in propose["description"]

    def test_service_is_game_on_all_tools(self):
        for t in build_negotiation_tools(_q3_steel_fields()):
            assert t["service"] == "game"

    def test_typed_propose_uses_additional_properties_false(self):
        """With typed fields, no unknown keys allowed — strict validation."""
        tools = build_negotiation_tools(_q3_steel_fields())
        propose = next(t for t in tools if t["name"] == "negotiate_propose")
        assert propose["parameters"]["additionalProperties"] is False


# ---------------------------------------------------------------------------
# Type mapping
# ---------------------------------------------------------------------------


class TestTypeMapping:
    def _get_field_schema(self, field_type: str):
        tools = build_negotiation_tools(
            [NegotiationField(name="x", type=field_type)]  # type: ignore[arg-type]
        )
        propose = next(t for t in tools if t["name"] == "negotiate_propose")
        return propose["parameters"]["properties"]["x"]

    def test_type_mapping_number(self):
        assert self._get_field_schema("number")["type"] == "number"

    def test_type_mapping_integer(self):
        assert self._get_field_schema("integer")["type"] == "integer"

    def test_type_mapping_string(self):
        assert self._get_field_schema("string")["type"] == "string"

    def test_type_mapping_boolean(self):
        assert self._get_field_schema("boolean")["type"] == "boolean"

    def test_enum_passthrough_for_string_type(self):
        tools = build_negotiation_tools(
            [NegotiationField(name="mode", type="string", enum=["sea", "air", "rail"])]
        )
        propose = next(t for t in tools if t["name"] == "negotiate_propose")
        assert propose["parameters"]["properties"]["mode"]["enum"] == ["sea", "air", "rail"]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestFieldValidation:
    def test_invalid_field_name_with_dot_raises(self):
        with pytest.raises(ValidationError):
            NegotiationField(name="foo.bar", type="number")

    def test_invalid_field_name_with_space_raises(self):
        with pytest.raises(ValidationError):
            NegotiationField(name="foo bar", type="number")

    def test_invalid_field_name_with_hyphen_raises(self):
        with pytest.raises(ValidationError):
            NegotiationField(name="foo-bar", type="number")

    def test_invalid_field_name_starting_with_digit_raises(self):
        with pytest.raises(ValidationError):
            NegotiationField(name="1field", type="number")

    def test_empty_field_name_raises(self):
        with pytest.raises(ValidationError):
            NegotiationField(name="", type="number")

    def test_valid_field_name_with_underscore_ok(self):
        f = NegotiationField(name="delivery_weeks", type="integer")
        assert f.name == "delivery_weeks"

    def test_valid_field_name_starting_with_underscore_ok(self):
        f = NegotiationField(name="_private", type="string")
        assert f.name == "_private"

    def test_invalid_type_raises(self):
        with pytest.raises(ValidationError):
            NegotiationField(name="x", type="decimal")  # type: ignore[arg-type]

    def test_enum_on_non_string_raises(self):
        with pytest.raises(ValidationError):
            NegotiationField(name="x", type="integer", enum=["a", "b"])  # type: ignore[list-item]

    def test_extra_fields_on_negotiation_field_raise(self):
        """extra='forbid' catches typos like 'typ' instead of 'type'."""
        with pytest.raises(ValidationError):
            NegotiationField(name="x", type="number", wrong_key="oops")  # type: ignore[call-arg]


class TestBuilderValidation:
    def test_duplicate_field_names_raise(self):
        fields = [
            NegotiationField(name="price", type="number"),
            NegotiationField(name="price", type="integer"),
        ]
        with pytest.raises(ValueError, match="Duplicate negotiation field"):
            build_negotiation_tools(fields)

    def test_reserved_name_deal_id_raises(self):
        with pytest.raises(ValueError, match="reserved parameter name"):
            build_negotiation_tools([NegotiationField(name="deal_id", type="string")])

    def test_reserved_name_message_raises(self):
        with pytest.raises(ValueError, match="reserved parameter name"):
            build_negotiation_tools([NegotiationField(name="message", type="string")])

    def test_reserved_name_reasoning_raises(self):
        with pytest.raises(ValueError, match="reserved parameter name"):
            build_negotiation_tools([NegotiationField(name="reasoning", type="string")])
