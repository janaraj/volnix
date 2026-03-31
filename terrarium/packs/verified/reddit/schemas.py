"""Entity schemas and tool definitions for the Reddit service pack.

Pure data -- no logic, no imports beyond stdlib.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Entity schemas
# ---------------------------------------------------------------------------

SUBREDDIT_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "name", "display_name", "status", "created_at"],
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "display_name": {"type": "string"},
        "description": {"type": "string"},
        "rules": {"type": "array", "items": {"type": "string"}},
        "subscriber_count": {"type": "integer", "default": 0},
        "moderator_ids": {
            "type": "array",
            "items": {"type": "string", "x-terrarium-ref": "reddit_user"},
        },
        "topics": {"type": "array", "items": {"type": "string"}},
        "post_types_allowed": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["text", "link", "image", "poll"],
            },
        },
        "visibility": {
            "type": "string",
            "enum": ["public", "restricted", "private"],
            "default": "public",
        },
        "status": {
            "type": "string",
            "enum": ["active", "quarantined", "banned"],
        },
        "created_at": {"type": "string"},
    },
}

REDDIT_POST_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": [
        "id",
        "subreddit_id",
        "author_id",
        "title",
        "post_type",
        "status",
        "created_at",
    ],
    "properties": {
        "id": {"type": "string"},
        "subreddit_id": {"type": "string", "x-terrarium-ref": "subreddit"},
        "author_id": {"type": "string", "x-terrarium-ref": "reddit_user"},
        "title": {"type": "string"},
        "body": {"type": "string"},
        "url": {"type": ["string", "null"]},
        "post_type": {
            "type": "string",
            "enum": ["text", "link", "image", "crosspost", "poll"],
        },
        "flair": {"type": ["string", "null"]},
        "upvotes": {"type": "integer", "default": 1},
        "downvotes": {"type": "integer", "default": 0},
        "score": {"type": "integer"},
        "comment_count": {"type": "integer", "default": 0},
        "crosspost_parent_id": {
            "type": ["string", "null"],
            "x-terrarium-ref": "reddit_post",
        },
        "is_pinned": {"type": "boolean"},
        "is_locked": {"type": "boolean"},
        "is_nsfw": {"type": "boolean"},
        "is_spoiler": {"type": "boolean"},
        "awards": {"type": "array", "items": {"type": "string"}},
        "status": {
            "type": "string",
            "enum": ["published", "removed", "spam"],
        },
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
    },
}

REDDIT_COMMENT_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "post_id", "author_id", "body", "status", "created_at"],
    "properties": {
        "id": {"type": "string"},
        "post_id": {"type": "string", "x-terrarium-ref": "reddit_post"},
        "parent_id": {"type": ["string", "null"]},
        "author_id": {"type": "string", "x-terrarium-ref": "reddit_user"},
        "body": {"type": "string"},
        "upvotes": {"type": "integer", "default": 1},
        "downvotes": {"type": "integer", "default": 0},
        "score": {"type": "integer"},
        "depth": {"type": "integer", "default": 0},
        "reply_count": {"type": "integer", "default": 0},
        "is_stickied": {"type": "boolean"},
        "status": {
            "type": "string",
            "enum": ["published", "removed", "spam"],
        },
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
    },
}

REDDIT_USER_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "username", "status", "created_at"],
    "properties": {
        "id": {"type": "string"},
        "username": {"type": "string"},
        "display_name": {"type": "string"},
        "bio": {"type": "string"},
        "avatar_url": {"type": "string"},
        "post_karma": {"type": "integer", "default": 0},
        "comment_karma": {"type": "integer", "default": 0},
        "is_moderator": {"type": "boolean"},
        "subscribed_subreddit_ids": {
            "type": "array",
            "items": {"type": "string", "x-terrarium-ref": "subreddit"},
        },
        "status": {
            "type": "string",
            "enum": ["active", "suspended", "deleted"],
        },
        "created_at": {"type": "string"},
    },
}

REDDIT_VOTE_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "user_id", "target_id", "target_type", "direction"],
    "properties": {
        "id": {"type": "string"},
        "user_id": {"type": "string", "x-terrarium-ref": "reddit_user"},
        "target_id": {"type": "string"},
        "target_type": {
            "type": "string",
            "enum": ["post", "comment"],
        },
        "direction": {
            "type": "string",
            "enum": ["up", "down"],
        },
    },
}

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

REDDIT_TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "subreddits_search",
        "description": "Search subreddits by query string, optionally filter by topic.",
        "http_path": "/subreddits/search",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for subreddit name or description.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                    "default": 25,
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of results to skip for pagination.",
                    "default": 0,
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "subreddits": {"type": "array"},
                "count": {"type": "integer"},
            },
        },
    },
    {
        "name": "subreddit_about",
        "description": "Get details about a specific subreddit.",
        "http_path": "/r/{subreddit}/about",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["subreddit"],
            "properties": {
                "subreddit": {
                    "type": "string",
                    "description": "Subreddit name (lowercase, without r/ prefix).",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "subreddit": {"type": "object"},
            },
        },
    },
    {
        "name": "subscribe",
        "description": "Subscribe the current user to a subreddit.",
        "http_path": "/api/subscribe",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["subreddit", "user_id"],
            "properties": {
                "subreddit": {
                    "type": "string",
                    "description": "Subreddit name to subscribe to.",
                },
                "user_id": {
                    "type": "string",
                    "description": "ID of the user subscribing.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
            },
        },
    },
    {
        "name": "unsubscribe",
        "description": "Unsubscribe the current user from a subreddit.",
        "http_path": "/api/unsubscribe",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["subreddit", "user_id"],
            "properties": {
                "subreddit": {
                    "type": "string",
                    "description": "Subreddit name to unsubscribe from.",
                },
                "user_id": {
                    "type": "string",
                    "description": "ID of the user unsubscribing.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
            },
        },
    },
    {
        "name": "submit",
        "description": "Create a new post (submission) in a subreddit.",
        "http_path": "/api/submit",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["sr", "title", "kind", "author_id"],
            "properties": {
                "sr": {
                    "type": "string",
                    "description": "Subreddit name to post in.",
                },
                "title": {
                    "type": "string",
                    "description": "Title of the post.",
                },
                "text": {
                    "type": "string",
                    "description": "Body text for self/text posts.",
                },
                "url": {
                    "type": "string",
                    "description": "URL for link posts.",
                },
                "kind": {
                    "type": "string",
                    "description": "Post type.",
                    "enum": ["text", "link", "image"],
                },
                "flair": {
                    "type": "string",
                    "description": "Flair to apply to the post.",
                },
                "author_id": {
                    "type": "string",
                    "description": "ID of the user creating the post.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "post": {"type": "object"},
            },
        },
    },
    {
        "name": "post_detail",
        "description": "Get details of a specific post by ID.",
        "http_path": "/comments/{id}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The post ID to retrieve.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "post": {"type": "object"},
            },
        },
    },
    {
        "name": "subreddit_hot",
        "description": "List hot posts in a subreddit, sorted by hotness score.",
        "http_path": "/r/{subreddit}/hot",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["subreddit"],
            "properties": {
                "subreddit": {
                    "type": "string",
                    "description": "Subreddit name.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of posts to return.",
                    "default": 25,
                },
                "after": {
                    "type": "string",
                    "description": "Cursor for pagination (post ID).",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "posts": {"type": "array"},
                "count": {"type": "integer"},
                "after": {"type": ["string", "null"]},
            },
        },
    },
    {
        "name": "subreddit_new",
        "description": "List newest posts in a subreddit, sorted by creation time.",
        "http_path": "/r/{subreddit}/new",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["subreddit"],
            "properties": {
                "subreddit": {
                    "type": "string",
                    "description": "Subreddit name.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of posts to return.",
                    "default": 25,
                },
                "after": {
                    "type": "string",
                    "description": "Cursor for pagination (post ID).",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "posts": {"type": "array"},
                "count": {"type": "integer"},
                "after": {"type": ["string", "null"]},
            },
        },
    },
    {
        "name": "subreddit_top",
        "description": "List top posts in a subreddit, sorted by score.",
        "http_path": "/r/{subreddit}/top",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["subreddit"],
            "properties": {
                "subreddit": {
                    "type": "string",
                    "description": "Subreddit name.",
                },
                "t": {
                    "type": "string",
                    "description": "Time filter for top posts.",
                    "enum": ["hour", "day", "week", "month", "year", "all"],
                    "default": "all",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of posts to return.",
                    "default": 25,
                },
                "after": {
                    "type": "string",
                    "description": "Cursor for pagination (post ID).",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "posts": {"type": "array"},
                "count": {"type": "integer"},
                "after": {"type": ["string", "null"]},
            },
        },
    },
    {
        "name": "search",
        "description": "Search posts across Reddit or within a specific subreddit.",
        "http_path": "/search",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["q"],
            "properties": {
                "q": {
                    "type": "string",
                    "description": "Search query string.",
                },
                "sr": {
                    "type": "string",
                    "description": "Restrict search to a specific subreddit name.",
                },
                "sort": {
                    "type": "string",
                    "description": "Sort order for results.",
                    "enum": ["relevance", "hot", "top", "new"],
                    "default": "relevance",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                    "default": 25,
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "posts": {"type": "array"},
                "count": {"type": "integer"},
            },
        },
    },
    {
        "name": "remove",
        "description": "Remove a post or comment (moderator action).",
        "http_path": "/api/remove",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["id", "type"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "ID of the post or comment to remove.",
                },
                "type": {
                    "type": "string",
                    "description": "Type of content to remove.",
                    "enum": ["post", "comment"],
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
            },
        },
    },
    {
        "name": "comment",
        "description": "Create a comment on a post or reply to another comment.",
        "http_path": "/api/comment",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["parent", "text", "author_id"],
            "properties": {
                "parent": {
                    "type": "string",
                    "description": (
                        "Fullname of the parent: t3_<id> for a post, t1_<id> for a comment."
                    ),
                },
                "text": {
                    "type": "string",
                    "description": "Comment body text.",
                },
                "author_id": {
                    "type": "string",
                    "description": "ID of the user authoring the comment.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "comment": {"type": "object"},
            },
        },
    },
    {
        "name": "post_comments",
        "description": "List comments for a specific post.",
        "http_path": "/comments/{id}/comments",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The post ID whose comments to list.",
                },
                "sort": {
                    "type": "string",
                    "description": "Sort order for comments.",
                    "enum": ["best", "top", "new"],
                    "default": "best",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "comments": {"type": "array"},
                "count": {"type": "integer"},
            },
        },
    },
    {
        "name": "vote",
        "description": "Vote on a post or comment.",
        "http_path": "/api/vote",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["id", "dir", "user_id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "ID of the post or comment to vote on.",
                },
                "dir": {
                    "type": "integer",
                    "description": "Vote direction: 1 for upvote, 0 to unvote, -1 for downvote.",
                    "enum": [1, 0, -1],
                },
                "user_id": {
                    "type": "string",
                    "description": "ID of the user voting.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
            },
        },
    },
    {
        "name": "user_about",
        "description": "Get details about a specific user by username.",
        "http_path": "/user/{username}/about",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["username"],
            "properties": {
                "username": {
                    "type": "string",
                    "description": "The username to look up.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "user": {"type": "object"},
            },
        },
    },
    {
        "name": "user_submitted",
        "description": "List posts submitted by a specific user.",
        "http_path": "/user/{username}/submitted",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["username"],
            "properties": {
                "username": {
                    "type": "string",
                    "description": "The username whose posts to list.",
                },
                "sort": {
                    "type": "string",
                    "description": "Sort order for results.",
                    "enum": ["hot", "new", "top"],
                    "default": "new",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of posts to return.",
                    "default": 25,
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "posts": {"type": "array"},
                "count": {"type": "integer"},
            },
        },
    },
    {
        "name": "best",
        "description": "Get the user's home feed with posts from subscribed subreddits.",
        "http_path": "/best",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["user_id"],
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "ID of the user to get the feed for.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of posts to return.",
                    "default": 25,
                },
                "after": {
                    "type": "string",
                    "description": "Cursor for pagination (post ID).",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "posts": {"type": "array"},
                "count": {"type": "integer"},
                "after": {"type": ["string", "null"]},
            },
        },
    },
    {
        "name": "popular",
        "description": "Get trending posts from all public subreddits.",
        "http_path": "/r/popular",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of posts to return.",
                    "default": 25,
                },
                "after": {
                    "type": "string",
                    "description": "Cursor for pagination (post ID).",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "posts": {"type": "array"},
                "count": {"type": "integer"},
                "after": {"type": ["string", "null"]},
            },
        },
    },
]
