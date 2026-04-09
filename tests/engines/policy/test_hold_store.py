"""Tests for the HoldStore -- persistent approval queue."""

import time

import pytest

from volnix.engines.policy.hold_store import HoldStore
from volnix.persistence.sqlite import SQLiteDatabase


@pytest.fixture
async def store():
    """Create and initialize an in-memory HoldStore backed by SQLiteDatabase."""
    db = SQLiteDatabase(":memory:")
    await db.connect()
    s = HoldStore(db)
    await s.initialize()
    yield s
    await s.close()


class TestStoreAndRetrieve:
    """Basic store/get round-trip."""

    async def test_store_and_retrieve(self, store):
        await store.store(
            hold_id="hold-abc123",
            actor_id="agent-1",
            service_id="gmail",
            action="email_send",
            input_data={"to": "user@example.com", "body": "hello"},
            approver_role="supervisor",
            policy_id="policy-refund",
            timeout_seconds=1800.0,
            run_id="run-001",
        )
        result = await store.get("hold-abc123")
        assert result is not None
        assert result["hold_id"] == "hold-abc123"
        assert result["actor_id"] == "agent-1"
        assert result["service_id"] == "gmail"
        assert result["action"] == "email_send"
        assert result["approver_role"] == "supervisor"
        assert result["policy_id"] == "policy-refund"
        assert result["status"] == "pending"
        assert result["run_id"] == "run-001"
        assert result["resolved_by"] is None

    async def test_get_nonexistent_returns_none(self, store):
        result = await store.get("hold-does-not-exist")
        assert result is None


class TestResolve:
    """Hold resolution (approve/reject)."""

    async def test_resolve_approved(self, store):
        await store.store(
            hold_id="hold-approve-1",
            actor_id="agent-1",
            service_id="stripe",
            action="refund_create",
            input_data={"amount": 500},
            approver_role="supervisor",
            policy_id="policy-refund",
            timeout_seconds=1800.0,
        )
        result = await store.resolve("hold-approve-1", approved=True, approver="supervisor-1")
        assert result is not None
        assert result["hold_id"] == "hold-approve-1"

        # Verify status updated
        updated = await store.get("hold-approve-1")
        assert updated["status"] == "approved"
        assert updated["resolved_by"] == "supervisor-1"
        assert updated["resolved_at"] is not None

    async def test_resolve_rejected(self, store):
        await store.store(
            hold_id="hold-reject-1",
            actor_id="agent-1",
            service_id="stripe",
            action="refund_create",
            input_data={"amount": 50000},
            approver_role="supervisor",
            policy_id="policy-refund",
            timeout_seconds=1800.0,
        )
        result = await store.resolve(
            "hold-reject-1",
            approved=False,
            approver="supervisor-1",
            reason="Amount too high",
        )
        assert result is not None

        updated = await store.get("hold-reject-1")
        assert updated["status"] == "rejected"
        assert updated["resolution_reason"] == "Amount too high"

    async def test_resolve_already_resolved(self, store):
        await store.store(
            hold_id="hold-double",
            actor_id="agent-1",
            service_id="stripe",
            action="refund_create",
            input_data={"amount": 100},
            approver_role="supervisor",
            policy_id="policy-refund",
            timeout_seconds=1800.0,
        )
        # First resolve succeeds
        result1 = await store.resolve("hold-double", approved=True, approver="sup-1")
        assert result1 is not None

        # Second resolve returns None (already resolved)
        result2 = await store.resolve("hold-double", approved=False, approver="sup-2")
        assert result2 is None

    async def test_resolve_nonexistent(self, store):
        result = await store.resolve("hold-ghost", approved=True, approver="sup-1")
        assert result is None


class TestListPending:
    """Filtering pending holds."""

    async def test_list_pending(self, store):
        for i in range(3):
            await store.store(
                hold_id=f"hold-list-{i}",
                actor_id="agent-1",
                service_id="stripe",
                action="refund_create",
                input_data={"amount": 100 * (i + 1)},
                approver_role="supervisor",
                policy_id="policy-refund",
                timeout_seconds=1800.0,
            )
        # Resolve one
        await store.resolve("hold-list-1", approved=True, approver="sup-1")

        pending = await store.list_pending()
        assert len(pending) == 2
        hold_ids = {h["hold_id"] for h in pending}
        assert "hold-list-0" in hold_ids
        assert "hold-list-2" in hold_ids
        assert "hold-list-1" not in hold_ids

    async def test_list_pending_filter_by_role(self, store):
        await store.store(
            hold_id="hold-mgr",
            actor_id="agent-1",
            service_id="stripe",
            action="refund_create",
            input_data={},
            approver_role="manager",
            policy_id="p1",
            timeout_seconds=1800.0,
        )
        await store.store(
            hold_id="hold-sup",
            actor_id="agent-1",
            service_id="stripe",
            action="refund_create",
            input_data={},
            approver_role="supervisor",
            policy_id="p2",
            timeout_seconds=1800.0,
        )

        supervisor_holds = await store.list_pending(approver_role="supervisor")
        assert len(supervisor_holds) == 1
        assert supervisor_holds[0]["hold_id"] == "hold-sup"

    async def test_list_pending_filter_by_run_id(self, store):
        await store.store(
            hold_id="hold-r1",
            actor_id="agent-1",
            service_id="stripe",
            action="refund_create",
            input_data={},
            approver_role="supervisor",
            policy_id="p1",
            timeout_seconds=1800.0,
            run_id="run-A",
        )
        await store.store(
            hold_id="hold-r2",
            actor_id="agent-1",
            service_id="stripe",
            action="refund_create",
            input_data={},
            approver_role="supervisor",
            policy_id="p1",
            timeout_seconds=1800.0,
            run_id="run-B",
        )

        run_a = await store.list_pending(run_id="run-A")
        assert len(run_a) == 1
        assert run_a[0]["hold_id"] == "hold-r1"


class TestExpireStale:
    """Timeout-based expiration."""

    async def test_expire_stale(self, store):
        # Store a hold that expires immediately (timeout=0)
        await store.store(
            hold_id="hold-expire-1",
            actor_id="agent-1",
            service_id="stripe",
            action="refund_create",
            input_data={"amount": 100},
            approver_role="supervisor",
            policy_id="policy-refund",
            timeout_seconds=0,
        )
        # Store a hold that won't expire yet
        await store.store(
            hold_id="hold-keep-1",
            actor_id="agent-1",
            service_id="stripe",
            action="refund_create",
            input_data={"amount": 200},
            approver_role="supervisor",
            policy_id="policy-refund",
            timeout_seconds=99999,
        )

        # Run expiry slightly in the future
        expired = await store.expire_stale(time.time() + 1)
        assert "hold-expire-1" in expired
        assert "hold-keep-1" not in expired

        # Verify status
        expired_hold = await store.get("hold-expire-1")
        assert expired_hold["status"] == "expired"
        assert expired_hold["resolution_reason"] == "timeout"

        kept_hold = await store.get("hold-keep-1")
        assert kept_hold["status"] == "pending"

    async def test_expire_returns_empty_when_nothing_stale(self, store):
        expired = await store.expire_stale(time.time())
        assert expired == []
