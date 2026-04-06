"""Semantic categories for the Volnix kernel.

Defines the nine canonical service categories and the frozen
:class:`SemanticCategory` model used to describe each one.
"""

from __future__ import annotations

from pydantic import BaseModel


class SemanticCategory(BaseModel, frozen=True):
    """Immutable descriptor for a semantic service category.

    Attributes:
        name: Machine-readable category identifier.
        description: Human-readable explanation of the category.
        primitives: Canonical primitive names within this category.
        example_services: Well-known services that belong to this category.
    """

    name: str
    description: str
    primitives: list[str]
    example_services: list[str]


# ---------------------------------------------------------------------------
# Canonical categories
# ---------------------------------------------------------------------------

CATEGORIES: dict[str, SemanticCategory] = {
    "communication": SemanticCategory(
        name="communication",
        description="Services for sending, receiving, and organising messages across channels.",
        primitives=["channel", "thread", "message", "delivery", "visibility_rule"],
        example_services=["slack", "gmail", "outlook", "teams"],
    ),
    "work_management": SemanticCategory(
        name="work_management",
        description="Services for tracking, assigning, and managing units of work.",
        primitives=["work_item", "lifecycle", "assignment", "sla", "escalation"],
        example_services=["jira", "zendesk", "linear", "asana"],
    ),
    "money_transactions": SemanticCategory(
        name="money_transactions",
        description="Services for processing, authorising, and recording financial transactions.",
        primitives=["transaction", "authorization", "settlement", "reversal", "balance"],
        example_services=["stripe", "paypal", "square"],
    ),
    "authority_approvals": SemanticCategory(
        name="authority_approvals",
        description="Services for requesting, granting, and auditing approvals.",
        primitives=["request", "approval", "rejection", "delegation", "audit_trail"],
        example_services=["servicenow", "docusign"],
    ),
    "identity_auth": SemanticCategory(
        name="identity_auth",
        description="Services for authentication, identity verification, and access control.",
        primitives=["user", "credential", "session", "role", "permission"],
        example_services=["okta", "auth0", "azure_ad"],
    ),
    "storage_documents": SemanticCategory(
        name="storage_documents",
        description="Services for storing, retrieving, and organising files and documents.",
        primitives=["document", "folder", "version", "share", "metadata"],
        example_services=["google_drive", "dropbox", "sharepoint"],
    ),
    "code_devops": SemanticCategory(
        name="code_devops",
        description="Services for source control, CI/CD, and developer operations.",
        primitives=["repository", "branch", "pull_request", "pipeline", "deployment"],
        example_services=["github", "gitlab", "bitbucket"],
    ),
    "scheduling": SemanticCategory(
        name="scheduling",
        description="Services for managing calendars, events, and availability.",
        primitives=["event", "availability", "recurrence", "attendee", "reminder"],
        example_services=["google_calendar", "outlook_calendar", "calendly"],
    ),
    "monitoring_observability": SemanticCategory(
        name="monitoring_observability",
        description="Services for monitoring, alerting, and observability of systems.",
        primitives=["metric", "alert", "incident", "dashboard", "log_stream"],
        example_services=["datadog", "pagerduty", "grafana"],
    ),
    "social_media": SemanticCategory(
        name="social_media",
        description=(
            "Services for public content sharing, social engagement, and community interaction."
        ),
        primitives=["post", "comment", "vote", "profile", "community", "feed", "thread"],
        example_services=["reddit", "twitter", "linkedin", "facebook"],
    ),
    "trading": SemanticCategory(
        name="trading",
        description=(
            "Services for securities trading, order management,"
            " market data, and portfolio tracking."
        ),
        primitives=["order", "position", "quote", "bar", "fill", "account"],
        example_services=["alpaca", "interactive_brokers", "td_ameritrade", "robinhood"],
    ),
}
