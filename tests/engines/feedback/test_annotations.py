"""Tests for AnnotationStore -- per-service behavioral annotations."""

from __future__ import annotations


async def test_add_and_retrieve(annotation_store):
    """Add an annotation, retrieve by service."""
    seq = await annotation_store.add("stripe", "Refunds >180 days should fail", "user")
    assert seq >= 1

    results = await annotation_store.get_by_service("stripe")
    assert len(results) == 1
    assert results[0]["text"] == "Refunds >180 days should fail"
    assert results[0]["author"] == "user"
    assert results[0]["service_id"] == "stripe"


async def test_get_by_run(annotation_store):
    """Annotations tagged with run_id are retrievable by run."""
    await annotation_store.add("jira", "Transitions need roles", "user", run_id="run-001")
    await annotation_store.add("jira", "Other note", "user", run_id="run-002")

    results = await annotation_store.get_by_run("run-001")
    assert len(results) == 1
    assert results[0]["text"] == "Transitions need roles"


async def test_search(annotation_store):
    """Search annotations by text content."""
    await annotation_store.add("stripe", "Refunds should fail for old charges", "user")
    await annotation_store.add("stripe", "Webhook signing is required", "user")
    await annotation_store.add("jira", "Transitions require roles", "user")

    results = await annotation_store.search("Refunds")
    assert len(results) == 1
    assert "Refunds" in results[0]["text"]


async def test_count_by_service(annotation_store):
    """Count annotations per service."""
    await annotation_store.add("stripe", "Note 1", "user")
    await annotation_store.add("stripe", "Note 2", "user")
    await annotation_store.add("jira", "Note 3", "user")

    assert await annotation_store.count_by_service("stripe") == 2
    assert await annotation_store.count_by_service("jira") == 1
    assert await annotation_store.count_by_service("unknown") == 0


async def test_add_with_tag(annotation_store):
    """Annotations can have optional tags."""
    await annotation_store.add("stripe", "Webhook issue", "system", tag="capability_gap")

    results = await annotation_store.get_by_service("stripe")
    assert len(results) == 1
    assert results[0]["tag"] == "capability_gap"


async def test_search_special_chars(annotation_store):
    """M9: Search with LIKE wildcards matches literally, not as wildcards."""
    await annotation_store.add("stripe", "100% of refunds work", "user")
    await annotation_store.add("stripe", "field_name is required", "user")
    await annotation_store.add("stripe", "Normal text here", "user")

    # % should match literally, not as wildcard
    results = await annotation_store.search("100%")
    assert len(results) == 1
    assert "100%" in results[0]["text"]

    # _ should match literally
    results = await annotation_store.search("field_name")
    assert len(results) == 1
    assert "field_name" in results[0]["text"]
