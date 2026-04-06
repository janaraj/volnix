"""Semantic primitives for each service category.

Primitives are the atomic domain concepts that every service within a
category must be able to express.  This module defines the frozen
:class:`SemanticPrimitive` model and a lookup helper.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SemanticPrimitive(BaseModel, frozen=True):
    """Immutable descriptor for a single semantic primitive.

    Attributes:
        name: Machine-readable primitive identifier.
        category: The category this primitive belongs to.
        description: Human-readable explanation of the primitive.
        fields: Canonical field names and their expected types.
    """

    name: str
    category: str
    description: str
    fields: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Primitive definitions per category
# ---------------------------------------------------------------------------

_PRIMITIVES: list[SemanticPrimitive] = [
    # -- communication --
    SemanticPrimitive(
        name="channel",
        category="communication",
        description="A named communication channel (e.g. Slack channel, email folder).",
        fields={"channel_id": "str", "name": "str", "visibility": "str"},
    ),
    SemanticPrimitive(
        name="thread",
        category="communication",
        description="A conversation thread within a channel.",
        fields={"thread_id": "str", "channel_id": "str", "subject": "str"},
    ),
    SemanticPrimitive(
        name="message",
        category="communication",
        description="A single message within a thread or channel.",
        fields={"message_id": "str", "sender": "str", "body": "str", "timestamp": "datetime"},
    ),
    SemanticPrimitive(
        name="delivery",
        category="communication",
        description="Delivery status and receipt tracking for a message.",
        fields={"message_id": "str", "status": "str", "delivered_at": "datetime | None"},
    ),
    SemanticPrimitive(
        name="visibility_rule",
        category="communication",
        description="Rule governing who can see messages in a channel or thread.",
        fields={"rule_id": "str", "channel_id": "str", "allowed_roles": "list[str]"},
    ),
    # -- work_management --
    SemanticPrimitive(
        name="work_item",
        category="work_management",
        description="A unit of work (ticket, issue, task).",
        fields={"item_id": "str", "title": "str", "status": "str", "priority": "str"},
    ),
    SemanticPrimitive(
        name="lifecycle",
        category="work_management",
        description="State machine defining valid status transitions for work items.",
        fields={"states": "list[str]", "transitions": "dict[str, list[str]]"},
    ),
    SemanticPrimitive(
        name="assignment",
        category="work_management",
        description="Binding of a work item to an assignee.",
        fields={"item_id": "str", "assignee": "str", "assigned_at": "datetime"},
    ),
    SemanticPrimitive(
        name="sla",
        category="work_management",
        description="Service-level agreement target for a work item.",
        fields={"item_id": "str", "target_hours": "float", "breached": "bool"},
    ),
    SemanticPrimitive(
        name="escalation",
        category="work_management",
        description="Escalation of a work item to a higher-tier responder.",
        fields={"item_id": "str", "from_tier": "int", "to_tier": "int", "reason": "str"},
    ),
    # -- money_transactions --
    SemanticPrimitive(
        name="transaction",
        category="money_transactions",
        description="A financial transaction record.",
        fields={"tx_id": "str", "amount": "float", "currency": "str", "status": "str"},
    ),
    SemanticPrimitive(
        name="authorization",
        category="money_transactions",
        description="Pre-authorisation hold on funds.",
        fields={"auth_id": "str", "tx_id": "str", "approved": "bool"},
    ),
    SemanticPrimitive(
        name="settlement",
        category="money_transactions",
        description="Final settlement of a previously authorised transaction.",
        fields={"settlement_id": "str", "tx_id": "str", "settled_at": "datetime"},
    ),
    SemanticPrimitive(
        name="reversal",
        category="money_transactions",
        description="Reversal or refund of a completed transaction.",
        fields={"reversal_id": "str", "tx_id": "str", "amount": "float", "reason": "str"},
    ),
    SemanticPrimitive(
        name="balance",
        category="money_transactions",
        description="Current balance snapshot for an account.",
        fields={"account_id": "str", "available": "float", "pending": "float", "currency": "str"},
    ),
    # -- authority_approvals --
    SemanticPrimitive(
        name="request",
        category="authority_approvals",
        description="A request submitted for approval.",
        fields={"request_id": "str", "requester": "str", "action": "str", "status": "str"},
    ),
    SemanticPrimitive(
        name="approval",
        category="authority_approvals",
        description="An approval decision on a request.",
        fields={"approval_id": "str", "request_id": "str", "approver": "str", "approved": "bool"},
    ),
    SemanticPrimitive(
        name="rejection",
        category="authority_approvals",
        description="A rejection decision on a request.",
        fields={"rejection_id": "str", "request_id": "str", "rejector": "str", "reason": "str"},
    ),
    SemanticPrimitive(
        name="delegation",
        category="authority_approvals",
        description="Delegation of approval authority to another actor.",
        fields={"delegation_id": "str", "from_approver": "str", "to_approver": "str"},
    ),
    SemanticPrimitive(
        name="audit_trail",
        category="authority_approvals",
        description="Immutable log of approval-related events.",
        fields={"trail_id": "str", "entries": "list[dict]"},
    ),
    # -- identity_auth --
    SemanticPrimitive(
        name="user",
        category="identity_auth",
        description="A user identity record.",
        fields={"user_id": "str", "email": "str", "display_name": "str"},
    ),
    SemanticPrimitive(
        name="credential",
        category="identity_auth",
        description="A credential (password hash, API key, token) for a user.",
        fields={"credential_id": "str", "user_id": "str", "credential_type": "str"},
    ),
    SemanticPrimitive(
        name="session",
        category="identity_auth",
        description="An active authentication session.",
        fields={"session_id": "str", "user_id": "str", "expires_at": "datetime"},
    ),
    SemanticPrimitive(
        name="role",
        category="identity_auth",
        description="A named role with associated permissions.",
        fields={"role_id": "str", "name": "str", "permissions": "list[str]"},
    ),
    SemanticPrimitive(
        name="permission",
        category="identity_auth",
        description="A single permission grant on a resource.",
        fields={"permission_id": "str", "resource": "str", "action": "str"},
    ),
    # -- storage_documents --
    SemanticPrimitive(
        name="document",
        category="storage_documents",
        description="A stored document or file.",
        fields={"doc_id": "str", "name": "str", "mime_type": "str", "size_bytes": "int"},
    ),
    SemanticPrimitive(
        name="folder",
        category="storage_documents",
        description="A folder or directory in a storage hierarchy.",
        fields={"folder_id": "str", "name": "str", "parent_id": "str | None"},
    ),
    SemanticPrimitive(
        name="version",
        category="storage_documents",
        description="A versioned snapshot of a document.",
        fields={"version_id": "str", "doc_id": "str", "version_number": "int"},
    ),
    SemanticPrimitive(
        name="share",
        category="storage_documents",
        description="A sharing link or permission for a document or folder.",
        fields={"share_id": "str", "target_id": "str", "grantee": "str", "access_level": "str"},
    ),
    SemanticPrimitive(
        name="metadata",
        category="storage_documents",
        description="Key-value metadata attached to a document.",
        fields={"doc_id": "str", "key": "str", "value": "str"},
    ),
    # -- code_devops --
    SemanticPrimitive(
        name="repository",
        category="code_devops",
        description="A source code repository.",
        fields={"repo_id": "str", "name": "str", "default_branch": "str"},
    ),
    SemanticPrimitive(
        name="branch",
        category="code_devops",
        description="A branch within a repository.",
        fields={"branch_name": "str", "repo_id": "str", "head_sha": "str"},
    ),
    SemanticPrimitive(
        name="pull_request",
        category="code_devops",
        description="A pull / merge request.",
        fields={"pr_id": "str", "repo_id": "str", "title": "str", "status": "str"},
    ),
    SemanticPrimitive(
        name="pipeline",
        category="code_devops",
        description="A CI/CD pipeline run.",
        fields={"pipeline_id": "str", "repo_id": "str", "status": "str", "triggered_by": "str"},
    ),
    SemanticPrimitive(
        name="deployment",
        category="code_devops",
        description="A deployment to an environment.",
        fields={"deployment_id": "str", "environment": "str", "version": "str", "status": "str"},
    ),
    # -- scheduling --
    SemanticPrimitive(
        name="event",
        category="scheduling",
        description="A calendar event.",
        fields={"event_id": "str", "title": "str", "start": "datetime", "end": "datetime"},
    ),
    SemanticPrimitive(
        name="availability",
        category="scheduling",
        description="An availability / free-busy slot.",
        fields={"user_id": "str", "start": "datetime", "end": "datetime", "status": "str"},
    ),
    SemanticPrimitive(
        name="recurrence",
        category="scheduling",
        description="A recurrence rule for repeating events.",
        fields={"event_id": "str", "rrule": "str"},
    ),
    SemanticPrimitive(
        name="attendee",
        category="scheduling",
        description="An attendee on a calendar event.",
        fields={"event_id": "str", "user_id": "str", "rsvp": "str"},
    ),
    SemanticPrimitive(
        name="reminder",
        category="scheduling",
        description="A reminder associated with a calendar event.",
        fields={"event_id": "str", "minutes_before": "int", "method": "str"},
    ),
    # -- monitoring_observability --
    SemanticPrimitive(
        name="metric",
        category="monitoring_observability",
        description="A time-series metric data point.",
        fields={"metric_name": "str", "value": "float", "timestamp": "datetime", "tags": "dict"},
    ),
    SemanticPrimitive(
        name="alert",
        category="monitoring_observability",
        description="An alert triggered by a monitoring rule.",
        fields={"alert_id": "str", "severity": "str", "message": "str", "triggered_at": "datetime"},
    ),
    SemanticPrimitive(
        name="incident",
        category="monitoring_observability",
        description="An operational incident record.",
        fields={"incident_id": "str", "title": "str", "severity": "str", "status": "str"},
    ),
    SemanticPrimitive(
        name="dashboard",
        category="monitoring_observability",
        description="A monitoring dashboard configuration.",
        fields={"dashboard_id": "str", "name": "str", "panels": "list[dict]"},
    ),
    SemanticPrimitive(
        name="log_stream",
        category="monitoring_observability",
        description="A stream of structured log entries.",
        fields={"stream_id": "str", "source": "str", "level": "str"},
    ),
    # -- social_media --
    SemanticPrimitive(
        name="post",
        category="social_media",
        description="A piece of published content (tweet, Reddit submission, LinkedIn post).",
        fields={"post_id": "str", "author_id": "str", "content": "str", "score": "int"},
    ),
    SemanticPrimitive(
        name="comment",
        category="social_media",
        description="A reply to a post or another comment.",
        fields={"comment_id": "str", "post_id": "str", "author_id": "str", "body": "str"},
    ),
    SemanticPrimitive(
        name="vote",
        category="social_media",
        description="An engagement action on content (upvote, downvote, like).",
        fields={"vote_id": "str", "user_id": "str", "target_id": "str", "direction": "str"},
    ),
    SemanticPrimitive(
        name="profile",
        category="social_media",
        description="A user's public identity and social graph metrics.",
        fields={"profile_id": "str", "username": "str", "follower_count": "int"},
    ),
    SemanticPrimitive(
        name="community",
        category="social_media",
        description="A group or topic where content is organised (subreddit, topic).",
        fields={"community_id": "str", "name": "str", "member_count": "int"},
    ),
    SemanticPrimitive(
        name="feed",
        category="social_media",
        description="A personalised stream of content for a user.",
        fields={"user_id": "str", "items": "list[str]", "algorithm": "str"},
    ),
    SemanticPrimitive(
        name="thread",
        category="social_media",
        description="A connected series of posts or comments forming a conversation.",
        fields={"thread_id": "str", "root_post_id": "str", "reply_count": "int"},
    ),
    # -- trading --
    SemanticPrimitive(
        name="order",
        category="trading",
        description="A trade order with side, quantity, price, and lifecycle state.",
        fields={"order_id": "str", "symbol": "str", "qty": "float",
                "side": "str", "type": "str", "status": "str"},
    ),
    SemanticPrimitive(
        name="position",
        category="trading",
        description="An open position in a security with entry price and P&L.",
        fields={"symbol": "str", "qty": "float", "avg_entry_price": "float",
                "unrealized_pl": "float", "side": "str"},
    ),
    SemanticPrimitive(
        name="quote",
        category="trading",
        description="A bid/ask quote for a security at a point in time.",
        fields={"symbol": "str", "bid_price": "float", "ask_price": "float",
                "timestamp": "str"},
    ),
    SemanticPrimitive(
        name="bar",
        category="trading",
        description="An OHLCV candle for a security over a time period.",
        fields={"symbol": "str", "open": "float", "high": "float",
                "low": "float", "close": "float", "volume": "int"},
    ),
    SemanticPrimitive(
        name="fill",
        category="trading",
        description="An execution/fill event recording that an order was matched.",
        fields={"order_id": "str", "price": "float", "qty": "float",
                "side": "str", "symbol": "str"},
    ),
    SemanticPrimitive(
        name="account",
        category="trading",
        description="A brokerage account with balances, margins, and trading permissions.",
        fields={"account_id": "str", "equity": "float", "buying_power": "float",
                "cash": "float", "portfolio_value": "float"},
    ),
]

# Build a lookup index by category
_BY_CATEGORY: dict[str, list[SemanticPrimitive]] = {}
for _p in _PRIMITIVES:
    _BY_CATEGORY.setdefault(_p.category, []).append(_p)


def get_primitives_for_category(category: str) -> list[SemanticPrimitive]:
    """Return all primitives belonging to *category*.

    Args:
        category: One of the nine canonical category names.

    Returns:
        List of :class:`SemanticPrimitive` instances, or an empty list
        if the category is unknown.
    """
    return list(_BY_CATEGORY.get(category, []))
