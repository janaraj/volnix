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
        "node_id": {"type": "string"},
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
        "topics": {
            "type": "array",
            "items": {"type": "string"},
        },
        "archived": {"type": "boolean"},
        "disabled": {"type": "boolean"},
        "has_issues": {"type": "boolean"},
        "has_projects": {"type": "boolean"},
        "has_wiki": {"type": "boolean"},
        "license": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "name": {"type": "string"},
                "spdx_id": {"type": "string"},
            },
        },
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
        "node_id": {"type": "string"},
        "title": {"type": "string"},
        "body": {"type": ["string", "null"]},
        "state": {
            "type": "string",
            "enum": ["open", "closed"],
        },
        "state_reason": {"type": ["string", "null"]},
        "labels": {
            "type": "array",
            "items": {"type": ["string", "object"]},
        },
        "assignees": {
            "type": "array",
            "items": {"type": ["string", "object"]},
        },
        "milestone": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "title": {"type": "string"},
                "number": {"type": "integer"},
            },
        },
        "user": {
            "type": "object",
            "properties": {
                "login": {"type": "string"},
            },
        },
        "reactions": {
            "type": "object",
            "properties": {
                "total_count": {"type": "integer", "minimum": 0},
                "+1": {"type": "integer", "minimum": 0},
                "-1": {"type": "integer", "minimum": 0},
                "laugh": {"type": "integer", "minimum": 0},
                "hooray": {"type": "integer", "minimum": 0},
                "confused": {"type": "integer", "minimum": 0},
                "heart": {"type": "integer", "minimum": 0},
                "rocket": {"type": "integer", "minimum": 0},
                "eyes": {"type": "integer", "minimum": 0},
            },
        },
        "comments": {"type": "integer", "minimum": 0},
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
        "closed_at": {"type": ["string", "null"]},
        "locked": {"type": "boolean"},
    },
}

PULL_REQUEST_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "number",
    "required": ["number", "title", "state", "head", "base", "user"],
    "properties": {
        "number": {"type": "integer"},
        "node_id": {"type": "string"},
        "title": {"type": "string"},
        "body": {"type": ["string", "null"]},
        "state": {
            "type": "string",
            "enum": ["open", "closed", "merged"],
        },
        "draft": {"type": "boolean"},
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
        "mergeable_state": {
            "type": "string",
            "enum": ["clean", "dirty", "unstable", "unknown"],
        },
        "merged": {"type": "boolean"},
        "merged_at": {"type": ["string", "null"]},
        "additions": {"type": "integer", "minimum": 0},
        "deletions": {"type": "integer", "minimum": 0},
        "changed_files": {"type": "integer", "minimum": 0},
        "commits": {"type": "integer", "minimum": 0},
        "review_comments": {"type": "integer", "minimum": 0},
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
        "node_id": {"type": "string"},
        "html_url": {"type": "string"},
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
        "parents": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sha": {"type": "string"},
                    "url": {"type": "string"},
                },
            },
        },
        "stats": {
            "type": "object",
            "properties": {
                "additions": {"type": "integer", "minimum": 0},
                "deletions": {"type": "integer", "minimum": 0},
                "total": {"type": "integer", "minimum": 0},
            },
        },
        "url": {"type": "string"},
    },
}

REVIEW_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "pull_number", "user", "state"],
    "properties": {
        "id": {"type": "string"},
        "pull_number": {"type": "integer"},
        "user": {
            "type": "object",
            "properties": {
                "login": {"type": "string"},
            },
        },
        "state": {
            "type": "string",
            "enum": [
                "APPROVED",
                "CHANGES_REQUESTED",
                "COMMENTED",
                "DISMISSED",
                "PENDING",
            ],
        },
        "body": {"type": "string"},
        "submitted_at": {"type": "string"},
        "commit_id": {"type": "string"},
    },
}

ISSUE_COMMENT_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "issue_number", "body"],
    "properties": {
        "id": {"type": "string"},
        "issue_number": {"type": "integer"},
        "body": {"type": "string"},
        "user": {
            "type": "object",
            "properties": {
                "login": {"type": "string"},
            },
        },
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
    },
}

PR_FILE_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "sha",
    "required": ["sha", "filename", "status"],
    "properties": {
        "sha": {"type": "string"},
        "filename": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["added", "removed", "modified", "renamed", "copied", "changed", "unchanged"],
        },
        "additions": {"type": "integer", "minimum": 0},
        "deletions": {"type": "integer", "minimum": 0},
        "changes": {"type": "integer", "minimum": 0},
        "patch": {"type": "string"},
        "previous_filename": {"type": "string"},
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
        "response_schema": {"type": "object"},
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
        "response_schema": {
            "type": "object",
            "properties": {
                "items": {"type": "array"},
                "total_count": {"type": "integer"},
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
        "response_schema": {"type": "object"},
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
        "response_schema": {"type": "object"},
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
        "response_schema": {"type": "object"},
    },
    {
        "name": "list_issue_comments",
        "description": "List all comments on an issue.",
        "http_path": "/repos/{owner}/{repo}/issues/{number}/comments",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["owner", "repo", "number"],
            "properties": {
                "owner": {"type": "string", "description": "Repository owner (user or org)."},
                "repo": {"type": "string", "description": "Repository name."},
                "number": {"type": "integer", "description": "Issue number."},
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
        "response_schema": {
            "type": "object",
            "properties": {
                "items": {"type": "array"},
                "total_count": {"type": "integer"},
            },
        },
    },
    {
        "name": "search_issues",
        "description": "Search across issues and pull requests with a query string.",
        "http_path": "/search/issues",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["q"],
            "properties": {
                "q": {
                    "type": "string",
                    "description": "Search query (GitHub search syntax).",
                },
                "sort": {
                    "type": "string",
                    "description": "Sort field (comments, reactions, created, updated).",
                },
                "order": {
                    "type": "string",
                    "description": "Sort order (asc or desc).",
                    "default": "desc",
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
        "response_schema": {
            "type": "object",
            "properties": {
                "total_count": {"type": "integer"},
                "incomplete_results": {"type": "boolean"},
                "items": {"type": "array"},
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
        "response_schema": {"type": "object"},
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
        "response_schema": {
            "type": "object",
            "properties": {
                "items": {"type": "array"},
                "total_count": {"type": "integer"},
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
        "response_schema": {"type": "object"},
    },
    {
        "name": "update_pull_request",
        "description": "Update an existing pull request.",
        "http_path": "/repos/{owner}/{repo}/pulls/{number}",
        "http_method": "PATCH",
        "parameters": {
            "type": "object",
            "required": ["owner", "repo", "number"],
            "properties": {
                "owner": {"type": "string", "description": "Repository owner (user or org)."},
                "repo": {"type": "string", "description": "Repository name."},
                "number": {"type": "integer", "description": "Pull request number."},
                "title": {"type": "string", "description": "New title."},
                "body": {"type": "string", "description": "New body text."},
                "state": {
                    "type": "string",
                    "description": "New state (open or closed).",
                },
                "base": {
                    "type": "string",
                    "description": "New base branch name.",
                },
            },
        },
        "response_schema": {"type": "object"},
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
        "response_schema": {
            "type": "object",
            "properties": {
                "merged": {"type": "boolean"},
                "message": {"type": "string"},
                "sha": {"type": "string"},
                "commit_title": {"type": "string"},
            },
        },
    },
    {
        "name": "create_pull_request_review",
        "description": "Create a review on a pull request.",
        "http_path": "/repos/{owner}/{repo}/pulls/{number}/reviews",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["owner", "repo", "number", "event"],
            "properties": {
                "owner": {"type": "string", "description": "Repository owner (user or org)."},
                "repo": {"type": "string", "description": "Repository name."},
                "number": {"type": "integer", "description": "Pull request number."},
                "body": {"type": "string", "description": "Review body text."},
                "event": {
                    "type": "string",
                    "description": "Review action (APPROVE, REQUEST_CHANGES, COMMENT).",
                    "enum": ["APPROVE", "REQUEST_CHANGES", "COMMENT"],
                },
            },
        },
        "response_schema": {"type": "object"},
    },
    {
        "name": "get_pull_request_files",
        "description": "List files changed in a pull request.",
        "http_path": "/repos/{owner}/{repo}/pulls/{number}/files",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["owner", "repo", "number"],
            "properties": {
                "owner": {"type": "string", "description": "Repository owner (user or org)."},
                "repo": {"type": "string", "description": "Repository name."},
                "number": {"type": "integer", "description": "Pull request number."},
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
        "response_schema": {
            "type": "object",
            "properties": {
                "items": {"type": "array"},
                "total_count": {"type": "integer"},
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
        "response_schema": {
            "type": "object",
            "properties": {
                "items": {"type": "array"},
                "total_count": {"type": "integer"},
            },
        },
    },
]
