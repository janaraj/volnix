"""Action handlers for the browser service pack.

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
from volnix.core.types import EntityId, ServiceId, SideEffect, StateDelta

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _browser_error(error: str, description: str) -> dict[str, Any]:
    """Return a browser-style error response body."""
    return {"error": error, "description": description}


def _new_id(prefix: str) -> str:
    """Generate a unique entity ID with the given prefix."""
    return f"{prefix}-{uuid.uuid4().hex}"


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def _find_entity(
    entities: list[dict[str, Any]],
    entity_id: str,
) -> dict[str, Any] | None:
    """Find an entity by id in a list."""
    for e in entities:
        if e.get("id") == entity_id:
            return e
    return None


def _parse_url(url: str) -> tuple[str, str]:
    """Parse a URL into (domain, path).

    Strips protocol (https://), lowercases domain, normalizes path.
    Returns e.g. ``('dashboard.acme.com', '/tickets/TK-123')``.
    """
    clean = url.strip()
    # Strip protocol
    for prefix in ("https://", "http://"):
        if clean.lower().startswith(prefix):
            clean = clean[len(prefix) :]
            break
    # Split domain and path
    if "/" in clean:
        domain, path = clean.split("/", 1)
        path = "/" + path
    else:
        domain = clean
        path = "/"
    # Normalize
    domain = domain.lower().rstrip(".")
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return domain, path


def _find_page_by_url(
    pages: list[dict[str, Any]],
    domain: str,
    path: str,
) -> dict[str, Any] | None:
    """Find a published or compromised web_page matching domain and path."""
    for p in pages:
        if (
            p.get("domain", "").lower() == domain
            and p.get("path", "") == path
            and p.get("status") in ("published", "compromised")
        ):
            return p
    return None


def _build_page_response(page: dict[str, Any]) -> dict[str, Any]:
    """Build the standard page response body from a page entity."""
    return {
        "id": page.get("id"),
        "url": f"{page.get('domain', '')}{page.get('path', '')}",
        "title": page.get("title", ""),
        "content_text": page.get("content_text", ""),
        "page_type": page.get("page_type", ""),
        "links": page.get("links", []),
        "forms": page.get("forms", []),
        "meta_description": page.get("meta_description", ""),
        "status": page.get("status", ""),
    }


# ---------------------------------------------------------------------------
# Handler 1: web_navigate (MUTATING — creates/updates session)
# ---------------------------------------------------------------------------


async def handle_web_navigate(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``web_navigate`` action.

    Navigate to a URL, return page content, and update/create session.
    Auto-creates a session if no session_id is provided.
    """
    url = input_data["url"]
    domain, path = _parse_url(url)
    session_id = input_data.get("session_id")
    now = _now_iso()
    pages = state.get("web_pages", [])
    sessions = state.get("web_sessions", [])
    deltas: list[StateDelta] = []

    # Find or auto-create session
    session: dict[str, Any] | None = None
    created_session = False
    if session_id:
        session = _find_entity(sessions, session_id)

    if session is None:
        session_id = _new_id("ws")
        session = {
            "id": session_id,
            "actor_id": input_data.get("actor_id", "unknown"),
            "current_url": None,
            "current_page_id": None,
            "history": [],
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        created_session = True

    # Push current URL to history (if we had one)
    history = list(session.get("history", []))
    prev_url = session.get("current_url")
    if prev_url:
        history.append(prev_url)

    # Look up page
    page = _find_page_by_url(pages, domain, path)
    full_url = f"{domain}{path}"

    # Build session update fields
    session_fields: dict[str, Any] = {
        "current_url": full_url,
        "current_page_id": page["id"] if page else None,
        "history": history,
        "updated_at": now,
    }

    if created_session:
        deltas.append(
            StateDelta(
                entity_type="web_session",
                entity_id=EntityId(session_id),
                operation="create",
                fields={**session, **session_fields},
            )
        )
    else:
        deltas.append(
            StateDelta(
                entity_type="web_session",
                entity_id=EntityId(session.get("id", session_id)),
                operation="update",
                fields=session_fields,
                previous_fields={
                    "current_url": session.get("current_url"),
                    "current_page_id": session.get("current_page_id"),
                },
            )
        )

    if page:
        return ResponseProposal(
            response_body={
                "page": _build_page_response(page),
                "session_id": session.get("id", session_id),
            },
            proposed_state_deltas=deltas,
        )

    return ResponseProposal(
        response_body={
            "page": None,
            "error": "PageNotFound",
            "description": f"No page found at '{full_url}'.",
            "session_id": session.get("id", session_id),
        },
        proposed_state_deltas=deltas,
    )


# ---------------------------------------------------------------------------
# Handler 2: web_search (READ-ONLY)
# ---------------------------------------------------------------------------


async def handle_web_search(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``web_search`` action.

    Search across all published web pages. Ranks by title (3),
    keywords (2), content/meta (1). Supports pagination.
    """
    query_tokens = [t for t in input_data["query"].lower().split() if len(t) > 2]
    pages = state.get("web_pages", [])

    # Score each published/compromised page (tokenized matching)
    scored: list[tuple[int, dict[str, Any]]] = []
    for p in pages:
        if p.get("status") not in ("published", "compromised"):
            continue
        score = 0
        title = p.get("title", "").lower()
        content = p.get("content_text", "").lower()
        meta = p.get("meta_description", "").lower()
        keywords = " ".join(p.get("keywords", [])).lower()

        for token in query_tokens:
            if token in title:
                score += 3
            if token in keywords:
                score += 2
            if token in content:
                score += 1
            if token in meta:
                score += 1
        if score > 0:
            scored.append((score, p))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Pagination
    per_page = input_data.get("per_page", 10)
    page_num = input_data.get("page", 1)
    if page_num is None:
        page_num = 1
    start = (page_num - 1) * per_page
    end = start + per_page
    paginated = scored[start:end]

    results = []
    for _score, p in paginated:
        content_text = p.get("content_text", "")
        snippet = content_text[:200] + ("..." if len(content_text) > 200 else "")
        results.append(
            {
                "title": p.get("title", ""),
                "url": f"{p.get('domain', '')}{p.get('path', '')}",
                "snippet": snippet,
                "page_id": p.get("id"),
            }
        )

    return ResponseProposal(
        response_body={
            "results": results,
            "count": len(results),
            "total": len(scored),
            "next_page": page_num + 1 if end < len(scored) else None,
        },
    )


# ---------------------------------------------------------------------------
# Handler 3: web_read_page (READ-ONLY)
# ---------------------------------------------------------------------------


async def handle_web_read_page(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``web_read_page`` action.

    Read full content of current page (by session) or specific page (by ID).
    """
    pages = state.get("web_pages", [])
    sessions = state.get("web_sessions", [])
    page_id = input_data.get("page_id")
    session_id = input_data.get("session_id")

    if page_id:
        page = _find_entity(pages, page_id)
    elif session_id:
        session = _find_entity(sessions, session_id)
        if session is None:
            return ResponseProposal(
                response_body=_browser_error(
                    "SessionNotFound",
                    f"Session '{session_id}' not found.",
                ),
            )
        cpid = session.get("current_page_id")
        if not cpid:
            return ResponseProposal(
                response_body=_browser_error(
                    "NoCurrentPage",
                    "Session has no current page.",
                ),
            )
        page = _find_entity(pages, cpid)
    else:
        return ResponseProposal(
            response_body=_browser_error(
                "MissingParameter",
                "Provide session_id or page_id.",
            ),
        )

    if page is None:
        return ResponseProposal(
            response_body=_browser_error("PageNotFound", "Page not found."),
        )

    return ResponseProposal(response_body={"page": _build_page_response(page)})


# ---------------------------------------------------------------------------
# Handler 4: web_click_link (MUTATING — updates session)
# ---------------------------------------------------------------------------


async def handle_web_click_link(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``web_click_link`` action.

    Follow a link on the current page. Validates the link exists on
    the page's links list, then navigates to the target URL.
    """
    session_id = input_data["session_id"]
    sessions = state.get("web_sessions", [])
    pages = state.get("web_pages", [])

    session = _find_entity(sessions, session_id)
    if session is None:
        return ResponseProposal(
            response_body=_browser_error(
                "SessionNotFound",
                f"Session '{session_id}' not found.",
            ),
        )

    current_page_id = session.get("current_page_id")
    if not current_page_id:
        return ResponseProposal(
            response_body=_browser_error(
                "NoCurrentPage",
                "No current page to click links on.",
            ),
        )

    current_page = _find_entity(pages, current_page_id)
    if current_page is None:
        return ResponseProposal(
            response_body=_browser_error(
                "PageNotFound",
                "Current page no longer exists.",
            ),
        )

    page_links = current_page.get("links", [])
    link_url = input_data.get("link_url")
    link_index = input_data.get("link_index")

    # Resolve the target href
    target_href: str | None = None
    if link_index is not None:
        if 0 <= link_index < len(page_links):
            target_href = page_links[link_index].get("href")
        else:
            return ResponseProposal(
                response_body=_browser_error(
                    "LinkNotFound",
                    f"Link index {link_index} out of range (page has {len(page_links)} links).",
                ),
            )
    elif link_url:
        for link in page_links:
            if link.get("href") == link_url:
                target_href = link_url
                break
        if target_href is None:
            return ResponseProposal(
                response_body=_browser_error(
                    "LinkNotFound",
                    f"Link '{link_url}' not found on current page.",
                ),
            )
    else:
        return ResponseProposal(
            response_body=_browser_error(
                "MissingParameter",
                "Provide link_url or link_index.",
            ),
        )

    # Resolve relative URLs
    if target_href.startswith("/"):
        target_href = f"{current_page.get('domain', '')}{target_href}"

    # Navigate to target
    domain, path = _parse_url(target_href)
    full_url = f"{domain}{path}"
    now = _now_iso()

    target_page = _find_page_by_url(pages, domain, path)

    history = list(session.get("history", []))
    prev_url = session.get("current_url")
    if prev_url:
        history.append(prev_url)

    session_fields: dict[str, Any] = {
        "current_url": full_url,
        "current_page_id": target_page["id"] if target_page else None,
        "history": history,
        "updated_at": now,
    }

    delta = StateDelta(
        entity_type="web_session",
        entity_id=EntityId(session_id),
        operation="update",
        fields=session_fields,
        previous_fields={
            "current_url": session.get("current_url"),
            "current_page_id": session.get("current_page_id"),
        },
    )

    if target_page:
        return ResponseProposal(
            response_body={
                "page": _build_page_response(target_page),
                "session_id": session_id,
            },
            proposed_state_deltas=[delta],
        )

    return ResponseProposal(
        response_body={
            "page": None,
            "error": "PageNotFound",
            "description": f"Link target '{full_url}' not found.",
            "session_id": session_id,
        },
        proposed_state_deltas=[delta],
    )


# ---------------------------------------------------------------------------
# Handler 5: web_submit_form (SIDE EFFECT — targets another service)
# ---------------------------------------------------------------------------


async def handle_web_submit_form(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``web_submit_form`` action.

    Submit a form on the current page. Creates a SideEffect targeting
    the form's service, which enters the governance pipeline.
    """
    session_id = input_data["session_id"]
    form_id = input_data["form_id"]
    form_data = input_data["form_data"]
    sessions = state.get("web_sessions", [])
    pages = state.get("web_pages", [])

    session = _find_entity(sessions, session_id)
    if session is None:
        return ResponseProposal(
            response_body=_browser_error(
                "SessionNotFound",
                f"Session '{session_id}' not found.",
            ),
        )

    current_page_id = session.get("current_page_id")
    if not current_page_id:
        return ResponseProposal(
            response_body=_browser_error(
                "NoCurrentPage",
                "No current page with forms.",
            ),
        )

    current_page = _find_entity(pages, current_page_id)
    if current_page is None:
        return ResponseProposal(
            response_body=_browser_error(
                "PageNotFound",
                "Current page no longer exists.",
            ),
        )

    # Find the form on the page
    page_forms = current_page.get("forms", [])
    form: dict[str, Any] | None = None
    for f in page_forms:
        if f.get("id") == form_id:
            form = f
            break
    if form is None:
        return ResponseProposal(
            response_body=_browser_error(
                "FormNotFound",
                f"Form '{form_id}' not found on current page.",
            ),
        )

    # Validate required fields
    for field_def in form.get("fields", []):
        if field_def.get("required") and field_def["name"] not in form_data:
            return ResponseProposal(
                response_body=_browser_error(
                    "MissingFormField",
                    f"Required field '{field_def['name']}' not provided.",
                ),
            )

    # Create SideEffect to route to target service
    side_effect = SideEffect(
        effect_type=form["action_type"],
        target_service=ServiceId(form["target_service"]),
        parameters={
            **form_data,
            "_source_interface": "browser",
            "_source_url": session.get("current_url", ""),
            "_form_id": form_id,
        },
    )

    return ResponseProposal(
        response_body={
            "submitted": True,
            "action_type": form["action_type"],
            "target_service": form["target_service"],
            "message": f"Form submitted to {form['target_service']}.",
        },
        proposed_side_effects=[side_effect],
    )


# ---------------------------------------------------------------------------
# Handler 6: web_back (MUTATING — updates session)
# ---------------------------------------------------------------------------


async def handle_web_back(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``web_back`` action.

    Navigate back to the previous page in session history.
    """
    session_id = input_data["session_id"]
    sessions = state.get("web_sessions", [])
    pages = state.get("web_pages", [])

    session = _find_entity(sessions, session_id)
    if session is None:
        return ResponseProposal(
            response_body=_browser_error(
                "SessionNotFound",
                f"Session '{session_id}' not found.",
            ),
        )

    history = list(session.get("history", []))
    if not history:
        return ResponseProposal(
            response_body=_browser_error(
                "NoHistory",
                "No previous page in history.",
            ),
        )

    # Pop last URL from history
    prev_url = history.pop()
    domain, path = _parse_url(prev_url)
    page = _find_page_by_url(pages, domain, path)
    now = _now_iso()

    session_fields: dict[str, Any] = {
        "current_url": prev_url,
        "current_page_id": page["id"] if page else None,
        "history": history,
        "updated_at": now,
    }

    delta = StateDelta(
        entity_type="web_session",
        entity_id=EntityId(session_id),
        operation="update",
        fields=session_fields,
        previous_fields={
            "current_url": session.get("current_url"),
            "current_page_id": session.get("current_page_id"),
        },
    )

    if page:
        return ResponseProposal(
            response_body={
                "page": _build_page_response(page),
                "session_id": session_id,
            },
            proposed_state_deltas=[delta],
        )

    return ResponseProposal(
        response_body={
            "page": None,
            "error": "PageNotFound",
            "description": f"Previous page '{prev_url}' no longer exists.",
            "session_id": session_id,
        },
        proposed_state_deltas=[delta],
    )


# ---------------------------------------------------------------------------
# Handler 7: web_list_sites (READ-ONLY)
# ---------------------------------------------------------------------------


async def handle_web_list_sites(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``web_list_sites`` action.

    List all websites in the world. Supports optional filters.
    """
    sites = list(state.get("web_sites", []))

    site_type = input_data.get("site_type")
    if site_type:
        sites = [s for s in sites if s.get("site_type") == site_type]

    auth_filter = input_data.get("auth_required")
    if auth_filter is not None:
        sites = [s for s in sites if s.get("auth_required") == auth_filter]

    return ResponseProposal(
        response_body={"sites": sites, "count": len(sites)},
    )


# ---------------------------------------------------------------------------
# Handler 8: web_get_page (READ-ONLY)
# ---------------------------------------------------------------------------


async def handle_web_get_page(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``web_get_page`` action.

    Get a specific page by its ID. No state mutations.
    """
    page_id = input_data["id"]
    pages = state.get("web_pages", [])
    page = _find_entity(pages, page_id)

    if page is None:
        return ResponseProposal(
            response_body=_browser_error(
                "PageNotFound",
                f"Page '{page_id}' not found.",
            ),
        )

    return ResponseProposal(response_body={"page": _build_page_response(page)})


# ---------------------------------------------------------------------------
# Handler 9: web_create_session (MUTATING — creates session)
# ---------------------------------------------------------------------------


async def handle_web_create_session(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``web_create_session`` action.

    Create a new browser session for an actor.
    """
    session_id = _new_id("ws")
    now = _now_iso()

    session_fields: dict[str, Any] = {
        "id": session_id,
        "actor_id": input_data["actor_id"],
        "current_url": None,
        "current_page_id": None,
        "history": [],
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }

    delta = StateDelta(
        entity_type="web_session",
        entity_id=EntityId(session_id),
        operation="create",
        fields=session_fields,
    )

    return ResponseProposal(
        response_body={"session": session_fields},
        proposed_state_deltas=[delta],
    )


# ---------------------------------------------------------------------------
# Handler 10: web_page_modify (MUTATING — Animator/system tool)
# ---------------------------------------------------------------------------


async def handle_web_page_modify(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``web_page_modify`` action.

    Modify a web page's content. Used by the Animator for content
    compromise, updates, and injections in dynamic/reactive modes.
    """
    pages = state.get("web_pages", [])
    modification = input_data["modification"]
    now = _now_iso()

    # Find page by ID or by domain+path
    page: dict[str, Any] | None = None
    if "id" in input_data:
        page = _find_entity(pages, input_data["id"])
    elif "domain" in input_data and "path" in input_data:
        page = _find_page_by_url(pages, input_data["domain"], input_data["path"])

    if page is None:
        return ResponseProposal(
            response_body=_browser_error(
                "PageNotFound",
                "Page not found for modification.",
            ),
        )

    updated_fields: dict[str, Any] = {"updated_at": now}
    previous_fields: dict[str, Any] = {}

    if modification == "inject_content":
        old_content = page.get("content_text", "")
        injected = input_data.get("injected_content", "")
        updated_fields["content_text"] = f"{old_content}\n\n{injected}"
        updated_fields["status"] = "compromised"
        previous_fields["content_text"] = old_content
        previous_fields["status"] = page.get("status")

    elif modification == "update_content":
        old_content = page.get("content_text", "")
        updated_fields["content_text"] = input_data.get("content_text", old_content)
        previous_fields["content_text"] = old_content
        if "title" in input_data:
            previous_fields["title"] = page.get("title")
            updated_fields["title"] = input_data["title"]

    elif modification == "replace_content":
        old_content = page.get("content_text", "")
        updated_fields["content_text"] = input_data.get("content_text", "")
        previous_fields["content_text"] = old_content
        if "title" in input_data:
            previous_fields["title"] = page.get("title")
            updated_fields["title"] = input_data["title"]

    elif modification == "update_status":
        old_status = page.get("status")
        updated_fields["status"] = input_data.get("status", old_status)
        previous_fields["status"] = old_status

    else:
        return ResponseProposal(
            response_body=_browser_error(
                "InvalidModification",
                f"Unknown modification '{modification}'.",
            ),
        )

    delta = StateDelta(
        entity_type="web_page",
        entity_id=EntityId(page["id"]),
        operation="update",
        fields=updated_fields,
        previous_fields=previous_fields if previous_fields else None,
    )

    merged_page = {**page, **updated_fields}
    return ResponseProposal(
        response_body={"page": _build_page_response(merged_page)},
        proposed_state_deltas=[delta],
    )


# ---------------------------------------------------------------------------
# Handler 11: web_page_create (MUTATING — Animator/system tool)
# ---------------------------------------------------------------------------


async def handle_web_page_create(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``web_page_create`` action.

    Create a new web page at runtime. Used by the Animator to add
    new content such as blog posts or competitor updates.
    """
    page_id = _new_id("wp")
    now = _now_iso()

    page_fields: dict[str, Any] = {
        "id": page_id,
        "site_id": input_data["site_id"],
        "domain": input_data["domain"],
        "path": input_data["path"],
        "title": input_data["title"],
        "content_text": input_data["content_text"],
        "page_type": input_data["page_type"],
        "links": input_data.get("links", []),
        "forms": input_data.get("forms", []),
        "meta_description": input_data.get("meta_description", ""),
        "keywords": input_data.get("keywords", []),
        "status": "published",
        "content_source": "runtime_generated",
        "created_at": now,
        "updated_at": now,
    }

    delta = StateDelta(
        entity_type="web_page",
        entity_id=EntityId(page_id),
        operation="create",
        fields=page_fields,
    )

    return ResponseProposal(
        response_body={"page": _build_page_response(page_fields)},
        proposed_state_deltas=[delta],
    )
