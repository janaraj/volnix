"""Repos service pack (Tier 1 -- verified).

Provides the canonical tool surface for code-category services:
GitHub-aligned issue, pull request, commit, and review operations.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.base import ActionHandler, ServicePack
from terrarium.packs.verified.github.handlers import (
    handle_add_issue_comment,
    handle_create_issue,
    handle_create_pull_request,
    handle_create_pull_request_review,
    handle_get_issue,
    handle_get_pull_request,
    handle_get_pull_request_files,
    handle_list_commits,
    handle_list_issue_comments,
    handle_list_issues,
    handle_list_pull_requests,
    handle_merge_pull_request,
    handle_search_issues,
    handle_update_issue,
    handle_update_pull_request,
)
from terrarium.packs.verified.github.schemas import (
    COMMIT_ENTITY_SCHEMA,
    ISSUE_COMMENT_ENTITY_SCHEMA,
    ISSUE_ENTITY_SCHEMA,
    PR_FILE_ENTITY_SCHEMA,
    PULL_REQUEST_ENTITY_SCHEMA,
    REPOS_TOOL_DEFINITIONS,
    REPOSITORY_ENTITY_SCHEMA,
    REVIEW_ENTITY_SCHEMA,
)
from terrarium.packs.verified.github.state_machines import (
    ISSUE_TRANSITIONS,
    PULL_REQUEST_TRANSITIONS,
    REVIEW_TRANSITIONS,
)


class ReposPack(ServicePack):
    """Verified pack for code repository services (GitHub-aligned).

    Tools: create_issue, list_issues, get_issue, update_issue,
    add_issue_comment, list_issue_comments, search_issues,
    create_pull_request, list_pull_requests, get_pull_request,
    update_pull_request, merge_pull_request, create_pull_request_review,
    get_pull_request_files, list_commits.
    """

    pack_name: ClassVar[str] = "github"
    category: ClassVar[str] = "code"
    fidelity_tier: ClassVar[int] = 1

    _handlers: ClassVar[dict[str, ActionHandler]] = {
        "create_issue": handle_create_issue,
        "list_issues": handle_list_issues,
        "get_issue": handle_get_issue,
        "update_issue": handle_update_issue,
        "add_issue_comment": handle_add_issue_comment,
        "list_issue_comments": handle_list_issue_comments,
        "search_issues": handle_search_issues,
        "create_pull_request": handle_create_pull_request,
        "list_pull_requests": handle_list_pull_requests,
        "get_pull_request": handle_get_pull_request,
        "update_pull_request": handle_update_pull_request,
        "merge_pull_request": handle_merge_pull_request,
        "create_pull_request_review": handle_create_pull_request_review,
        "get_pull_request_files": handle_get_pull_request_files,
        "list_commits": handle_list_commits,
    }

    def get_tools(self) -> list[dict]:
        """Return the repos tool manifest."""
        return list(REPOS_TOOL_DEFINITIONS)

    def get_entity_schemas(self) -> dict:
        """Return entity schemas for all repo entity types."""
        return {
            "repository": REPOSITORY_ENTITY_SCHEMA,
            "issue": ISSUE_ENTITY_SCHEMA,
            "pull_request": PULL_REQUEST_ENTITY_SCHEMA,
            "commit": COMMIT_ENTITY_SCHEMA,
            "review": REVIEW_ENTITY_SCHEMA,
            "issue_comment": ISSUE_COMMENT_ENTITY_SCHEMA,
            "pr_file": PR_FILE_ENTITY_SCHEMA,
        }

    def get_state_machines(self) -> dict:
        """Return state machines for repo entities."""
        return {
            "issue": {"transitions": ISSUE_TRANSITIONS},
            "pull_request": {"transitions": PULL_REQUEST_TRANSITIONS},
            "review": {"transitions": REVIEW_TRANSITIONS},
        }

    async def handle_action(
        self,
        action: ToolName,
        input_data: dict,
        state: dict,
    ) -> ResponseProposal:
        """Dispatch to the appropriate repos action handler."""
        return await self.dispatch_action(action, input_data, state)
