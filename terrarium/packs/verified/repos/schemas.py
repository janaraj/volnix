"""Entity schemas and tool definitions for the repos service pack.

Pure data -- no logic, no imports beyond stdlib.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Entity schemas
# ---------------------------------------------------------------------------

REPOSITORY_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "name", "full_name", "owner"],
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "full_name": {"type": "string"},
        "owner": {
            "type": "object",
            "properties": {
                "login": {"type": "string"},
                "type": {"type": "string"},
            },
        },
        "description": {"type": "string"},
        "private": {"type": "boolean"},
        "default_branch": {"type": "string"},
        "language": {"type": "string"},
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
        "pushed_at": {"type": "string"},
        "stargazers_count": {"type": "integer", "minimum": 0},
        "forks_count": {"type": "integer", "minimum": 0},
        "open_issues_count": {"type": "integer", "minimum": 0},
        "visibility": {"type": "string"},
    },
}

ISSUE_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "number",
    "required": ["number", "title", "state", "user"],
    "properties": {
        "number": {"type": "integer"},
        "title": {"type": "string"},
        "body": {"type": "string"},
        "state": {
            "type": "string",
            "enum": ["open", "closed"],
        },
        "state_reason": {"type": "string"},
        "labels": {
            "type": "array",
            "items": {"type": "string"},
        },
        "assignees": {
            "type": "array",
            "items": {"type": "string"},
        },
        "user": {
            "type": "object",
            "properties": {
                "login": {"type": "string"},
            },
        },
        "comments": {"type": "integer", "minimum": 0},
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
        "closed_at": {"type": "string"},
        "locked": {"type": "boolean"},
    },
}

PULL_REQUEST_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "number",
    "required": ["number", "title", "state", "head", "base", "user"],
    "properties": {
        "number": {"type": "integer"},
        "title": {"type": "string"},
        "body": {"type": "string"},
        "state": {
            "type": "string",
            "enum": ["open", "closed", "merged"],
        },
        "head": {
            "type": "object",
            "properties": {
                "ref": {"type": "string"},
                "sha": {"type": "string"},
            },
        },
        "base": {
            "type": "object",
            "properties": {
                "ref": {"type": "string"},
                "sha": {"type": "string"},
            },
        },
        "user": {
            "type": "object",
            "properties": {
                "login": {"type": "string"},
            },
        },
        "mergeable": {"type": "boolean"},
        "merged": {"type": "boolean"},
        "merged_at": {"type": "string"},
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
    },
}

COMMIT_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "sha",
    "required": ["sha", "message"],
    "properties": {
        "sha": {"type": "string"},
        "message": {"type": "string"},
        "author": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "email": {"type": "string"},
                "date": {"type": "string"},
            },
        },
        "committer": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "email": {"type": "string"},
                "date": {"type": "string"},
            },
        },
        "url": {"type": "string"},
    },
}

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

REPOS_TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "create_issue",
        "description": "Create a new issue in a GitHub repository.",
        "http_path": "/repos/{owner}/{repo}/issues",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["owner", "repo", "title"],
            "properties": {
                "owner": {"type": "string", "description": "Repository owner (user or org)."},
                "repo": {"type": "string", "description": "Repository name."},
                "title": {"type": "string", "description": "Issue title."},
                "body": {"type": "string", "description": "Issue body text."},
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Labels to assign to the issue.",
                },
                "assignees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Usernames to assign to the issue.",
                },
            },
        },
    },
    {
        "name": "list_issues",
        "description": "List issues in a GitHub repository.",
        "http_path": "/repos/{owner}/{repo}/issues",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["owner", "repo"],
            "properties": {
                "owner": {"type": "string", "description": "Repository owner (user or org)."},
                "repo": {"type": "string", "description": "Repository name."},
                "state": {
                    "type": "string",
                    "description": "Filter by state.",
                    "default": "open",
                },
                "labels": {
                    "type": "string",
                    "description": "Comma-separated list of label names to filter by.",
                },
                "assignee": {
                    "type": "string",
                    "description": "Filter by assignee username.",
                },
                "per_page": {
                    "type": "integer",
                    "description": "Number of results per page.",
                    "default": 30,
                },
                "page": {
                    "type": "integer",
                    "description": "Page number of results.",
                },
            },
        },
    },
    {
        "name": "get_issue",
        "description": "Get a single issue by number.",
        "http_path": "/repos/{owner}/{repo}/issues/{number}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["owner", "repo", "number"],
            "properties": {
                "owner": {"type": "string", "description": "Repository owner (user or org)."},
                "repo": {"type": "string", "description": "Repository name."},
                "number": {"type": "integer", "description": "Issue number."},
            },
        },
    },
    {
        "name": "update_issue",
        "description": "Update an existing issue.",
        "http_path": "/repos/{owner}/{repo}/issues/{number}",
        "http_method": "PATCH",
        "parameters": {
            "type": "object",
            "required": ["owner", "repo", "number"],
            "properties": {
                "owner": {"type": "string", "description": "Repository owner (user or org)."},
                "repo": {"type": "string", "description": "Repository name."},
                "number": {"type": "integer", "description": "Issue number."},
                "title": {"type": "string", "description": "New title."},
                "body": {"type": "string", "description": "New body text."},
                "state": {"type": "string", "description": "New state (open or closed)."},
                "state_reason": {
                    "type": "string",
                    "description": "Reason for state change (completed, not_planned, reopened).",
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Replace labels.",
                },
                "assignees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Replace assignees.",
                },
            },
        },
    },
    {
        "name": "add_issue_comment",
        "description": "Add a comment to an issue.",
        "http_path": "/repos/{owner}/{repo}/issues/{number}/comments",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["owner", "repo", "number", "body"],
            "properties": {
                "owner": {"type": "string", "description": "Repository owner (user or org)."},
                "repo": {"type": "string", "description": "Repository name."},
                "number": {"type": "integer", "description": "Issue number."},
                "body": {"type": "string", "description": "Comment body text."},
            },
        },
    },
    {
        "name": "create_pull_request",
        "description": "Create a new pull request.",
        "http_path": "/repos/{owner}/{repo}/pulls",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["owner", "repo", "title", "head", "base"],
            "properties": {
                "owner": {"type": "string", "description": "Repository owner (user or org)."},
                "repo": {"type": "string", "description": "Repository name."},
                "title": {"type": "string", "description": "Pull request title."},
                "body": {"type": "string", "description": "Pull request body text."},
                "head": {
                    "type": "string",
                    "description": "The branch (or user:branch) where changes are implemented.",
                },
                "base": {
                    "type": "string",
                    "description": "The branch you want the changes pulled into.",
                },
            },
        },
    },
    {
        "name": "list_pull_requests",
        "description": "List pull requests in a repository.",
        "http_path": "/repos/{owner}/{repo}/pulls",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["owner", "repo"],
            "properties": {
                "owner": {"type": "string", "description": "Repository owner (user or org)."},
                "repo": {"type": "string", "description": "Repository name."},
                "state": {
                    "type": "string",
                    "description": "Filter by state (open, closed, all).",
                    "default": "open",
                },
                "head": {
                    "type": "string",
                    "description": "Filter by head branch (user:ref-name or ref-name).",
                },
                "base": {
                    "type": "string",
                    "description": "Filter by base branch name.",
                },
                "per_page": {
                    "type": "integer",
                    "description": "Number of results per page.",
                },
            },
        },
    },
    {
        "name": "get_pull_request",
        "description": "Get a single pull request by number.",
        "http_path": "/repos/{owner}/{repo}/pulls/{number}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["owner", "repo", "number"],
            "properties": {
                "owner": {"type": "string", "description": "Repository owner (user or org)."},
                "repo": {"type": "string", "description": "Repository name."},
                "number": {"type": "integer", "description": "Pull request number."},
            },
        },
    },
    {
        "name": "merge_pull_request",
        "description": "Merge a pull request.",
        "http_path": "/repos/{owner}/{repo}/pulls/{number}/merge",
        "http_method": "PUT",
        "parameters": {
            "type": "object",
            "required": ["owner", "repo", "number"],
            "properties": {
                "owner": {"type": "string", "description": "Repository owner (user or org)."},
                "repo": {"type": "string", "description": "Repository name."},
                "number": {"type": "integer", "description": "Pull request number."},
                "commit_title": {
                    "type": "string",
                    "description": "Title for the merge commit.",
                },
                "merge_method": {
                    "type": "string",
                    "description": "Merge method to use.",
                    "enum": ["merge", "squash", "rebase"],
                },
            },
        },
    },
    {
        "name": "list_commits",
        "description": "List commits in a repository.",
        "http_path": "/repos/{owner}/{repo}/commits",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["owner", "repo"],
            "properties": {
                "owner": {"type": "string", "description": "Repository owner (user or org)."},
                "repo": {"type": "string", "description": "Repository name."},
                "sha": {
                    "type": "string",
                    "description": "SHA or branch to start listing commits from.",
                },
                "per_page": {
                    "type": "integer",
                    "description": "Number of results per page.",
                },
            },
        },
    },
]
