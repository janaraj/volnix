"""Convert JSON Schema to Pydantic models — shared across framework adapters.

Volnix tools expose JSON Schema via the MCP tool manifest. Framework
adapters (CrewAI, LangGraph, AutoGen) need Pydantic models for typed
tool arguments. This module bridges the two.

Usage::

    schema = {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]}
    Model = json_schema_to_pydantic("get_bars", schema)
    # Model has: symbol: str (required)
"""

from __future__ import annotations

from typing import Any


def json_schema_to_pydantic(tool_name: str, schema: dict[str, Any]) -> type:
    """Convert a JSON Schema object to a Pydantic model class.

    Handles: string, integer, number, boolean, array types.
    Required fields have no default; optional fields default to None.

    Args:
        tool_name: Tool name (used to generate model class name).
        schema: JSON Schema dict with "properties" and optionally "required".

    Returns:
        A Pydantic model class with typed fields.
    """
    from pydantic import Field, create_model

    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    fields: dict[str, Any] = {}

    type_map: dict[str, type] = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
    }

    for prop_name, prop_schema in properties.items():
        json_type = prop_schema.get("type", "string")
        description = prop_schema.get("description", "")

        # Handle union types like ["string", "null"]
        if isinstance(json_type, list):
            json_type = next((t for t in json_type if t != "null"), "string")

        if json_type == "array":
            # Use list[str] instead of bare list — OpenAI requires typed items
            items_type = prop_schema.get("items", {}).get("type", "string")
            item_py = type_map.get(items_type, str)
            py_type: type = list[item_py]  # type: ignore[valid-type]
        elif json_type == "object":
            # Free-form objects → string (JSON) for LLM compatibility.
            # OpenAI/Anthropic function calling requires strict object schemas.
            # The LLM sends a JSON string; the HTTP layer deserializes it.
            py_type = str
        else:
            py_type = type_map.get(json_type, str)

        if prop_name in required:
            fields[prop_name] = (py_type, Field(description=description))
        else:
            fields[prop_name] = (
                py_type | None,
                Field(default=None, description=description),
            )

    # Sanitize tool name for valid Python class name
    class_name = tool_name.replace(".", "_").replace("-", "_").title().replace("_", "")
    return create_model(f"{class_name}Schema", **fields)
