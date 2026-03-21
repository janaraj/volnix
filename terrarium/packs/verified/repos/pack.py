"""Repos service pack (Tier 1 -- verified).

Provides the canonical tool surface for code-devops services:
list branches, create PR, list PRs, merge PR, and add review.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.base import ServicePack


class ReposPack(ServicePack):
    """Verified pack for code repository / DevOps services.

    Tools: repo_list_branches, repo_create_pr, repo_list_prs,
    repo_merge_pr, repo_add_review.
    """

    pack_name: ClassVar[str] = "repos"
    category: ClassVar[str] = "code_devops"
    fidelity_tier: ClassVar[int] = 1

    def get_tools(self) -> list[dict]:
        """Return the repos tool manifest."""
        ...

    def get_entity_schemas(self) -> dict:
        """Return entity schemas (repo, branch, pull_request, review)."""
        ...

    def get_state_machines(self) -> dict:
        """Return state machines for repo entities."""
        ...

    async def handle_action(
        self,
        action: ToolName,
        input_data: dict,
        state: dict,
    ) -> ResponseProposal:
        """Dispatch to the appropriate repos action handler."""
        ...
