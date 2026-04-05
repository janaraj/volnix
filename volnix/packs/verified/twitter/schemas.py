"""Entity schemas and tool definitions for the Twitter/X service pack.

Pure data -- no logic, no imports beyond stdlib.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Entity schemas
# ---------------------------------------------------------------------------

TWEET_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "author_id", "text", "tweet_type", "status", "created_at"],
    "properties": {
        "id": {"type": "string"},
        "author_id": {"type": "string", "x-volnix-ref": "user"},
        "text": {"type": "string", "maxLength": 280},
        "tweet_type": {
            "type": "string",
            "enum": ["original", "reply", "retweet", "quote"],
        },
        "reply_to_tweet_id": {"type": ["string", "null"], "x-volnix-ref": "tweet"},
        "retweet_of_id": {"type": ["string", "null"], "x-volnix-ref": "tweet"},
        "quote_of_id": {"type": ["string", "null"], "x-volnix-ref": "tweet"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "mentions": {"type": "array", "items": {"type": "string"}},
        "media_urls": {"type": "array", "items": {"type": "string"}},
        "link_url": {"type": ["string", "null"]},
        "like_count": {"type": "integer", "default": 0},
        "retweet_count": {"type": "integer", "default": 0},
        "quote_count": {"type": "integer", "default": 0},
        "reply_count": {"type": "integer", "default": 0},
        "view_count": {"type": "integer", "default": 0},
        "bookmark_count": {"type": "integer", "default": 0},
        "is_pinned": {"type": "boolean", "default": False},
        "status": {
            "type": "string",
            "enum": ["published", "deleted"],
        },
        "created_at": {"type": "string"},
    },
}

TWITTER_USER_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "username", "display_name", "status", "created_at"],
    "properties": {
        "id": {"type": "string"},
        "username": {"type": "string"},
        "display_name": {"type": "string"},
        "bio": {"type": "string"},
        "avatar_url": {"type": "string"},
        "location": {"type": "string"},
        "website_url": {"type": ["string", "null"]},
        "follower_count": {"type": "integer", "default": 0},
        "following_count": {"type": "integer", "default": 0},
        "tweet_count": {"type": "integer", "default": 0},
        "verified": {"type": "boolean", "default": False},
        "status": {
            "type": "string",
            "enum": ["active", "suspended", "deactivated"],
        },
        "created_at": {"type": "string"},
    },
}

TWITTER_FOLLOW_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "follower_id", "following_id", "created_at"],
    "properties": {
        "id": {"type": "string"},
        "follower_id": {"type": "string", "x-volnix-ref": "user"},
        "following_id": {"type": "string", "x-volnix-ref": "user"},
        "created_at": {"type": "string"},
    },
}

TWITTER_LIKE_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "user_id", "tweet_id", "created_at"],
    "properties": {
        "id": {"type": "string"},
        "user_id": {"type": "string", "x-volnix-ref": "user"},
        "tweet_id": {"type": "string", "x-volnix-ref": "tweet"},
        "created_at": {"type": "string"},
    },
}

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TWITTER_TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "create_tweet",
        "description": "Create a new tweet.",
        "http_path": "/2/tweets",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["text", "author_id"],
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Tweet text content (max 280 characters).",
                    "maxLength": 280,
                },
                "author_id": {
                    "type": "string",
                    "description": "ID of the user creating the tweet.",
                },
                "media_urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional media URLs to attach.",
                },
                "link_url": {
                    "type": "string",
                    "description": "Optional link URL to include.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "object"},
            },
        },
    },
    {
        "name": "get_tweet",
        "description": "Get tweet details by ID.",
        "http_path": "/2/tweets/{id}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The tweet ID to retrieve.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "object"},
            },
        },
    },
    {
        "name": "delete_tweet",
        "description": "Delete a tweet.",
        "http_path": "/2/tweets/{id}",
        "http_method": "DELETE",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The tweet ID to delete.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "object"},
            },
        },
    },
    {
        "name": "search_recent",
        "description": "Search recent tweets by query.",
        "http_path": "/2/tweets/search/recent",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        'Search query. Supports #hashtag, @mention, "from:username", and free text.'
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                    "default": 10,
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "array"},
                "meta": {"type": "object"},
            },
        },
    },
    {
        "name": "reply",
        "description": "Reply to a tweet.",
        "http_path": "/2/tweets",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["text", "author_id", "in_reply_to_tweet_id"],
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Reply text content (max 280 characters).",
                    "maxLength": 280,
                },
                "author_id": {
                    "type": "string",
                    "description": "ID of the user replying.",
                },
                "in_reply_to_tweet_id": {
                    "type": "string",
                    "description": "ID of the tweet being replied to.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "object"},
            },
        },
    },
    {
        "name": "retweet",
        "description": "Retweet a tweet.",
        "http_path": "/2/users/{id}/retweets",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["user_id", "tweet_id"],
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "ID of the user retweeting.",
                },
                "tweet_id": {
                    "type": "string",
                    "description": "ID of the tweet to retweet.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "object"},
            },
        },
    },
    {
        "name": "unretweet",
        "description": "Undo a retweet.",
        "http_path": "/2/users/{id}/retweets/{tweet_id}",
        "http_method": "DELETE",
        "parameters": {
            "type": "object",
            "required": ["user_id", "tweet_id"],
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "ID of the user who retweeted.",
                },
                "tweet_id": {
                    "type": "string",
                    "description": "ID of the original tweet to unretweet.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "object"},
            },
        },
    },
    {
        "name": "quote_tweet",
        "description": "Quote tweet another tweet.",
        "http_path": "/2/tweets",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["text", "author_id", "quote_tweet_id"],
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Quote tweet text content (max 280 characters).",
                    "maxLength": 280,
                },
                "author_id": {
                    "type": "string",
                    "description": "ID of the user quoting.",
                },
                "quote_tweet_id": {
                    "type": "string",
                    "description": "ID of the tweet being quoted.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "object"},
            },
        },
    },
    {
        "name": "like",
        "description": "Like a tweet.",
        "http_path": "/2/users/{id}/likes",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["user_id", "tweet_id"],
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "ID of the user liking the tweet.",
                },
                "tweet_id": {
                    "type": "string",
                    "description": "ID of the tweet to like.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "object"},
            },
        },
    },
    {
        "name": "unlike",
        "description": "Unlike a tweet.",
        "http_path": "/2/users/{id}/likes/{tweet_id}",
        "http_method": "DELETE",
        "parameters": {
            "type": "object",
            "required": ["user_id", "tweet_id"],
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "ID of the user unliking the tweet.",
                },
                "tweet_id": {
                    "type": "string",
                    "description": "ID of the tweet to unlike.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "object"},
            },
        },
    },
    {
        "name": "follow",
        "description": "Follow a user.",
        "http_path": "/2/users/{id}/following",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["user_id", "target_user_id"],
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "ID of the user who wants to follow.",
                },
                "target_user_id": {
                    "type": "string",
                    "description": "ID of the user to follow.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "object"},
            },
        },
    },
    {
        "name": "unfollow",
        "description": "Unfollow a user.",
        "http_path": "/2/users/{id}/following/{target_id}",
        "http_method": "DELETE",
        "parameters": {
            "type": "object",
            "required": ["user_id", "target_user_id"],
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "ID of the user who wants to unfollow.",
                },
                "target_user_id": {
                    "type": "string",
                    "description": "ID of the user to unfollow.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "object"},
            },
        },
    },
    {
        "name": "get_followers",
        "description": "List followers of a user.",
        "http_path": "/2/users/{id}/followers",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The user ID whose followers to list.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                    "default": 20,
                },
                "pagination_token": {
                    "type": "string",
                    "description": "Token for paginating through results.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "array"},
                "meta": {"type": "object"},
            },
        },
    },
    {
        "name": "get_following",
        "description": "List users that a user is following.",
        "http_path": "/2/users/{id}/following",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The user ID whose following list to retrieve.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                    "default": 20,
                },
                "pagination_token": {
                    "type": "string",
                    "description": "Token for paginating through results.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "array"},
                "meta": {"type": "object"},
            },
        },
    },
    {
        "name": "get_user",
        "description": "Get user profile by ID.",
        "http_path": "/2/users/{id}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The user ID to retrieve.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "object"},
            },
        },
    },
    {
        "name": "user_tweets",
        "description": "Get a user's tweet timeline.",
        "http_path": "/2/users/{id}/tweets",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The user ID whose tweets to retrieve.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                    "default": 20,
                },
                "pagination_token": {
                    "type": "string",
                    "description": "Token for paginating through results.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "array"},
                "meta": {"type": "object"},
            },
        },
    },
]
