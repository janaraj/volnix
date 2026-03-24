"""Action handlers for the repos service pack.

Each function handles one tool action, producing a ResponseProposal with
any state mutations expressed as StateDelta objects.

Handlers import ONLY from terrarium.core (types, context). They NEVER
import from persistence/, engines/, or bus/.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from terrarium.core.context import ResponseProposal
from terrarium.core.types import EntityId, StateDelta


def _new_id(prefix: str) -> str:
    """Generate a unique ID with the given prefix."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def _next_number(state: dict[str, Any]) -> int:
    """GitHub shares issue/PR number sequence per repo."""
    max_issue = max(
        (i.get("number", 0) for i in state.get("issues", [])),
        default=0,
    )
    max_pr = max(
        (p.get("number", 0) for p in state.get("pull_requests", [])),
        default=0,
    )
    return max(max_issue, max_pr) + 1


def _paginate(items: list[Any], input_data: dict[str, Any], default_per_page: int = 30) -> list:
    """Apply per_page/page pagination to a list of items."""
    per_page = input_data.get("per_page", default_per_page)
    page = input_data.get("page", 1)
    if page is None:
        page = 1
    start = (page - 1) * per_page
    return items[start : start + per_page]


# ---------------------------------------------------------------------------
# Issue handlers
# ---------------------------------------------------------------------------


async def handle_create_issue(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``create_issue`` action.

    Creates an issue entity with auto-incremented number and state="open".
    """
    number = _next_number(state)
    now = _now_iso()

    issue_fields: dict[str, Any] = {
        "number": number,
        "title": input_data["title"],
        "body": input_data.get("body", ""),
        "state": "open",
        "state_reason": None,
        "labels": input_data.get("labels", []),
        "assignees": input_data.get("assignees", []),
        "user": {"login": input_data.get("user", {}).get("login", "unknown")},
        "comments": 0,
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "locked": False,
    }

    delta = StateDelta(
        entity_type="issue",
        entity_id=EntityId(str(number)),
        operation="create",
        fields=issue_fields,
    )

    return ResponseProposal(
        response_body=issue_fields,
        proposed_state_deltas=[delta],
    )


async def handle_list_issues(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``list_issues`` action.

    Filters state["issues"] by state, labels (comma-separated), and assignee.
    Sorts by created_at descending. Paginates with per_page/page.
    """
    issues = list(state.get("issues", []))
    state_filter = input_data.get("state", "open")

    # Filter by state
    if state_filter and state_filter != "all":
        issues = [i for i in issues if i.get("state") == state_filter]

    # Filter by labels (comma-separated string)
    labels_filter = input_data.get("labels")
    if labels_filter:
        required_labels = {lbl.strip() for lbl in labels_filter.split(",")}
        issues = [i for i in issues if required_labels.issubset(set(i.get("labels", [])))]

    # Filter by assignee
    assignee_filter = input_data.get("assignee")
    if assignee_filter:
        issues = [i for i in issues if assignee_filter in i.get("assignees", [])]

    # Sort by created_at descending
    issues.sort(key=lambda i: i.get("created_at", ""), reverse=True)

    # Paginate
    page_items = _paginate(issues, input_data)

    return ResponseProposal(
        response_body={
            "items": page_items,
            "total_count": len(page_items),
        },
    )


async def handle_get_issue(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``get_issue`` action.

    Finds an issue by number. Returns 404-style error if not found.
    """
    number = input_data["number"]
    issues = state.get("issues", [])

    for issue in issues:
        if issue.get("number") == number:
            return ResponseProposal(response_body=issue)

    return ResponseProposal(
        response_body={
            "message": "Not Found",
            "status": 404,
        },
    )


async def handle_update_issue(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``update_issue`` action.

    Updates title/body/state/state_reason/labels/assignees on an issue.
    If closing: sets closed_at. If reopening: clears closed_at.
    """
    number = input_data["number"]
    issues = state.get("issues", [])

    target: dict[str, Any] | None = None
    for issue in issues:
        if issue.get("number") == number:
            target = issue
            break

    if target is None:
        return ResponseProposal(
            response_body={
                "message": "Not Found",
                "status": 404,
            },
        )

    now = _now_iso()
    updated_fields: dict[str, Any] = {"updated_at": now}
    previous_fields: dict[str, Any] = {}

    # Updatable scalar fields
    for field in ("title", "body", "state_reason"):
        if field in input_data:
            previous_fields[field] = target.get(field)
            updated_fields[field] = input_data[field]

    # Array fields (replace)
    for field in ("labels", "assignees"):
        if field in input_data:
            previous_fields[field] = target.get(field, [])
            updated_fields[field] = input_data[field]

    # State transitions with closed_at logic
    new_state = input_data.get("state")
    if new_state and new_state != target.get("state"):
        previous_fields["state"] = target.get("state")
        updated_fields["state"] = new_state

        if new_state == "closed":
            updated_fields["closed_at"] = now
            previous_fields["closed_at"] = target.get("closed_at")
        elif new_state == "open" and target.get("state") == "closed":
            updated_fields["closed_at"] = None
            previous_fields["closed_at"] = target.get("closed_at")

    delta = StateDelta(
        entity_type="issue",
        entity_id=EntityId(str(number)),
        operation="update",
        fields=updated_fields,
        previous_fields=previous_fields,
    )

    # Build response body with merged fields
    response_body = {**target, **updated_fields}

    return ResponseProposal(
        response_body=response_body,
        proposed_state_deltas=[delta],
    )


async def handle_add_issue_comment(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``add_issue_comment`` action.

    Creates a comment entity and increments the issue's comments count.
    Produces two deltas: create comment + update issue.
    """
    number = input_data["number"]
    issues = state.get("issues", [])

    target: dict[str, Any] | None = None
    for issue in issues:
        if issue.get("number") == number:
            target = issue
            break

    if target is None:
        return ResponseProposal(
            response_body={
                "message": "Not Found",
                "status": 404,
            },
        )

    now = _now_iso()
    comment_id = _new_id("comment")

    comment_fields: dict[str, Any] = {
        "id": comment_id,
        "issue_number": number,
        "body": input_data["body"],
        "user": {"login": input_data.get("user", {}).get("login", "unknown")},
        "created_at": now,
        "updated_at": now,
    }

    old_count = target.get("comments", 0)

    deltas: list[StateDelta] = [
        # Create the comment entity
        StateDelta(
            entity_type="comment",
            entity_id=EntityId(comment_id),
            operation="create",
            fields=comment_fields,
        ),
        # Increment issue's comments count
        StateDelta(
            entity_type="issue",
            entity_id=EntityId(str(number)),
            operation="update",
            fields={"comments": old_count + 1, "updated_at": now},
            previous_fields={"comments": old_count},
        ),
    ]

    return ResponseProposal(
        response_body=comment_fields,
        proposed_state_deltas=deltas,
    )


# ---------------------------------------------------------------------------
# Pull request handlers
# ---------------------------------------------------------------------------


async def handle_create_pull_request(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``create_pull_request`` action.

    Creates a PR entity with auto-incremented number (shared with issues),
    state="open", merged=False, mergeable=True.
    """
    number = _next_number(state)
    now = _now_iso()

    pr_fields: dict[str, Any] = {
        "number": number,
        "title": input_data["title"],
        "body": input_data.get("body", ""),
        "state": "open",
        "head": {"ref": input_data["head"], "sha": uuid.uuid4().hex[:7]},
        "base": {"ref": input_data["base"], "sha": uuid.uuid4().hex[:7]},
        "user": {"login": input_data.get("user", {}).get("login", "unknown")},
        "mergeable": True,
        "merged": False,
        "merged_at": None,
        "created_at": now,
        "updated_at": now,
    }

    delta = StateDelta(
        entity_type="pull_request",
        entity_id=EntityId(str(number)),
        operation="create",
        fields=pr_fields,
    )

    return ResponseProposal(
        response_body=pr_fields,
        proposed_state_deltas=[delta],
    )


async def handle_list_pull_requests(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``list_pull_requests`` action.

    Filters state["pull_requests"] by state, head, and base.
    Paginates with per_page/page.
    """
    prs = list(state.get("pull_requests", []))
    state_filter = input_data.get("state", "open")

    # Filter by state
    if state_filter and state_filter != "all":
        prs = [p for p in prs if p.get("state") == state_filter]

    # Filter by head ref
    head_filter = input_data.get("head")
    if head_filter:
        prs = [p for p in prs if p.get("head", {}).get("ref") == head_filter]

    # Filter by base ref
    base_filter = input_data.get("base")
    if base_filter:
        prs = [p for p in prs if p.get("base", {}).get("ref") == base_filter]

    # Paginate
    page_items = _paginate(prs, input_data)

    return ResponseProposal(
        response_body={
            "items": page_items,
            "total_count": len(page_items),
        },
    )


async def handle_get_pull_request(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``get_pull_request`` action.

    Finds a PR by number. Returns 404-style error if not found.
    """
    number = input_data["number"]
    prs = state.get("pull_requests", [])

    for pr in prs:
        if pr.get("number") == number:
            return ResponseProposal(response_body=pr)

    return ResponseProposal(
        response_body={
            "message": "Not Found",
            "status": 404,
        },
    )


async def handle_merge_pull_request(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``merge_pull_request`` action.

    Validates that the PR exists, state="open", and mergeable=True.
    Sets merged=True, state="closed", merged_at to now.
    Returns error if PR is not mergeable or not open.
    """
    number = input_data["number"]
    prs = state.get("pull_requests", [])

    target: dict[str, Any] | None = None
    for pr in prs:
        if pr.get("number") == number:
            target = pr
            break

    if target is None:
        return ResponseProposal(
            response_body={
                "message": "Not Found",
                "status": 404,
            },
        )

    if target.get("state") != "open":
        return ResponseProposal(
            response_body={
                "message": "Pull request is not open",
                "status": 405,
            },
        )

    if not target.get("mergeable", False):
        return ResponseProposal(
            response_body={
                "message": "Pull request is not mergeable",
                "status": 405,
            },
        )

    now = _now_iso()
    merge_method = input_data.get("merge_method", "merge")
    commit_title = input_data.get("commit_title", f"Merge pull request #{number}")

    updated_fields: dict[str, Any] = {
        "state": "closed",
        "merged": True,
        "merged_at": now,
        "updated_at": now,
    }
    previous_fields: dict[str, Any] = {
        "state": target.get("state"),
        "merged": target.get("merged"),
        "merged_at": target.get("merged_at"),
    }

    delta = StateDelta(
        entity_type="pull_request",
        entity_id=EntityId(str(number)),
        operation="update",
        fields=updated_fields,
        previous_fields=previous_fields,
    )

    return ResponseProposal(
        response_body={
            "merged": True,
            "message": f"Pull Request successfully merged ({merge_method})",
            "sha": uuid.uuid4().hex[:7],
            "commit_title": commit_title,
        },
        proposed_state_deltas=[delta],
    )


# ---------------------------------------------------------------------------
# Commit handlers
# ---------------------------------------------------------------------------


async def handle_list_commits(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``list_commits`` action.

    Returns state["commits"] paginated. Optional filter by sha prefix.
    """
    commits = list(state.get("commits", []))

    # Optional filter by sha prefix
    sha_filter = input_data.get("sha")
    if sha_filter:
        commits = [c for c in commits if c.get("sha", "").startswith(sha_filter)]

    # Paginate
    page_items = _paginate(commits, input_data)

    return ResponseProposal(
        response_body={
            "items": page_items,
            "total_count": len(page_items),
        },
    )
