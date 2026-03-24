"""Tests for terrarium.packs.verified.repos -- ReposPack through pack's own handle_action."""

import pytest

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.verified.repos.pack import ReposPack
from terrarium.packs.verified.repos.schemas import (
    COMMIT_ENTITY_SCHEMA,
    ISSUE_ENTITY_SCHEMA,
    PULL_REQUEST_ENTITY_SCHEMA,
    REPOSITORY_ENTITY_SCHEMA,
    REVIEW_ENTITY_SCHEMA,
)
from terrarium.packs.verified.repos.state_machines import (
    ISSUE_TRANSITIONS,
    PULL_REQUEST_TRANSITIONS,
    REVIEW_TRANSITIONS,
)


@pytest.fixture
def repos_pack():
    return ReposPack()


@pytest.fixture
def sample_state():
    """State with pre-existing issues, pull requests, commits, and comments."""
    return {
        "issues": [
            {
                "number": 1,
                "node_id": "MDU6SXNzdWUxMjM0NTY3OA",
                "title": "Bug in login",
                "body": "Login fails on mobile",
                "state": "open",
                "state_reason": None,
                "labels": ["bug", "high-priority"],
                "assignees": ["alice"],
                "milestone": None,
                "user": {"login": "bob"},
                "reactions": {
                    "total_count": 3,
                    "+1": 2,
                    "-1": 0,
                    "laugh": 0,
                    "hooray": 0,
                    "confused": 0,
                    "heart": 1,
                    "rocket": 0,
                    "eyes": 0,
                },
                "comments": 2,
                "created_at": "2025-01-10T10:00:00+00:00",
                "updated_at": "2025-01-11T10:00:00+00:00",
                "closed_at": None,
                "locked": False,
            },
            {
                "number": 2,
                "node_id": "MDU6SXNzdWUxMjM0NTY3OQ",
                "title": "Add dark mode",
                "body": "Users want dark mode",
                "state": "open",
                "state_reason": None,
                "labels": ["enhancement"],
                "assignees": ["charlie"],
                "milestone": None,
                "user": {"login": "alice"},
                "reactions": {
                    "total_count": 0,
                    "+1": 0,
                    "-1": 0,
                    "laugh": 0,
                    "hooray": 0,
                    "confused": 0,
                    "heart": 0,
                    "rocket": 0,
                    "eyes": 0,
                },
                "comments": 0,
                "created_at": "2025-01-12T10:00:00+00:00",
                "updated_at": "2025-01-12T10:00:00+00:00",
                "closed_at": None,
                "locked": False,
            },
            {
                "number": 3,
                "title": "Fix typo in README",
                "body": "",
                "state": "closed",
                "state_reason": "completed",
                "labels": ["docs"],
                "assignees": [],
                "user": {"login": "bob"},
                "comments": 1,
                "created_at": "2025-01-08T10:00:00+00:00",
                "updated_at": "2025-01-09T10:00:00+00:00",
                "closed_at": "2025-01-09T10:00:00+00:00",
                "locked": False,
            },
        ],
        "pull_requests": [
            {
                "number": 4,
                "node_id": "MDExOlB1bGxSZXF1ZXN0MTIz",
                "title": "Fix login bug",
                "body": "Fixes #1",
                "state": "open",
                "draft": False,
                "head": {"ref": "fix-login", "sha": "abc1234"},
                "base": {"ref": "main", "sha": "def5678"},
                "user": {"login": "alice"},
                "mergeable": True,
                "mergeable_state": "clean",
                "merged": False,
                "merged_at": None,
                "additions": 50,
                "deletions": 10,
                "changed_files": 3,
                "commits": 2,
                "review_comments": 1,
                "created_at": "2025-01-13T10:00:00+00:00",
                "updated_at": "2025-01-13T10:00:00+00:00",
            },
            {
                "number": 5,
                "title": "Dark mode implementation",
                "body": "WIP dark mode",
                "state": "open",
                "draft": True,
                "head": {"ref": "dark-mode", "sha": "111aaaa"},
                "base": {"ref": "main", "sha": "def5678"},
                "user": {"login": "charlie"},
                "mergeable": False,
                "mergeable_state": "dirty",
                "merged": False,
                "merged_at": None,
                "additions": 200,
                "deletions": 50,
                "changed_files": 15,
                "commits": 5,
                "review_comments": 0,
                "created_at": "2025-01-14T10:00:00+00:00",
                "updated_at": "2025-01-14T10:00:00+00:00",
            },
            {
                "number": 6,
                "title": "Old closed PR",
                "body": "",
                "state": "closed",
                "head": {"ref": "old-feature", "sha": "999bbb"},
                "base": {"ref": "main", "sha": "def5678"},
                "user": {"login": "bob"},
                "mergeable": False,
                "merged": False,
                "merged_at": None,
                "created_at": "2025-01-01T10:00:00+00:00",
                "updated_at": "2025-01-02T10:00:00+00:00",
            },
        ],
        "commits": [
            {
                "sha": "abc1234def5678",
                "node_id": "MDQ6Q29tbWl0MTIzNDU2Nzg",
                "html_url": "https://github.com/owner/repo/commit/abc1234def5678",
                "message": "Initial commit",
                "author": {
                    "name": "Alice",
                    "email": "alice@test.com",
                    "date": "2025-01-01T00:00:00+00:00",
                },
                "committer": {
                    "name": "Alice",
                    "email": "alice@test.com",
                    "date": "2025-01-01T00:00:00+00:00",
                },
                "parents": [],
                "stats": {"additions": 100, "deletions": 0, "total": 100},
                "url": "https://api.github.com/repos/owner/repo/commits/abc1234def5678",
            },
            {
                "sha": "def5678abc1234",
                "node_id": "MDQ6Q29tbWl0OTg3NjU0MzI",
                "html_url": "https://github.com/owner/repo/commit/def5678abc1234",
                "message": "Add README",
                "author": {
                    "name": "Bob",
                    "email": "bob@test.com",
                    "date": "2025-01-02T00:00:00+00:00",
                },
                "committer": {
                    "name": "Bob",
                    "email": "bob@test.com",
                    "date": "2025-01-02T00:00:00+00:00",
                },
                "parents": [
                    {
                        "sha": "abc1234def5678",
                        "url": "https://api.github.com/repos/owner/repo/commits/abc1234def5678",
                    }
                ],
                "stats": {"additions": 20, "deletions": 0, "total": 20},
                "url": "https://api.github.com/repos/owner/repo/commits/def5678abc1234",
            },
        ],
        "comments": [
            {
                "id": "comment_001",
                "issue_number": 1,
                "body": "I can reproduce this",
                "user": {"login": "alice"},
                "created_at": "2025-01-10T11:00:00+00:00",
                "updated_at": "2025-01-10T11:00:00+00:00",
            },
            {
                "id": "comment_002",
                "issue_number": 1,
                "body": "Me too",
                "user": {"login": "charlie"},
                "created_at": "2025-01-10T12:00:00+00:00",
                "updated_at": "2025-01-10T12:00:00+00:00",
            },
        ],
        "reviews": [
            {
                "id": "review_001",
                "pull_number": 4,
                "user": {"login": "bob"},
                "state": "COMMENTED",
                "body": "Looks good but needs tests",
                "submitted_at": "2025-01-13T11:00:00+00:00",
                "commit_id": "abc1234",
            },
        ],
        "pr_files": [
            {
                "sha": "aabbcc112233",
                "filename": "src/login.py",
                "status": "modified",
                "additions": 30,
                "deletions": 5,
                "changes": 35,
                "patch": "@@ -1,5 +1,30 @@",
                "pull_number": 4,
            },
            {
                "sha": "ddeeff445566",
                "filename": "tests/test_login.py",
                "status": "added",
                "additions": 20,
                "deletions": 0,
                "changes": 20,
                "patch": "@@ -0,0 +1,20 @@",
                "pull_number": 4,
            },
        ],
    }


# ---- Metadata tests ----


class TestReposPackMetadata:
    def test_metadata(self, repos_pack):
        """pack_name, category, fidelity_tier are correct."""
        assert repos_pack.pack_name == "repos"
        assert repos_pack.category == "code"
        assert repos_pack.fidelity_tier == 1

    def test_tools_count_and_names(self, repos_pack):
        """ReposPack exposes 15 tools with expected names."""
        tools = repos_pack.get_tools()
        assert len(tools) == 15
        tool_names = {t["name"] for t in tools}
        assert tool_names == {
            "create_issue",
            "list_issues",
            "get_issue",
            "update_issue",
            "add_issue_comment",
            "list_issue_comments",
            "search_issues",
            "create_pull_request",
            "list_pull_requests",
            "get_pull_request",
            "update_pull_request",
            "merge_pull_request",
            "create_pull_request_review",
            "get_pull_request_files",
            "list_commits",
        }

    def test_entity_schemas(self, repos_pack):
        """All entity schemas are present."""
        schemas = repos_pack.get_entity_schemas()
        assert "repository" in schemas
        assert "issue" in schemas
        assert "pull_request" in schemas
        assert "commit" in schemas
        assert "review" in schemas
        assert "issue_comment" in schemas
        assert "pr_file" in schemas

    def test_state_machines(self, repos_pack):
        """State machines for issue, pull_request, and review are present."""
        sms = repos_pack.get_state_machines()
        assert "issue" in sms
        assert "pull_request" in sms
        assert "review" in sms
        assert sms["issue"]["transitions"] == ISSUE_TRANSITIONS
        assert sms["pull_request"]["transitions"] == PULL_REQUEST_TRANSITIONS
        assert sms["review"]["transitions"] == REVIEW_TRANSITIONS

    def test_issue_schema_identity_is_number(self):
        """Issue identity field is 'number', not 'id'."""
        assert ISSUE_ENTITY_SCHEMA["x-terrarium-identity"] == "number"

    def test_pr_schema_identity_is_number(self):
        """Pull request identity field is 'number'."""
        assert PULL_REQUEST_ENTITY_SCHEMA["x-terrarium-identity"] == "number"

    def test_repository_schema_identity(self):
        """Repository identity field is 'id'."""
        assert REPOSITORY_ENTITY_SCHEMA["x-terrarium-identity"] == "id"

    def test_commit_schema_identity(self):
        """Commit identity field is 'sha'."""
        assert COMMIT_ENTITY_SCHEMA["x-terrarium-identity"] == "sha"

    def test_review_schema_identity(self):
        """Review identity field is 'id'."""
        assert REVIEW_ENTITY_SCHEMA["x-terrarium-identity"] == "id"

    def test_issue_schema_has_new_fields(self):
        """Issue schema includes P1 audit fields."""
        props = ISSUE_ENTITY_SCHEMA["properties"]
        assert "node_id" in props
        assert "milestone" in props
        assert "reactions" in props

    def test_pr_schema_has_new_fields(self):
        """PR schema includes P1 audit fields."""
        props = PULL_REQUEST_ENTITY_SCHEMA["properties"]
        assert "node_id" in props
        assert "draft" in props
        assert "mergeable_state" in props
        assert "additions" in props
        assert "deletions" in props
        assert "changed_files" in props
        assert "commits" in props
        assert "review_comments" in props

    def test_commit_schema_has_new_fields(self):
        """Commit schema includes P1 audit fields."""
        props = COMMIT_ENTITY_SCHEMA["properties"]
        assert "node_id" in props
        assert "html_url" in props
        assert "parents" in props
        assert "stats" in props

    def test_repository_schema_has_new_fields(self):
        """Repository schema includes P1 audit fields."""
        props = REPOSITORY_ENTITY_SCHEMA["properties"]
        assert "node_id" in props
        assert "topics" in props
        assert "archived" in props
        assert "disabled" in props
        assert "has_issues" in props
        assert "has_projects" in props
        assert "has_wiki" in props
        assert "license" in props


# ---- Issue handler tests ----


class TestCreateIssue:
    async def test_creates_issue_with_auto_number(self, repos_pack, sample_state):
        """create_issue assigns a number higher than existing issues and PRs."""
        proposal = await repos_pack.handle_action(
            ToolName("create_issue"),
            {"owner": "acme", "repo": "web", "title": "New bug"},
            sample_state,
        )
        assert isinstance(proposal, ResponseProposal)
        # Max existing number is 6 (PR), so new should be 7
        assert proposal.response_body["number"] == 7
        assert proposal.response_body["state"] == "open"
        assert proposal.response_body["comments"] == 0
        assert proposal.response_body["locked"] is False
        assert "node_id" in proposal.response_body
        assert proposal.response_body["reactions"]["total_count"] == 0

        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.entity_type == "issue"
        assert delta.operation == "create"
        assert str(delta.entity_id) == "7"

    async def test_creates_issue_with_labels_and_assignees(self, repos_pack, sample_state):
        """create_issue sets labels and assignees from input."""
        proposal = await repos_pack.handle_action(
            ToolName("create_issue"),
            {
                "owner": "acme",
                "repo": "web",
                "title": "Feature request",
                "body": "Please add X",
                "labels": ["enhancement", "v2"],
                "assignees": ["alice", "bob"],
            },
            sample_state,
        )
        assert proposal.response_body["labels"] == ["enhancement", "v2"]
        assert proposal.response_body["assignees"] == ["alice", "bob"]
        assert proposal.response_body["body"] == "Please add X"

    async def test_creates_issue_empty_state(self, repos_pack):
        """create_issue works with empty state, assigns number 1."""
        proposal = await repos_pack.handle_action(
            ToolName("create_issue"),
            {"owner": "acme", "repo": "web", "title": "First issue"},
            {},
        )
        assert proposal.response_body["number"] == 1


class TestListIssues:
    async def test_filters_by_state_open(self, repos_pack, sample_state):
        """list_issues with state=open returns only open issues."""
        proposal = await repos_pack.handle_action(
            ToolName("list_issues"),
            {"owner": "acme", "repo": "web", "state": "open"},
            sample_state,
        )
        issues = proposal.response_body["items"]
        assert len(issues) == 2
        assert all(i["state"] == "open" for i in issues)
        assert proposal.proposed_state_deltas == []

    async def test_filters_by_state_closed(self, repos_pack, sample_state):
        """list_issues with state=closed returns only closed issues."""
        proposal = await repos_pack.handle_action(
            ToolName("list_issues"),
            {"owner": "acme", "repo": "web", "state": "closed"},
            sample_state,
        )
        issues = proposal.response_body["items"]
        assert len(issues) == 1
        assert issues[0]["title"] == "Fix typo in README"

    async def test_filters_by_labels(self, repos_pack, sample_state):
        """list_issues filters by comma-separated labels."""
        proposal = await repos_pack.handle_action(
            ToolName("list_issues"),
            {"owner": "acme", "repo": "web", "state": "open", "labels": "bug"},
            sample_state,
        )
        issues = proposal.response_body["items"]
        assert len(issues) == 1
        assert issues[0]["title"] == "Bug in login"

    async def test_filters_by_assignee(self, repos_pack, sample_state):
        """list_issues filters by assignee."""
        proposal = await repos_pack.handle_action(
            ToolName("list_issues"),
            {"owner": "acme", "repo": "web", "state": "open", "assignee": "charlie"},
            sample_state,
        )
        issues = proposal.response_body["items"]
        assert len(issues) == 1
        assert issues[0]["title"] == "Add dark mode"

    async def test_sorted_by_created_at_desc(self, repos_pack, sample_state):
        """list_issues returns issues sorted by created_at descending."""
        proposal = await repos_pack.handle_action(
            ToolName("list_issues"),
            {"owner": "acme", "repo": "web", "state": "open"},
            sample_state,
        )
        issues = proposal.response_body["items"]
        dates = [i["created_at"] for i in issues]
        assert dates == sorted(dates, reverse=True)

    async def test_empty_state(self, repos_pack):
        """list_issues returns empty list from empty state."""
        proposal = await repos_pack.handle_action(
            ToolName("list_issues"),
            {"owner": "acme", "repo": "web"},
            {},
        )
        assert proposal.response_body["items"] == []


class TestGetIssue:
    async def test_returns_issue_by_number(self, repos_pack, sample_state):
        """get_issue returns the correct issue."""
        proposal = await repos_pack.handle_action(
            ToolName("get_issue"),
            {"owner": "acme", "repo": "web", "number": 1},
            sample_state,
        )
        assert proposal.response_body["title"] == "Bug in login"
        assert proposal.proposed_state_deltas == []

    async def test_not_found(self, repos_pack, sample_state):
        """get_issue returns GitHub-format 404 for nonexistent number."""
        proposal = await repos_pack.handle_action(
            ToolName("get_issue"),
            {"owner": "acme", "repo": "web", "number": 999},
            sample_state,
        )
        assert proposal.response_body["status"] == 404
        assert proposal.response_body["message"] == "Not Found"
        assert "documentation_url" in proposal.response_body


class TestUpdateIssue:
    async def test_updates_title_and_body(self, repos_pack, sample_state):
        """update_issue modifies title and body."""
        proposal = await repos_pack.handle_action(
            ToolName("update_issue"),
            {
                "owner": "acme",
                "repo": "web",
                "number": 1,
                "title": "Updated title",
                "body": "New body",
            },
            sample_state,
        )
        assert proposal.response_body["title"] == "Updated title"
        assert proposal.response_body["body"] == "New body"
        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.operation == "update"
        assert str(delta.entity_id) == "1"

    async def test_close_sets_closed_at(self, repos_pack, sample_state):
        """update_issue with state=closed sets closed_at."""
        proposal = await repos_pack.handle_action(
            ToolName("update_issue"),
            {"owner": "acme", "repo": "web", "number": 1, "state": "closed"},
            sample_state,
        )
        assert proposal.response_body["state"] == "closed"
        assert proposal.response_body["closed_at"] is not None
        delta = proposal.proposed_state_deltas[0]
        assert delta.fields["state"] == "closed"
        assert delta.previous_fields["state"] == "open"

    async def test_reopen_clears_closed_at(self, repos_pack, sample_state):
        """update_issue with state=open on a closed issue clears closed_at."""
        proposal = await repos_pack.handle_action(
            ToolName("update_issue"),
            {"owner": "acme", "repo": "web", "number": 3, "state": "open"},
            sample_state,
        )
        assert proposal.response_body["state"] == "open"
        assert proposal.response_body["closed_at"] is None
        delta = proposal.proposed_state_deltas[0]
        assert delta.fields["closed_at"] is None
        assert delta.previous_fields["state"] == "closed"

    async def test_update_not_found(self, repos_pack, sample_state):
        """update_issue returns GitHub-format 404 for nonexistent number."""
        proposal = await repos_pack.handle_action(
            ToolName("update_issue"),
            {"owner": "acme", "repo": "web", "number": 999, "title": "nope"},
            sample_state,
        )
        assert proposal.response_body["status"] == 404
        assert "documentation_url" in proposal.response_body

    async def test_update_labels(self, repos_pack, sample_state):
        """update_issue can replace labels."""
        proposal = await repos_pack.handle_action(
            ToolName("update_issue"),
            {"owner": "acme", "repo": "web", "number": 1, "labels": ["critical"]},
            sample_state,
        )
        assert proposal.response_body["labels"] == ["critical"]
        delta = proposal.proposed_state_deltas[0]
        assert delta.previous_fields["labels"] == ["bug", "high-priority"]


class TestAddIssueComment:
    async def test_creates_comment_and_increments_count(self, repos_pack, sample_state):
        """add_issue_comment creates a comment and bumps comments count."""
        proposal = await repos_pack.handle_action(
            ToolName("add_issue_comment"),
            {"owner": "acme", "repo": "web", "number": 1, "body": "Nice find!"},
            sample_state,
        )
        assert proposal.response_body["body"] == "Nice find!"
        assert proposal.response_body["issue_number"] == 1

        # Should have TWO deltas: create comment + update issue
        assert len(proposal.proposed_state_deltas) == 2

        comment_delta = proposal.proposed_state_deltas[0]
        assert comment_delta.entity_type == "comment"
        assert comment_delta.operation == "create"

        issue_delta = proposal.proposed_state_deltas[1]
        assert issue_delta.entity_type == "issue"
        assert issue_delta.operation == "update"
        assert issue_delta.fields["comments"] == 3  # was 2, now 3
        assert issue_delta.previous_fields["comments"] == 2

    async def test_comment_on_nonexistent_issue(self, repos_pack, sample_state):
        """add_issue_comment returns GitHub-format 404 for nonexistent issue."""
        proposal = await repos_pack.handle_action(
            ToolName("add_issue_comment"),
            {"owner": "acme", "repo": "web", "number": 999, "body": "hello"},
            sample_state,
        )
        assert proposal.response_body["status"] == 404
        assert "documentation_url" in proposal.response_body


class TestListIssueComments:
    async def test_returns_comments_for_issue(self, repos_pack, sample_state):
        """list_issue_comments returns comments for the given issue number."""
        proposal = await repos_pack.handle_action(
            ToolName("list_issue_comments"),
            {"owner": "acme", "repo": "web", "number": 1},
            sample_state,
        )
        comments = proposal.response_body["items"]
        assert len(comments) == 2
        assert all(c["issue_number"] == 1 for c in comments)
        assert proposal.proposed_state_deltas == []

    async def test_returns_empty_for_no_comments(self, repos_pack, sample_state):
        """list_issue_comments returns empty list for issue with no comments."""
        proposal = await repos_pack.handle_action(
            ToolName("list_issue_comments"),
            {"owner": "acme", "repo": "web", "number": 2},
            sample_state,
        )
        assert proposal.response_body["items"] == []

    async def test_empty_state(self, repos_pack):
        """list_issue_comments returns empty from empty state."""
        proposal = await repos_pack.handle_action(
            ToolName("list_issue_comments"),
            {"owner": "acme", "repo": "web", "number": 1},
            {},
        )
        assert proposal.response_body["items"] == []


class TestSearchIssues:
    async def test_search_finds_by_title(self, repos_pack, sample_state):
        """search_issues finds issues matching title."""
        proposal = await repos_pack.handle_action(
            ToolName("search_issues"),
            {"q": "dark mode"},
            sample_state,
        )
        items = proposal.response_body["items"]
        assert len(items) >= 1
        titles = [i["title"] for i in items]
        assert any("dark" in t.lower() for t in titles)
        assert proposal.response_body["incomplete_results"] is False

    async def test_search_finds_by_body(self, repos_pack, sample_state):
        """search_issues finds items matching body text."""
        proposal = await repos_pack.handle_action(
            ToolName("search_issues"),
            {"q": "mobile"},
            sample_state,
        )
        items = proposal.response_body["items"]
        assert len(items) == 1
        assert items[0]["title"] == "Bug in login"

    async def test_search_includes_prs(self, repos_pack, sample_state):
        """search_issues searches across both issues and PRs."""
        proposal = await repos_pack.handle_action(
            ToolName("search_issues"),
            {"q": "fixes"},
            sample_state,
        )
        items = proposal.response_body["items"]
        assert len(items) == 1
        assert items[0]["title"] == "Fix login bug"

    async def test_search_no_results(self, repos_pack, sample_state):
        """search_issues returns empty for non-matching query."""
        proposal = await repos_pack.handle_action(
            ToolName("search_issues"),
            {"q": "nonexistent_xyz_query"},
            sample_state,
        )
        assert proposal.response_body["total_count"] == 0
        assert proposal.response_body["items"] == []

    async def test_search_empty_state(self, repos_pack):
        """search_issues returns empty from empty state."""
        proposal = await repos_pack.handle_action(
            ToolName("search_issues"),
            {"q": "anything"},
            {},
        )
        assert proposal.response_body["items"] == []
        assert proposal.response_body["total_count"] == 0


# ---- Pull request handler tests ----


class TestCreatePullRequest:
    async def test_creates_pr_with_shared_number_sequence(self, repos_pack, sample_state):
        """create_pull_request uses shared number sequence with issues."""
        proposal = await repos_pack.handle_action(
            ToolName("create_pull_request"),
            {
                "owner": "acme",
                "repo": "web",
                "title": "New feature",
                "head": "feature-branch",
                "base": "main",
            },
            sample_state,
        )
        # Max existing is 6, so new should be 7
        assert proposal.response_body["number"] == 7
        assert proposal.response_body["state"] == "open"
        assert proposal.response_body["merged"] is False
        assert proposal.response_body["mergeable"] is True
        assert proposal.response_body["head"]["ref"] == "feature-branch"
        assert proposal.response_body["base"]["ref"] == "main"
        assert "node_id" in proposal.response_body
        assert proposal.response_body["draft"] is False
        assert proposal.response_body["mergeable_state"] == "clean"
        assert proposal.response_body["additions"] == 0
        assert proposal.response_body["commits"] == 1

        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.entity_type == "pull_request"
        assert delta.operation == "create"
        assert str(delta.entity_id) == "7"


class TestListPullRequests:
    async def test_filters_by_state_open(self, repos_pack, sample_state):
        """list_pull_requests with state=open returns only open PRs."""
        proposal = await repos_pack.handle_action(
            ToolName("list_pull_requests"),
            {"owner": "acme", "repo": "web", "state": "open"},
            sample_state,
        )
        prs = proposal.response_body["items"]
        assert len(prs) == 2
        assert all(p["state"] == "open" for p in prs)
        assert proposal.proposed_state_deltas == []

    async def test_filters_by_head(self, repos_pack, sample_state):
        """list_pull_requests filters by head branch ref."""
        proposal = await repos_pack.handle_action(
            ToolName("list_pull_requests"),
            {"owner": "acme", "repo": "web", "state": "open", "head": "fix-login"},
            sample_state,
        )
        prs = proposal.response_body["items"]
        assert len(prs) == 1
        assert prs[0]["title"] == "Fix login bug"

    async def test_filters_by_base(self, repos_pack, sample_state):
        """list_pull_requests filters by base branch ref."""
        proposal = await repos_pack.handle_action(
            ToolName("list_pull_requests"),
            {"owner": "acme", "repo": "web", "state": "all", "base": "main"},
            sample_state,
        )
        prs = proposal.response_body["items"]
        assert len(prs) == 3  # all 3 PRs target main

    async def test_empty_state(self, repos_pack):
        """list_pull_requests returns empty list from empty state."""
        proposal = await repos_pack.handle_action(
            ToolName("list_pull_requests"),
            {"owner": "acme", "repo": "web"},
            {},
        )
        assert proposal.response_body["items"] == []


class TestGetPullRequest:
    async def test_returns_pr_by_number(self, repos_pack, sample_state):
        """get_pull_request returns the correct PR."""
        proposal = await repos_pack.handle_action(
            ToolName("get_pull_request"),
            {"owner": "acme", "repo": "web", "number": 4},
            sample_state,
        )
        assert proposal.response_body["title"] == "Fix login bug"
        assert proposal.proposed_state_deltas == []

    async def test_not_found(self, repos_pack, sample_state):
        """get_pull_request returns GitHub-format 404 for nonexistent number."""
        proposal = await repos_pack.handle_action(
            ToolName("get_pull_request"),
            {"owner": "acme", "repo": "web", "number": 999},
            sample_state,
        )
        assert proposal.response_body["status"] == 404
        assert "documentation_url" in proposal.response_body


class TestUpdatePullRequest:
    async def test_updates_title_and_body(self, repos_pack, sample_state):
        """update_pull_request modifies title and body."""
        proposal = await repos_pack.handle_action(
            ToolName("update_pull_request"),
            {
                "owner": "acme",
                "repo": "web",
                "number": 4,
                "title": "Updated PR title",
                "body": "New PR body",
            },
            sample_state,
        )
        assert proposal.response_body["title"] == "Updated PR title"
        assert proposal.response_body["body"] == "New PR body"
        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.operation == "update"
        assert delta.fields["title"] == "Updated PR title"
        assert delta.previous_fields["title"] == "Fix login bug"

    async def test_updates_state(self, repos_pack, sample_state):
        """update_pull_request can change state."""
        proposal = await repos_pack.handle_action(
            ToolName("update_pull_request"),
            {"owner": "acme", "repo": "web", "number": 4, "state": "closed"},
            sample_state,
        )
        assert proposal.response_body["state"] == "closed"
        delta = proposal.proposed_state_deltas[0]
        assert delta.fields["state"] == "closed"
        assert delta.previous_fields["state"] == "open"

    async def test_updates_base(self, repos_pack, sample_state):
        """update_pull_request can change base branch."""
        proposal = await repos_pack.handle_action(
            ToolName("update_pull_request"),
            {"owner": "acme", "repo": "web", "number": 4, "base": "develop"},
            sample_state,
        )
        assert proposal.response_body["base"]["ref"] == "develop"
        delta = proposal.proposed_state_deltas[0]
        assert delta.fields["base"]["ref"] == "develop"
        assert delta.previous_fields["base"]["ref"] == "main"

    async def test_not_found(self, repos_pack, sample_state):
        """update_pull_request returns GitHub-format 404 for nonexistent number."""
        proposal = await repos_pack.handle_action(
            ToolName("update_pull_request"),
            {"owner": "acme", "repo": "web", "number": 999, "title": "nope"},
            sample_state,
        )
        assert proposal.response_body["status"] == 404
        assert "documentation_url" in proposal.response_body


class TestMergePullRequest:
    async def test_merges_open_mergeable_pr(self, repos_pack, sample_state):
        """merge_pull_request succeeds for an open, mergeable PR."""
        proposal = await repos_pack.handle_action(
            ToolName("merge_pull_request"),
            {"owner": "acme", "repo": "web", "number": 4},
            sample_state,
        )
        assert proposal.response_body["merged"] is True
        assert "sha" in proposal.response_body

        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.entity_type == "pull_request"
        assert delta.operation == "update"
        assert delta.fields["state"] == "closed"
        assert delta.fields["merged"] is True
        assert delta.fields["merged_at"] is not None
        assert delta.previous_fields["state"] == "open"
        assert delta.previous_fields["merged"] is False

    async def test_rejects_not_mergeable(self, repos_pack, sample_state):
        """merge_pull_request fails if mergeable=False."""
        proposal = await repos_pack.handle_action(
            ToolName("merge_pull_request"),
            {"owner": "acme", "repo": "web", "number": 5},
            sample_state,
        )
        assert proposal.response_body["status"] == 405
        assert "not mergeable" in proposal.response_body["message"]
        assert proposal.proposed_state_deltas == []

    async def test_rejects_closed_pr(self, repos_pack, sample_state):
        """merge_pull_request fails if PR is not open."""
        proposal = await repos_pack.handle_action(
            ToolName("merge_pull_request"),
            {"owner": "acme", "repo": "web", "number": 6},
            sample_state,
        )
        assert proposal.response_body["status"] == 405
        assert "not open" in proposal.response_body["message"]
        assert proposal.proposed_state_deltas == []

    async def test_not_found(self, repos_pack, sample_state):
        """merge_pull_request returns GitHub-format 404 for nonexistent number."""
        proposal = await repos_pack.handle_action(
            ToolName("merge_pull_request"),
            {"owner": "acme", "repo": "web", "number": 999},
            sample_state,
        )
        assert proposal.response_body["status"] == 404
        assert "documentation_url" in proposal.response_body

    async def test_merge_with_method(self, repos_pack, sample_state):
        """merge_pull_request includes the merge method in the response."""
        proposal = await repos_pack.handle_action(
            ToolName("merge_pull_request"),
            {"owner": "acme", "repo": "web", "number": 4, "merge_method": "squash"},
            sample_state,
        )
        assert "squash" in proposal.response_body["message"]


class TestCreatePullRequestReview:
    async def test_creates_review(self, repos_pack, sample_state):
        """create_pull_request_review creates a review and increments review_comments."""
        proposal = await repos_pack.handle_action(
            ToolName("create_pull_request_review"),
            {
                "owner": "acme",
                "repo": "web",
                "number": 4,
                "event": "APPROVE",
                "body": "LGTM",
            },
            sample_state,
        )
        assert proposal.response_body["state"] == "APPROVED"
        assert proposal.response_body["body"] == "LGTM"
        assert proposal.response_body["pull_number"] == 4
        assert "submitted_at" in proposal.response_body

        # Two deltas: review create + PR update (review_comments count)
        assert len(proposal.proposed_state_deltas) == 2
        review_delta = proposal.proposed_state_deltas[0]
        assert review_delta.entity_type == "review"
        assert review_delta.operation == "create"
        assert review_delta.fields["state"] == "APPROVED"

        pr_delta = proposal.proposed_state_deltas[1]
        assert pr_delta.entity_type == "pull_request"
        assert pr_delta.operation == "update"
        assert pr_delta.fields["review_comments"] == 2  # was 1, now 2

    async def test_creates_request_changes_review(self, repos_pack, sample_state):
        """create_pull_request_review maps REQUEST_CHANGES to CHANGES_REQUESTED."""
        proposal = await repos_pack.handle_action(
            ToolName("create_pull_request_review"),
            {
                "owner": "acme",
                "repo": "web",
                "number": 4,
                "event": "REQUEST_CHANGES",
                "body": "Needs work",
            },
            sample_state,
        )
        assert proposal.response_body["state"] == "CHANGES_REQUESTED"

    async def test_creates_comment_review(self, repos_pack, sample_state):
        """create_pull_request_review maps COMMENT to COMMENTED."""
        proposal = await repos_pack.handle_action(
            ToolName("create_pull_request_review"),
            {
                "owner": "acme",
                "repo": "web",
                "number": 4,
                "event": "COMMENT",
                "body": "Some thoughts",
            },
            sample_state,
        )
        assert proposal.response_body["state"] == "COMMENTED"

    async def test_review_not_found(self, repos_pack, sample_state):
        """create_pull_request_review returns 404 for nonexistent PR."""
        proposal = await repos_pack.handle_action(
            ToolName("create_pull_request_review"),
            {
                "owner": "acme",
                "repo": "web",
                "number": 999,
                "event": "APPROVE",
            },
            sample_state,
        )
        assert proposal.response_body["status"] == 404


class TestGetPullRequestFiles:
    async def test_returns_files_for_pr(self, repos_pack, sample_state):
        """get_pull_request_files returns files changed in a PR."""
        proposal = await repos_pack.handle_action(
            ToolName("get_pull_request_files"),
            {"owner": "acme", "repo": "web", "number": 4},
            sample_state,
        )
        files = proposal.response_body["items"]
        assert len(files) == 2
        filenames = {f["filename"] for f in files}
        assert "src/login.py" in filenames
        assert "tests/test_login.py" in filenames
        assert proposal.proposed_state_deltas == []

    async def test_returns_empty_for_pr_without_files(self, repos_pack, sample_state):
        """get_pull_request_files returns empty for a PR with no files in state."""
        proposal = await repos_pack.handle_action(
            ToolName("get_pull_request_files"),
            {"owner": "acme", "repo": "web", "number": 5},
            sample_state,
        )
        assert proposal.response_body["items"] == []

    async def test_not_found(self, repos_pack, sample_state):
        """get_pull_request_files returns 404 for nonexistent PR."""
        proposal = await repos_pack.handle_action(
            ToolName("get_pull_request_files"),
            {"owner": "acme", "repo": "web", "number": 999},
            sample_state,
        )
        assert proposal.response_body["status"] == 404


# ---- Commit handler tests ----


class TestListCommits:
    async def test_returns_all_commits(self, repos_pack, sample_state):
        """list_commits returns all commits."""
        proposal = await repos_pack.handle_action(
            ToolName("list_commits"),
            {"owner": "acme", "repo": "web"},
            sample_state,
        )
        assert len(proposal.response_body["items"]) == 2
        assert proposal.proposed_state_deltas == []

    async def test_filters_by_sha_prefix(self, repos_pack, sample_state):
        """list_commits filters by SHA prefix."""
        proposal = await repos_pack.handle_action(
            ToolName("list_commits"),
            {"owner": "acme", "repo": "web", "sha": "abc"},
            sample_state,
        )
        commits = proposal.response_body["items"]
        assert len(commits) == 1
        assert commits[0]["sha"].startswith("abc")

    async def test_empty_state(self, repos_pack):
        """list_commits returns empty list from empty state."""
        proposal = await repos_pack.handle_action(
            ToolName("list_commits"),
            {"owner": "acme", "repo": "web"},
            {},
        )
        assert proposal.response_body["items"] == []


# ---- State machine tests ----


class TestStateMachines:
    def test_issue_transitions(self):
        """Issue can transition open<->closed."""
        assert "closed" in ISSUE_TRANSITIONS["open"]
        assert "open" in ISSUE_TRANSITIONS["closed"]

    def test_pr_transitions(self):
        """PR transitions: open->closed/merged, closed->open, merged->nothing."""
        assert "closed" in PULL_REQUEST_TRANSITIONS["open"]
        assert "merged" in PULL_REQUEST_TRANSITIONS["open"]
        assert "open" in PULL_REQUEST_TRANSITIONS["closed"]
        assert PULL_REQUEST_TRANSITIONS["merged"] == []

    def test_review_transitions(self):
        """Review transitions are properly defined."""
        assert "APPROVED" in REVIEW_TRANSITIONS["PENDING"]
        assert "CHANGES_REQUESTED" in REVIEW_TRANSITIONS["PENDING"]
        assert "DISMISSED" in REVIEW_TRANSITIONS["APPROVED"]
        assert REVIEW_TRANSITIONS["DISMISSED"] != []


# ---- Dispatch error test ----


class TestDispatchError:
    async def test_unknown_action_raises(self, repos_pack, sample_state):
        """Dispatching an unknown action raises PackNotFoundError."""
        from terrarium.core.errors import PackNotFoundError

        with pytest.raises(PackNotFoundError):
            await repos_pack.handle_action(
                ToolName("nonexistent_action"),
                {},
                sample_state,
            )
