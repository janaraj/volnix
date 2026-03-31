"""Entity schemas and tool definitions for the browser service pack.

Pure data -- no logic, no imports beyond stdlib.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Entity schemas
# ---------------------------------------------------------------------------

WEB_SITE_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "domain", "name", "site_type", "created_at"],
    "properties": {
        "id": {"type": "string"},
        "domain": {
            "type": "string",
            "description": "The domain name, e.g. 'dashboard.acme.com'.",
        },
        "name": {
            "type": "string",
            "description": "Human-readable site name.",
        },
        "site_type": {
            "type": "string",
            "enum": [
                "internal_dashboard",
                "knowledge_base",
                "corporate_website",
                "search_engine",
            ],
        },
        "auth_required": {"type": "boolean", "default": False},
        "description": {"type": "string"},
        "renders_from": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Service pack names this dashboard renders from (Layer 1).",
        },
        "unknown_url_behavior": {
            "type": "string",
            "enum": ["block", "404"],
            "default": "404",
            "description": "What happens when navigating to a path not in this site.",
        },
        "created_at": {"type": "string"},
    },
}

WEB_PAGE_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": [
        "id",
        "site_id",
        "domain",
        "path",
        "title",
        "page_type",
        "status",
        "content_source",
        "created_at",
    ],
    "properties": {
        "id": {"type": "string"},
        "site_id": {"type": "string", "x-terrarium-ref": "web_site"},
        "domain": {
            "type": "string",
            "description": "Denormalized from web_site for fast URL lookups.",
        },
        "path": {
            "type": "string",
            "description": "URL path, e.g. '/tickets/TK-2847'. Always starts with '/'.",
        },
        "title": {"type": "string"},
        "content_text": {
            "type": "string",
            "description": "Plain text content of the page.",
        },
        "page_type": {
            "type": "string",
            "enum": [
                "entity_view",
                "article",
                "landing",
                "form_page",
                "search_results",
                "error",
            ],
        },
        "links": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "href": {"type": "string"},
                },
            },
            "description": "Navigable links on this page.",
        },
        "forms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "action_type": {
                        "type": "string",
                        "description": "Tool name to invoke, e.g. 'refund_create'.",
                    },
                    "target_service": {
                        "type": "string",
                        "description": "Service pack name, e.g. 'payments'.",
                    },
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "DELETE"],
                    },
                    "fields": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "type": {"type": "string"},
                                "required": {"type": "boolean", "default": False},
                                "label": {"type": "string"},
                                "default_value": {},
                            },
                        },
                    },
                },
            },
            "description": (
                "Interactive forms — submissions become SideEffects "
                "targeting other services via the governance pipeline."
            ),
        },
        "meta_description": {"type": "string"},
        "keywords": {
            "type": "array",
            "items": {"type": "string"},
        },
        "status": {
            "type": "string",
            "enum": ["published", "draft", "archived", "compromised"],
        },
        "content_source": {
            "type": "string",
            "enum": ["compiled", "runtime_generated"],
            "description": "How this page was created.",
        },
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
    },
}

WEB_SESSION_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "actor_id", "status", "created_at"],
    "properties": {
        "id": {"type": "string"},
        "actor_id": {"type": "string"},
        "current_url": {"type": ["string", "null"]},
        "current_page_id": {
            "type": ["string", "null"],
            "x-terrarium-ref": "web_page",
        },
        "history": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Stack of previously visited URLs.",
        },
        "status": {
            "type": "string",
            "enum": ["active", "expired"],
        },
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
    },
}

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

BROWSER_TOOL_DEFINITIONS: list[dict] = [
    # --- 1. web_navigate ---
    {
        "name": "web_navigate",
        "description": (
            "Navigate to a URL and return the page content. Creates a session if none provided."
        ),
        "http_path": "/web/navigate",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {
                    "type": "string",
                    "description": ("The URL to navigate to (e.g. 'dashboard.acme.com/tickets')."),
                },
                "session_id": {
                    "type": "string",
                    "description": "Browser session ID. Auto-created if omitted.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "page": {"type": "object"},
                "session_id": {"type": "string"},
            },
        },
    },
    # --- 2. web_search ---
    {
        "name": "web_search",
        "description": "Search across all published web pages in the world.",
        "http_path": "/web/search",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query string.",
                },
                "page": {
                    "type": "integer",
                    "description": "Page number for pagination.",
                    "default": 1,
                },
                "per_page": {
                    "type": "integer",
                    "description": "Results per page.",
                    "default": 10,
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "results": {"type": "array"},
                "count": {"type": "integer"},
                "next_page": {"type": ["integer", "null"]},
            },
        },
    },
    # --- 3. web_read_page ---
    {
        "name": "web_read_page",
        "description": (
            "Read the full content of the current page (by session) or a specific page (by ID)."
        ),
        "http_path": "/web/page",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID to read current page from.",
                },
                "page_id": {
                    "type": "string",
                    "description": "Page ID to read directly.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "page": {"type": "object"},
            },
        },
    },
    # --- 4. web_click_link ---
    {
        "name": "web_click_link",
        "description": (
            "Follow a link on the current page. Validates the link exists before navigating."
        ),
        "http_path": "/web/click",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["session_id"],
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Browser session ID.",
                },
                "link_url": {
                    "type": "string",
                    "description": "The href of the link to click.",
                },
                "link_index": {
                    "type": "integer",
                    "description": "Zero-based index into the page's links array.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "page": {"type": "object"},
                "session_id": {"type": "string"},
            },
        },
    },
    # --- 5. web_submit_form ---
    {
        "name": "web_submit_form",
        "description": (
            "Submit a form on the current page. The form's action is routed "
            "through the governance pipeline to the target service."
        ),
        "http_path": "/web/submit",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["session_id", "form_id", "form_data"],
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Browser session ID.",
                },
                "form_id": {
                    "type": "string",
                    "description": "ID of the form on the current page.",
                },
                "form_data": {
                    "type": "object",
                    "description": "Key-value pairs for form field values.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "submitted": {"type": "boolean"},
                "action_type": {"type": "string"},
                "target_service": {"type": "string"},
                "message": {"type": "string"},
            },
        },
    },
    # --- 6. web_back ---
    {
        "name": "web_back",
        "description": "Navigate back to the previous page in the session history.",
        "http_path": "/web/back",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["session_id"],
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Browser session ID.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "page": {"type": "object"},
                "session_id": {"type": "string"},
            },
        },
    },
    # --- 7. web_list_sites ---
    {
        "name": "web_list_sites",
        "description": "List all websites available in the world.",
        "http_path": "/web/sites",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "site_type": {
                    "type": "string",
                    "description": "Filter by site type.",
                    "enum": [
                        "internal_dashboard",
                        "knowledge_base",
                        "corporate_website",
                        "search_engine",
                    ],
                },
                "auth_required": {
                    "type": "boolean",
                    "description": "Filter by auth requirement.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "sites": {"type": "array"},
                "count": {"type": "integer"},
            },
        },
    },
    # --- 8. web_get_page ---
    {
        "name": "web_get_page",
        "description": "Get a specific page by its ID.",
        "http_path": "/web/pages/{id}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The page ID to retrieve.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "page": {"type": "object"},
            },
        },
    },
    # --- 9. web_create_session ---
    {
        "name": "web_create_session",
        "description": "Initialize a new browser session for an actor.",
        "http_path": "/web/sessions",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["actor_id"],
            "properties": {
                "actor_id": {
                    "type": "string",
                    "description": "The actor ID to create a session for.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "session": {"type": "object"},
            },
        },
    },
    # --- 10. web_page_modify (Animator/system tool) ---
    {
        "name": "web_page_modify",
        "description": (
            "Modify an existing web page's content. Used by the Animator to "
            "inject compromised content, update articles, or change page data."
        ),
        "http_path": "/web/pages/{id}/modify",
        "http_method": "PUT",
        "parameters": {
            "type": "object",
            "required": ["modification"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Page ID. Alternatively use domain+path.",
                },
                "domain": {
                    "type": "string",
                    "description": "Domain (alternative to id).",
                },
                "path": {
                    "type": "string",
                    "description": "Path (alternative to id).",
                },
                "modification": {
                    "type": "string",
                    "enum": [
                        "inject_content",
                        "update_content",
                        "replace_content",
                        "update_status",
                    ],
                    "description": "Type of modification to apply.",
                },
                "content_text": {
                    "type": "string",
                    "description": "New or injected content text.",
                },
                "injected_content": {
                    "type": "string",
                    "description": "Content to inject (appended for inject_content).",
                },
                "injection_type": {
                    "type": "string",
                    "description": ("Label for the injection type (e.g. 'social_engineering')."),
                },
                "status": {
                    "type": "string",
                    "description": "New status (for update_status modification).",
                    "enum": ["published", "draft", "archived", "compromised"],
                },
                "title": {
                    "type": "string",
                    "description": "New title (optional).",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "page": {"type": "object"},
            },
        },
    },
    # --- 11. web_page_create (Animator/system tool) ---
    {
        "name": "web_page_create",
        "description": (
            "Create a new web page at runtime. Used by the Animator to add "
            "new content (blog posts, competitor updates, etc.)."
        ),
        "http_path": "/web/pages",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": [
                "site_id",
                "domain",
                "path",
                "title",
                "page_type",
                "content_text",
            ],
            "properties": {
                "site_id": {
                    "type": "string",
                    "description": "The web_site this page belongs to.",
                },
                "domain": {"type": "string"},
                "path": {"type": "string"},
                "title": {"type": "string"},
                "page_type": {
                    "type": "string",
                    "enum": [
                        "entity_view",
                        "article",
                        "landing",
                        "form_page",
                        "search_results",
                        "error",
                    ],
                },
                "content_text": {"type": "string"},
                "links": {"type": "array", "items": {"type": "object"}},
                "forms": {"type": "array", "items": {"type": "object"}},
                "meta_description": {"type": "string"},
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "page": {"type": "object"},
            },
        },
    },
]
