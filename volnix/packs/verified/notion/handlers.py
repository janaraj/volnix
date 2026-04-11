"""Action handlers for the Notion service pack.

Each function handles one tool action, producing a ResponseProposal with
any state mutations expressed as StateDelta objects.

Handlers import ONLY from volnix.core (types, context). They NEVER
import from persistence/, engines/, or bus/.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from volnix.core.context import ResponseProposal
from volnix.core.types import EntityId, StateDelta

# ---------------------------------------------------------------------------
# Notion-style error response helper
# ---------------------------------------------------------------------------


def _notion_error(status: int, code: str, message: str) -> dict[str, Any]:
    """Return a Notion-format error response body."""
    return {
        "object": "error",
        "status": status,
        "code": code,
        "message": message,
    }


def _new_id(prefix: str) -> str:
    """Generate a unique entity ID with the given prefix."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def _extract_title_plain_text(obj: dict[str, Any]) -> str:
    """Extract a plain-text title from a page or database object.

    Checks properties for a 'title'-type property (pages) and the
    top-level 'title' rich-text array (databases).
    """
    # Database-style: top-level 'title' array
    title_array = obj.get("title")
    if isinstance(title_array, list):
        parts = []
        for rt in title_array:
            if isinstance(rt, dict):
                parts.append(rt.get("plain_text") or rt.get("text", {}).get("content", ""))
            elif isinstance(rt, str):
                parts.append(rt)
        joined = "".join(parts)
        if joined:
            return joined

    # Page-style: search properties for one of type 'title'
    properties = obj.get("properties", {})
    for prop_val in properties.values():
        if isinstance(prop_val, dict) and prop_val.get("type") == "title":
            title_items = prop_val.get("title", [])
            if isinstance(title_items, list):
                parts = [
                    rt.get("plain_text") or (rt.get("text", {}).get("content", ""))
                    for rt in title_items
                ]
                joined = "".join(parts)
                if joined:
                    return joined

    return ""


# ---------------------------------------------------------------------------
# Cursor-based pagination helper
# ---------------------------------------------------------------------------


def _infer_list_type(
    page: list[dict[str, Any]],
    items: list[dict[str, Any]],
) -> str:
    """Infer the Notion-API `type` discriminator for a pagination response.

    Cascading fallback chain, resilient to missing ``"object"`` keys and
    non-dict items (both of which occasionally arrive from LLM-generated
    seed data or dynamic enrichment). Order:

    1. Scan the current page for the first dict item that has ``"object"``.
       Matches the real Notion API contract — the page's type reflects
       the type of items in that page.
    2. Fall back to scanning the full items list for any dict item with
       ``"object"``. This keeps the response accurate when the current
       page happens to contain only corrupt items but other items in the
       full list are well-formed.
    3. Ultimate fallback to the literal ``"list"`` — Notion's own generic
       object-discriminator for list responses. Always accurate, never
       lies about the underlying entity type.

    Scanning (rather than checking only [0]) makes the helper robust
    against the "first item corrupt, rest well-formed" shape observed
    in the P6.3 supply-chain live run, where auto-registered actor
    entities occasionally lacked the "object" discriminator.
    """
    for item in page:
        if isinstance(item, dict) and "object" in item:
            return str(item["object"])
    for item in items:
        if isinstance(item, dict) and "object" in item:
            return str(item["object"])
    return "list"


def _paginate_cursor(
    items: list[dict[str, Any]],
    input_data: dict[str, Any],
) -> dict[str, Any]:
    """Apply Notion-style cursor pagination to a list of items.

    Returns a dict with ``results``, ``has_more``, ``next_cursor``, and
    ``object: "list"``.
    """
    page_size = min(input_data.get("page_size", 100), 100)
    start_cursor = input_data.get("start_cursor")

    start_index = 0
    if start_cursor:
        for i, item in enumerate(items):
            if isinstance(item, dict) and item.get("id") == start_cursor:
                start_index = i + 1
                break

    end_index = start_index + page_size
    page = items[start_index:end_index]
    has_more = end_index < len(items)
    next_cursor = (
        items[end_index]["id"]
        if has_more and isinstance(items[end_index], dict) and "id" in items[end_index]
        else None
    )

    return {
        "object": "list",
        "results": page,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "type": _infer_list_type(page, items),
    }


# ---------------------------------------------------------------------------
# Pages handlers
# ---------------------------------------------------------------------------


async def handle_pages_create(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``pages.create`` action.

    Creates a page entity under a parent database or page.  Optionally
    creates child block entities from the ``children`` input.
    """
    parent = input_data.get("parent", {})
    if not isinstance(parent, dict) or not (parent.get("database_id") or parent.get("page_id")):
        return ResponseProposal(
            response_body=_notion_error(
                400,
                "validation_error",
                "parent must contain database_id or page_id.",
            ),
        )
    properties = input_data.get("properties", {})
    now = _now_iso()
    page_id = _new_id("page")

    page_fields: dict[str, Any] = {
        "id": page_id,
        "object": "page",
        "created_time": now,
        "last_edited_time": now,
        "created_by": {"object": "user", "id": "system"},
        "last_edited_by": {"object": "user", "id": "system"},
        "parent": parent,
        "archived": False,
        "in_trash": False,
        "properties": properties,
        "url": f"https://www.notion.so/{page_id.replace('-', '')}",
        "public_url": None,
    }

    if "icon" in input_data:
        page_fields["icon"] = input_data["icon"]
    if "cover" in input_data:
        page_fields["cover"] = input_data["cover"]

    deltas: list[StateDelta] = [
        StateDelta(
            entity_type="page",
            entity_id=EntityId(page_id),
            operation="create",
            fields=page_fields,
        ),
    ]

    # Create child blocks if provided
    children_input = input_data.get("children", [])
    for child_def in children_input:
        block_id = _new_id("block")
        block_type = child_def.get("type", "paragraph")
        block_fields: dict[str, Any] = {
            "id": block_id,
            "object": "block",
            "type": block_type,
            "parent": {"type": "page_id", "page_id": page_id},
            "created_time": now,
            "last_edited_time": now,
            "created_by": {"object": "user", "id": "system"},
            "last_edited_by": {"object": "user", "id": "system"},
            "archived": False,
            "in_trash": False,
            "has_children": False,
        }
        # Copy the type-specific content (e.g. child_def["paragraph"])
        if block_type in child_def:
            block_fields[block_type] = child_def[block_type]
        deltas.append(
            StateDelta(
                entity_type="block",
                entity_id=EntityId(block_id),
                operation="create",
                fields=block_fields,
            ),
        )

    return ResponseProposal(
        response_body=page_fields,
        proposed_state_deltas=deltas,
    )


async def handle_pages_retrieve(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``pages.retrieve`` action.

    Finds a single page by ID. No state mutations.
    """
    page_id = input_data["page_id"]
    pages = state.get("pages", [])

    for p in pages:
        if p.get("id") == page_id:
            return ResponseProposal(response_body=p)

    return ResponseProposal(
        response_body=_notion_error(
            404, "object_not_found", f"Could not find page with ID: {page_id}."
        ),
    )


async def handle_pages_update(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``pages.update`` action.

    Updates page properties, icon, cover, or archived status.
    """
    page_id = input_data["page_id"]
    pages = state.get("pages", [])

    page = None
    for p in pages:
        if p.get("id") == page_id:
            page = p
            break

    if page is None:
        return ResponseProposal(
            response_body=_notion_error(
                404, "object_not_found", f"Could not find page with ID: {page_id}."
            ),
        )

    now = _now_iso()
    updated_fields: dict[str, Any] = {"last_edited_time": now}
    previous_fields: dict[str, Any] = {}

    # Merge property updates
    if "properties" in input_data:
        old_props = page.get("properties", {})
        new_props = {**old_props, **input_data["properties"]}
        updated_fields["properties"] = new_props
        previous_fields["properties"] = old_props

    if "archived" in input_data:
        old_archived = page.get("archived", False)
        updated_fields["archived"] = input_data["archived"]
        if input_data["archived"]:
            updated_fields["in_trash"] = True
        previous_fields["archived"] = old_archived

    if "icon" in input_data:
        previous_fields["icon"] = page.get("icon")
        updated_fields["icon"] = input_data["icon"]

    if "cover" in input_data:
        previous_fields["cover"] = page.get("cover")
        updated_fields["cover"] = input_data["cover"]

    delta = StateDelta(
        entity_type="page",
        entity_id=EntityId(page_id),
        operation="update",
        fields=updated_fields,
        previous_fields=previous_fields if previous_fields else None,
    )

    response_page = {**page, **updated_fields}

    return ResponseProposal(
        response_body=response_page,
        proposed_state_deltas=[delta],
    )


# ---------------------------------------------------------------------------
# Databases handlers
# ---------------------------------------------------------------------------


async def handle_databases_create(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``databases.create`` action.

    Creates a new database entity under a parent page.
    """
    parent = input_data.get("parent", {})
    if not isinstance(parent, dict) or not parent.get("page_id"):
        return ResponseProposal(
            response_body=_notion_error(
                400,
                "validation_error",
                "parent must contain page_id. Databases are created under pages.",
            ),
        )
    title = input_data.get("title", [])
    properties = input_data.get("properties", {})
    now = _now_iso()
    db_id = _new_id("db")

    db_fields: dict[str, Any] = {
        "id": db_id,
        "object": "database",
        "created_time": now,
        "last_edited_time": now,
        "created_by": {"object": "user", "id": "system"},
        "last_edited_by": {"object": "user", "id": "system"},
        "title": title,
        "description": [],
        "parent": parent,
        "archived": False,
        "in_trash": False,
        "is_inline": input_data.get("is_inline", False),
        "properties": properties,
        "url": f"https://www.notion.so/{db_id.replace('-', '')}",
        "public_url": None,
    }

    if "icon" in input_data:
        db_fields["icon"] = input_data["icon"]
    if "cover" in input_data:
        db_fields["cover"] = input_data["cover"]

    delta = StateDelta(
        entity_type="database",
        entity_id=EntityId(db_id),
        operation="create",
        fields=db_fields,
    )

    return ResponseProposal(
        response_body=db_fields,
        proposed_state_deltas=[delta],
    )


async def handle_databases_retrieve(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``databases.retrieve`` action.

    Finds a single database by ID. No state mutations.
    """
    db_id = input_data["database_id"]
    databases = state.get("databases", [])

    for db in databases:
        if db.get("id") == db_id:
            return ResponseProposal(response_body=db)

    return ResponseProposal(
        response_body=_notion_error(
            404, "object_not_found", f"Could not find database with ID: {db_id}."
        ),
    )


def _match_property_filter(
    page: dict[str, Any],
    filter_obj: dict[str, Any],
) -> bool:
    """Evaluate a single Notion property filter against a page's properties.

    Supports: equals, does_not_equal, contains, does_not_contain,
    starts_with, ends_with, is_empty, is_not_empty for text-like types;
    equals/does_not_equal/greater_than/less_than etc. for numbers;
    equals/does_not_equal for checkbox and select.
    """
    prop_name = filter_obj.get("property")
    if not prop_name:
        return True

    properties = page.get("properties", {})
    prop_value = properties.get(prop_name, {})

    # Determine the filter type key (e.g. "title", "rich_text", "number", ...)
    filter_type_keys = [
        "title",
        "rich_text",
        "number",
        "checkbox",
        "select",
        "multi_select",
        "date",
        "status",
        "url",
        "email",
        "phone_number",
    ]

    for type_key in filter_type_keys:
        condition = filter_obj.get(type_key)
        if condition is None:
            continue

        # Extract the actual value from the property
        actual_value = _extract_property_value(prop_value, type_key)

        # Evaluate the condition
        return _evaluate_condition(actual_value, condition, type_key)

    # No recognized filter type key found — include the entity
    # (matches Notion API behavior: unknown filter types are ignored)
    return True


def _extract_property_value(
    prop_value: dict[str, Any] | Any,
    type_key: str,
) -> Any:
    """Extract the comparable value from a Notion property value object."""
    if not isinstance(prop_value, dict):
        return prop_value

    prop_type = prop_value.get("type", type_key)

    if prop_type in ("title", "rich_text"):
        items = prop_value.get(prop_type, [])
        if isinstance(items, list):
            parts = []
            for rt in items:
                if isinstance(rt, dict):
                    parts.append(rt.get("plain_text") or rt.get("text", {}).get("content", ""))
                elif isinstance(rt, str):
                    parts.append(rt)
            return "".join(parts)
        return str(items) if items else ""

    if prop_type == "number":
        return prop_value.get("number")

    if prop_type == "checkbox":
        return prop_value.get("checkbox", False)

    if prop_type == "select":
        sel = prop_value.get("select")
        if isinstance(sel, dict):
            return sel.get("name", "")
        return sel

    if prop_type == "multi_select":
        items = prop_value.get("multi_select", [])
        if isinstance(items, list):
            return [s.get("name", "") if isinstance(s, dict) else s for s in items]
        return []

    if prop_type == "date":
        date_obj = prop_value.get("date")
        if isinstance(date_obj, dict):
            return date_obj.get("start")
        return date_obj

    if prop_type == "status":
        status = prop_value.get("status")
        if isinstance(status, dict):
            return status.get("name", "")
        return status

    if prop_type in ("url", "email", "phone_number"):
        return prop_value.get(prop_type, "")

    # Fallback: return the raw value
    return prop_value


def _evaluate_condition(
    actual: Any,
    condition: dict[str, Any],
    type_key: str,
) -> bool:
    """Evaluate a Notion filter condition dict against an actual value."""
    actual_str = str(actual).lower() if actual is not None else ""

    if "equals" in condition:
        expected = condition["equals"]
        if type_key in ("number",):
            return bool(actual == expected)
        if type_key == "checkbox":
            return bool(actual == expected)
        return actual_str == str(expected).lower()

    if "does_not_equal" in condition:
        expected = condition["does_not_equal"]
        if type_key in ("number",):
            return bool(actual != expected)
        if type_key == "checkbox":
            return bool(actual != expected)
        return actual_str != str(expected).lower()

    if "contains" in condition:
        return str(condition["contains"]).lower() in actual_str

    if "does_not_contain" in condition:
        return str(condition["does_not_contain"]).lower() not in actual_str

    if "starts_with" in condition:
        return actual_str.startswith(str(condition["starts_with"]).lower())

    if "ends_with" in condition:
        return actual_str.endswith(str(condition["ends_with"]).lower())

    if "is_empty" in condition:
        if condition["is_empty"]:
            return actual is None or actual == "" or actual == []
        return actual is not None and actual != "" and actual != []

    if "is_not_empty" in condition:
        if condition["is_not_empty"]:
            return actual is not None and actual != "" and actual != []
        return actual is None or actual == "" or actual == []

    if "greater_than" in condition:
        if actual is None:
            return False
        return bool(actual > condition["greater_than"])

    if "greater_than_or_equal_to" in condition:
        if actual is None:
            return False
        return bool(actual >= condition["greater_than_or_equal_to"])

    if "less_than" in condition:
        if actual is None:
            return False
        return bool(actual < condition["less_than"])

    if "less_than_or_equal_to" in condition:
        if actual is None:
            return False
        return bool(actual <= condition["less_than_or_equal_to"])

    return True


def _apply_filter(
    pages: list[dict[str, Any]],
    filter_obj: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Apply a Notion filter (including compound and/or) to a list of pages."""
    if not filter_obj:
        return pages

    # Compound AND
    if "and" in filter_obj:
        and_result = list(pages)
        for sub_filter in filter_obj["and"]:
            and_result = _apply_filter(and_result, sub_filter)
        return and_result

    # Compound OR
    if "or" in filter_obj:
        seen_ids: set[str] = set()
        or_result: list[dict[str, Any]] = []
        for sub_filter in filter_obj["or"]:
            for p in _apply_filter(pages, sub_filter):
                pid = p.get("id", "")
                if pid not in seen_ids:
                    seen_ids.add(pid)
                    or_result.append(p)
        return or_result

    # Single property filter
    return [p for p in pages if _match_property_filter(p, filter_obj)]


async def handle_databases_query(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``databases.query`` action.

    Queries pages that belong to the specified database, applying optional
    filters (property conditions, compound and/or) and sorts.  Uses cursor
    pagination.
    """
    db_id = input_data["database_id"]
    databases = state.get("databases", [])

    # Verify database exists
    db_exists = any(db.get("id") == db_id for db in databases)
    if not db_exists:
        return ResponseProposal(
            response_body=_notion_error(
                404, "object_not_found", f"Could not find database with ID: {db_id}."
            ),
        )

    # Collect pages belonging to this database
    pages = state.get("pages", [])
    db_pages = [
        p
        for p in pages
        if isinstance(p.get("parent"), dict)
        and p["parent"].get("database_id") == db_id
        and not p.get("archived", False)
    ]

    # Apply filters
    filter_obj = input_data.get("filter")
    db_pages = _apply_filter(db_pages, filter_obj)

    # Apply sorts
    sorts = input_data.get("sorts", [])
    for sort_spec in reversed(sorts):
        sort_key = sort_spec.get("property") or sort_spec.get("timestamp")
        direction = sort_spec.get("direction", "ascending")
        reverse = direction == "descending"

        if sort_spec.get("timestamp"):
            db_pages.sort(key=lambda p: p.get(sort_key, ""), reverse=reverse)
        elif sort_key:

            def _sort_val(p: dict[str, Any], key: str = sort_key) -> str:
                prop_val = p.get("properties", {}).get(key, {})
                return str(_extract_property_value(prop_val, "rich_text")).lower()

            db_pages.sort(key=_sort_val, reverse=reverse)

    result = _paginate_cursor(db_pages, input_data)
    return ResponseProposal(response_body=result)


# ---------------------------------------------------------------------------
# Blocks handlers
# ---------------------------------------------------------------------------


async def handle_blocks_children_list(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``blocks.children.list`` action.

    Lists child blocks of a given block or page. Uses cursor pagination.
    """
    parent_id = input_data["block_id"]
    blocks = state.get("blocks", [])

    children = [
        b
        for b in blocks
        if isinstance(b.get("parent"), dict)
        and (b["parent"].get("page_id") == parent_id or b["parent"].get("block_id") == parent_id)
        and not b.get("archived", False)
    ]

    result = _paginate_cursor(children, input_data)
    return ResponseProposal(response_body=result)


async def handle_blocks_children_append(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``blocks.children.append`` action.

    Appends new child blocks to a block or page. Creates block entities
    and updates the parent's has_children flag.
    """
    parent_id = input_data["block_id"]
    children_input = input_data.get("children", [])
    now = _now_iso()

    deltas: list[StateDelta] = []
    created_blocks: list[dict[str, Any]] = []

    # Determine parent type — could be a page or a block
    pages = state.get("pages", [])
    parent_is_page = any(p.get("id") == parent_id for p in pages)
    parent_type = "page_id" if parent_is_page else "block_id"

    for child_def in children_input:
        block_id = _new_id("block")
        block_type = child_def.get("type", "paragraph")
        block_fields: dict[str, Any] = {
            "id": block_id,
            "object": "block",
            "type": block_type,
            "parent": {"type": parent_type, parent_type: parent_id},
            "created_time": now,
            "last_edited_time": now,
            "created_by": {"object": "user", "id": "system"},
            "last_edited_by": {"object": "user", "id": "system"},
            "archived": False,
            "in_trash": False,
            "has_children": False,
        }
        # Copy the type-specific content
        if block_type in child_def:
            block_fields[block_type] = child_def[block_type]

        created_blocks.append(block_fields)
        deltas.append(
            StateDelta(
                entity_type="block",
                entity_id=EntityId(block_id),
                operation="create",
                fields=block_fields,
            ),
        )

    # Update parent's has_children flag if parent is a block
    if not parent_is_page:
        blocks = state.get("blocks", [])
        for b in blocks:
            if b.get("id") == parent_id:
                if not b.get("has_children", False):
                    deltas.append(
                        StateDelta(
                            entity_type="block",
                            entity_id=EntityId(parent_id),
                            operation="update",
                            fields={"has_children": True, "last_edited_time": now},
                            previous_fields={"has_children": False},
                        ),
                    )
                break

    return ResponseProposal(
        response_body={
            "object": "list",
            "results": created_blocks,
            "type": "block",
        },
        proposed_state_deltas=deltas,
    )


async def handle_blocks_retrieve(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``blocks.retrieve`` action.

    Finds a single block by ID. No state mutations.
    """
    block_id = input_data["block_id"]
    blocks = state.get("blocks", [])

    for b in blocks:
        if b.get("id") == block_id:
            return ResponseProposal(response_body=b)

    return ResponseProposal(
        response_body=_notion_error(
            404, "object_not_found", f"Could not find block with ID: {block_id}."
        ),
    )


async def handle_blocks_delete(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``blocks.delete`` action.

    Archives (soft-deletes) a block by setting archived=True and
    in_trash=True.
    """
    block_id = input_data["block_id"]
    blocks = state.get("blocks", [])

    block = None
    for b in blocks:
        if b.get("id") == block_id:
            block = b
            break

    if block is None:
        return ResponseProposal(
            response_body=_notion_error(
                404, "object_not_found", f"Could not find block with ID: {block_id}."
            ),
        )

    now = _now_iso()
    delta = StateDelta(
        entity_type="block",
        entity_id=EntityId(block_id),
        operation="update",
        fields={"archived": True, "in_trash": True, "last_edited_time": now},
        previous_fields={
            "archived": block.get("archived", False),
            "in_trash": block.get("in_trash", False),
        },
    )

    response_block = {
        **block,
        "archived": True,
        "in_trash": True,
        "last_edited_time": now,
    }

    return ResponseProposal(
        response_body=response_block,
        proposed_state_deltas=[delta],
    )


# ---------------------------------------------------------------------------
# Users handlers
# ---------------------------------------------------------------------------


async def handle_users_list(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``users.list`` action.

    Lists all users in the workspace. Uses cursor pagination.
    """
    users = list(state.get("users", []))
    result = _paginate_cursor(users, input_data)
    return ResponseProposal(response_body=result)


async def handle_users_me(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``users.me`` action.

    Returns the bot user associated with the integration token.
    Looks for a user with type='bot'; falls back to the first user.
    """
    users = state.get("users", [])

    # Look for the bot user
    for u in users:
        if u.get("type") == "bot":
            return ResponseProposal(response_body=u)

    # Fallback: return the first user if any
    if users:
        return ResponseProposal(response_body=users[0])

    return ResponseProposal(
        response_body=_notion_error(
            404, "object_not_found", "No bot user found for this integration."
        ),
    )


# ---------------------------------------------------------------------------
# Search handler
# ---------------------------------------------------------------------------


async def handle_search(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``search`` action.

    Fuzzy case-insensitive search across page titles and database titles.
    Supports filtering by object type (page/database) and cursor pagination.
    """
    query = input_data.get("query", "").lower()
    filter_obj = input_data.get("filter")
    sort_obj = input_data.get("sort")

    # Collect all searchable objects
    candidates: list[dict[str, Any]] = []

    # Include pages unless filter restricts to databases only
    include_pages = True
    include_databases = True
    if filter_obj and filter_obj.get("value"):
        obj_type = filter_obj["value"]
        include_pages = obj_type == "page"
        include_databases = obj_type == "database"

    if include_pages:
        for p in state.get("pages", []):
            if not p.get("archived", False):
                candidates.append(p)

    if include_databases:
        for db in state.get("databases", []):
            if not db.get("archived", False):
                candidates.append(db)

    # Apply fuzzy case-insensitive title matching
    if query:
        matched: list[dict[str, Any]] = []
        for obj in candidates:
            title_text = _extract_title_plain_text(obj).lower()
            # Also search in property values for pages
            properties_text = ""
            if obj.get("object") == "page":
                for prop_val in obj.get("properties", {}).values():
                    if isinstance(prop_val, str):
                        properties_text += " " + prop_val
                    elif isinstance(prop_val, dict):
                        extracted = _extract_property_value(prop_val, prop_val.get("type", ""))
                        if extracted:
                            properties_text += " " + str(extracted).lower()

            searchable = title_text + " " + properties_text
            if query in searchable:
                matched.append(obj)
        candidates = matched

    # Apply sort
    if sort_obj:
        ts_key = sort_obj.get("timestamp", "last_edited_time")
        direction = sort_obj.get("direction", "descending")
        candidates.sort(
            key=lambda o: o.get(ts_key, ""),
            reverse=(direction == "descending"),
        )

    result = _paginate_cursor(candidates, input_data)
    return ResponseProposal(response_body=result)


# ---------------------------------------------------------------------------
# Comments handlers
# ---------------------------------------------------------------------------


async def handle_comments_create(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``comments.create`` action.

    Creates a comment on a page (new discussion) or in an existing
    discussion thread.  Requires either parent.page_id or discussion_id.
    """
    parent = input_data.get("parent")
    discussion_id = input_data.get("discussion_id")
    rich_text = input_data.get("rich_text", [])

    if not parent and not discussion_id:
        return ResponseProposal(
            response_body=_notion_error(
                400,
                "validation_error",
                "Either parent.page_id or discussion_id is required.",
            ),
        )

    now = _now_iso()
    comment_id = _new_id("comment")

    # Determine discussion ID
    resolved_parent: dict[str, Any]
    if discussion_id:
        resolved_discussion_id = discussion_id
        # Build parent from existing comment's parent
        comments = state.get("comments", [])
        resolved_parent = {"type": "page_id", "page_id": "unknown"}
        for c in comments:
            if c.get("discussion_id") == discussion_id:
                existing_parent = c.get("parent")
                if isinstance(existing_parent, dict):
                    resolved_parent = existing_parent
                break
    else:
        if not isinstance(parent, dict) or "page_id" not in parent:
            return ResponseProposal(
                response_body=_notion_error(
                    400,
                    "validation_error",
                    "parent must be an object with page_id.",
                ),
            )
        page_id = parent["page_id"]
        # Verify the page exists
        pages = state.get("pages", [])
        if not any(p.get("id") == page_id for p in pages):
            return ResponseProposal(
                response_body=_notion_error(
                    404,
                    "object_not_found",
                    f"Could not find page with ID: {page_id}.",
                ),
            )
        resolved_discussion_id = _new_id("disc")
        resolved_parent = {"type": "page_id", "page_id": page_id}

    comment_fields: dict[str, Any] = {
        "id": comment_id,
        "object": "comment",
        "parent": resolved_parent,
        "discussion_id": resolved_discussion_id,
        "rich_text": rich_text,
        "created_time": now,
        "last_edited_time": now,
        "created_by": {"object": "user", "id": "system"},
    }

    delta = StateDelta(
        entity_type="comment",
        entity_id=EntityId(comment_id),
        operation="create",
        fields=comment_fields,
    )

    return ResponseProposal(
        response_body=comment_fields,
        proposed_state_deltas=[delta],
    )


async def handle_comments_list(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``comments.list`` action.

    Lists comments on a page or block. Uses cursor pagination.
    """
    block_id = input_data["block_id"]
    comments = state.get("comments", [])

    # Filter comments by parent page_id or block_id
    filtered = [
        c
        for c in comments
        if isinstance(c.get("parent"), dict)
        and (c["parent"].get("page_id") == block_id or c["parent"].get("block_id") == block_id)
    ]

    result = _paginate_cursor(filtered, input_data)
    return ResponseProposal(response_body=result)
