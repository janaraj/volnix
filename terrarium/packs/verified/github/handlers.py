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

# ---------------------------------------------------------------------------
# GitHub-style error response helper
# ---------------------------------------------------------------------------

_GITHUB_DOCS_URL = "https://docs.github.com/rest"


def _gh_error(message: str, status: int = 404) -> dict[str, Any]:
    """Return a GitHub-format error response body."""
    return {
        "message": message,
        "documentation_url": _GITHUB_DOCS_URL,
        "status": status,
    }


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
        "node_id": _new_id("MDU6SXNzdWU"),
        "title": input_data["title"],
        "body": input_data.get("body", ""),
        "state": "open",
        "state_reason": None,
        "labels": input_data.get("labels", []),
        "assignees": input_data.get("assignees", []),
        "milestone": None,
        "user": {"login": input_data.get("user", {}).get("login", "unknown")},
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

    Finds an issue by number. Returns GitHub-format 404 error if not found.
    """
    number = input_data["number"]
    issues = state.get("issues", [])

    for issue in issues:
        if issue.get("number") == number:
            return ResponseProposal(response_body=issue)

    return ResponseProposal(response_body=_gh_error("Not Found", 404))


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
        return ResponseProposal(response_body=_gh_error("Not Found", 404))

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
        return ResponseProposal(response_body=_gh_error("Not Found", 404))

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


async def handle_list_issue_comments(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``list_issue_comments`` action.

    Returns all comments for a given issue number from state["comments"].
    Paginates with per_page/page. No state mutations.
    """
    number = input_data["number"]
    comments = list(state.get("comments", []))

    # Filter comments belonging to this issue
    filtered = [c for c in comments if c.get("issue_number") == number]

    # Sort by created_at ascending (oldest first, like GitHub)
    filtered.sort(key=lambda c: c.get("created_at", ""))

    # Paginate
    page_items = _paginate(filtered, input_data)

    return ResponseProposal(
        response_body={"items": page_items, "total_count": len(page_items)},
    )


async def handle_search_issues(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``search_issues`` action.

    Searches across issues and pull requests by matching the query string
    (case-insensitive) against title and body. Supports sort and order.
    Paginates with per_page/page.
    """
    query = input_data["q"].lower()
    sort_field = input_data.get("sort", "created")
    order = input_data.get("order", "desc")

    # Combine issues and pull_requests for searching
    issues = list(state.get("issues", []))
    prs = list(state.get("pull_requests", []))
    all_items: list[dict[str, Any]] = []

    for item in issues:
        searchable = " ".join(
            [
                item.get("title", ""),
                item.get("body", ""),
                " ".join(item.get("labels", [])),
            ]
        ).lower()
        if query in searchable:
            all_items.append({**item, "_type": "issue"})

    for item in prs:
        searchable = " ".join(
            [
                item.get("title", ""),
                item.get("body", ""),
            ]
        ).lower()
        if query in searchable:
            all_items.append({**item, "_type": "pull_request"})

    # Sort
    sort_key_map = {
        "created": "created_at",
        "updated": "updated_at",
        "comments": "comments",
    }
    sort_key = sort_key_map.get(sort_field, "created_at")
    reverse = order == "desc"
    all_items.sort(key=lambda i: i.get(sort_key, ""), reverse=reverse)

    # Remove internal _type field from results
    for item in all_items:
        item.pop("_type", None)

    total = len(all_items)

    # Paginate
    page_items = _paginate(all_items, input_data)

    return ResponseProposal(
        response_body={
            "total_count": total,
            "incomplete_results": False,
            "items": page_items,
        },
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
        "node_id": _new_id("MDExOlB1bGxSZXF1ZXN0"),
        "title": input_data["title"],
        "body": input_data.get("body", ""),
        "state": "open",
        "draft": input_data.get("draft", False),
        "head": {"ref": input_data["head"], "sha": uuid.uuid4().hex[:7]},
        "base": {"ref": input_data["base"], "sha": uuid.uuid4().hex[:7]},
        "user": {"login": input_data.get("user", {}).get("login", "unknown")},
        "mergeable": True,
        "mergeable_state": "clean",
        "merged": False,
        "merged_at": None,
        "additions": 0,
        "deletions": 0,
        "changed_files": 0,
        "commits": 1,
        "review_comments": 0,
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

    Finds a PR by number. Returns GitHub-format 404 error if not found.
    """
    number = input_data["number"]
    prs = state.get("pull_requests", [])

    for pr in prs:
        if pr.get("number") == number:
            return ResponseProposal(response_body=pr)

    return ResponseProposal(response_body=_gh_error("Not Found", 404))


async def handle_update_pull_request(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``update_pull_request`` action.

    Updates title, body, state, and/or base on an existing pull request.
    """
    number = input_data["number"]
    prs = state.get("pull_requests", [])

    target: dict[str, Any] | None = None
    for pr in prs:
        if pr.get("number") == number:
            target = pr
            break

    if target is None:
        return ResponseProposal(response_body=_gh_error("Not Found", 404))

    now = _now_iso()
    updated_fields: dict[str, Any] = {"updated_at": now}
    previous_fields: dict[str, Any] = {}

    # Updatable scalar fields
    for field in ("title", "body"):
        if field in input_data:
            previous_fields[field] = target.get(field)
            updated_fields[field] = input_data[field]

    # State transitions
    new_state = input_data.get("state")
    if new_state and new_state != target.get("state"):
        previous_fields["state"] = target.get("state")
        updated_fields["state"] = new_state

    # Base branch change
    new_base = input_data.get("base")
    if new_base:
        old_base = target.get("base", {})
        previous_fields["base"] = old_base
        updated_fields["base"] = {"ref": new_base, "sha": old_base.get("sha", "")}

    delta = StateDelta(
        entity_type="pull_request",
        entity_id=EntityId(str(number)),
        operation="update",
        fields=updated_fields,
        previous_fields=previous_fields,
    )

    response_body = {**target, **updated_fields}

    return ResponseProposal(
        response_body=response_body,
        proposed_state_deltas=[delta],
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
        return ResponseProposal(response_body=_gh_error("Not Found", 404))

    if target.get("state") != "open":
        return ResponseProposal(
            response_body=_gh_error("Pull request is not open", 405),
        )

    if not target.get("mergeable", False):
        return ResponseProposal(
            response_body=_gh_error("Pull request is not mergeable", 405),
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


async def handle_create_pull_request_review(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``create_pull_request_review`` action.

    Creates a review entity on a pull request. The event parameter maps:
    APPROVE -> APPROVED, REQUEST_CHANGES -> CHANGES_REQUESTED, COMMENT -> COMMENTED.
    Also increments the PR's review_comments count.
    """
    number = input_data["number"]
    prs = state.get("pull_requests", [])

    target: dict[str, Any] | None = None
    for pr in prs:
        if pr.get("number") == number:
            target = pr
            break

    if target is None:
        return ResponseProposal(response_body=_gh_error("Not Found", 404))

    # Map input event to stored state
    event_to_state = {
        "APPROVE": "APPROVED",
        "REQUEST_CHANGES": "CHANGES_REQUESTED",
        "COMMENT": "COMMENTED",
    }
    event = input_data["event"]
    review_state = event_to_state.get(event, "COMMENTED")

    now = _now_iso()
    review_id = _new_id("review")

    review_fields: dict[str, Any] = {
        "id": review_id,
        "pull_number": number,
        "user": {"login": input_data.get("user", {}).get("login", "unknown")},
        "state": review_state,
        "body": input_data.get("body", ""),
        "submitted_at": now,
        "commit_id": target.get("head", {}).get("sha", ""),
    }

    old_review_count = target.get("review_comments", 0)

    deltas: list[StateDelta] = [
        StateDelta(
            entity_type="review",
            entity_id=EntityId(review_id),
            operation="create",
            fields=review_fields,
        ),
        StateDelta(
            entity_type="pull_request",
            entity_id=EntityId(str(number)),
            operation="update",
            fields={"review_comments": old_review_count + 1, "updated_at": now},
            previous_fields={"review_comments": old_review_count},
        ),
    ]

    return ResponseProposal(
        response_body=review_fields,
        proposed_state_deltas=deltas,
    )


async def handle_get_pull_request_files(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``get_pull_request_files`` action.

    Returns files changed in a pull request from state["pr_files"].
    Filters by pull_number, paginates with per_page/page. No state mutations.
    """
    number = input_data["number"]
    prs = state.get("pull_requests", [])

    # Verify PR exists
    target: dict[str, Any] | None = None
    for pr in prs:
        if pr.get("number") == number:
            target = pr
            break

    if target is None:
        return ResponseProposal(response_body=_gh_error("Not Found", 404))

    # Get files for this PR from state
    pr_files = list(state.get("pr_files", []))
    filtered = [f for f in pr_files if f.get("pull_number") == number]

    # Paginate
    page_items = _paginate(filtered, input_data)

    return ResponseProposal(
        response_body={"items": page_items, "total_count": len(page_items)},
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
