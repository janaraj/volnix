"""Game tool handlers — the sole writers to negotiation entity state.

Per MF1: these handlers produce ``ResponseProposal`` objects with
``proposed_state_deltas`` that are committed atomically in the pipeline's
commit step. They are the ONLY code path that mutates
``negotiation_deal`` / ``negotiation_proposal`` state. The orchestrator's
bus subscriber reads state but never writes through it.

Each handler reads ``input_data["_actor_id"]`` which is injected by
``PackRuntime.execute`` from ``ActionContext.actor_id``. Underscore-
prefixed key signals that it is not a user-facing tool parameter.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from volnix.core.context import ResponseProposal
from volnix.core.types import EntityId, StateDelta

# Fields we never treat as "negotiation terms" — they're metadata.
_RESERVED_KEYS = {
    "deal_id",
    "message",
    "reasoning",
    "intended_for",
    "state_updates",
    "_actor_id",  # pipeline-injected
}


def _now_iso() -> str:
    """UTC ISO-8601 timestamp string."""
    return datetime.now(UTC).isoformat()


def _new_proposal_id() -> str:
    """Generate a unique negotiation_proposal id."""
    return f"prop-{uuid.uuid4().hex[:12]}"


def _extract_actor_id(input_data: dict[str, Any]) -> str:
    """Read the pipeline-injected actor_id from input_data.

    Returns empty string if missing (tests / manual invocation).
    """
    return str(input_data.get("_actor_id", ""))


def _extract_terms(input_data: dict[str, Any]) -> dict[str, Any]:
    """Extract the free-form 'terms' dict (everything that isn't metadata)."""
    return {k: v for k, v in input_data.items() if k not in _RESERVED_KEYS}


def _find_deal(state: dict[str, Any], deal_id: str) -> dict[str, Any] | None:
    """Look up a negotiation_deal by id from the pack runtime's state dict."""
    deals = state.get("negotiation_deal") or []
    for deal in deals:
        if isinstance(deal, dict) and deal.get("id") == deal_id:
            return deal
    return None


def _error(message: str) -> ResponseProposal:
    """Build a ResponseProposal for an error (no deltas)."""
    return ResponseProposal(
        response_body={"object": "error", "message": message},
        proposed_state_deltas=[],
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def handle_negotiate_propose(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle ``negotiate_propose``: write deal.terms + create proposal entity."""
    deal_id = str(input_data.get("deal_id") or "")
    if not deal_id:
        return _error("deal_id required")

    deal = _find_deal(state, deal_id)
    if deal is None:
        return _error(f"deal {deal_id} not found")

    actor_id = _extract_actor_id(input_data)
    terms = _extract_terms(input_data)
    proposal_id = _new_proposal_id()
    now_iso = _now_iso()

    deltas: list[StateDelta] = [
        StateDelta(
            entity_type="negotiation_deal",
            entity_id=EntityId(deal_id),
            operation="update",
            fields={
                "status": "proposed",
                "terms": terms,
                "last_proposed_by": actor_id,
                "last_updated_at": now_iso,
            },
        ),
        StateDelta(
            entity_type="negotiation_proposal",
            entity_id=EntityId(proposal_id),
            operation="create",
            fields={
                "id": proposal_id,
                "deal_id": deal_id,
                "proposed_by": actor_id,
                "msg_type": "propose",
                "terms": terms,
                "created_at": now_iso,
            },
        ),
    ]

    return ResponseProposal(
        response_body={
            "object": "negotiation_proposal",
            "id": proposal_id,
            "deal_id": deal_id,
            "status": "proposed",
            "terms": terms,
        },
        proposed_state_deltas=deltas,
    )


async def handle_negotiate_counter(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle ``negotiate_counter``: like propose, but status=countered.

    Also resets ``deal.consent_by`` to empty — any counter invalidates
    prior consents (P7-ready behavior baked in now).
    """
    deal_id = str(input_data.get("deal_id") or "")
    if not deal_id:
        return _error("deal_id required")

    deal = _find_deal(state, deal_id)
    if deal is None:
        return _error(f"deal {deal_id} not found")

    actor_id = _extract_actor_id(input_data)
    terms = _extract_terms(input_data)
    proposal_id = _new_proposal_id()
    now_iso = _now_iso()

    deltas: list[StateDelta] = [
        StateDelta(
            entity_type="negotiation_deal",
            entity_id=EntityId(deal_id),
            operation="update",
            fields={
                "status": "countered",
                "terms": terms,
                "last_proposed_by": actor_id,
                "last_updated_at": now_iso,
                # P7: counter resets the consent ledger so prior consents don't
                # carry over onto new terms.
                "consent_by": [],
            },
        ),
        StateDelta(
            entity_type="negotiation_proposal",
            entity_id=EntityId(proposal_id),
            operation="create",
            fields={
                "id": proposal_id,
                "deal_id": deal_id,
                "proposed_by": actor_id,
                "msg_type": "counter",
                "terms": terms,
                "created_at": now_iso,
            },
        ),
    ]

    return ResponseProposal(
        response_body={
            "object": "negotiation_proposal",
            "id": proposal_id,
            "deal_id": deal_id,
            "status": "countered",
            "terms": terms,
        },
        proposed_state_deltas=deltas,
    )


async def handle_negotiate_accept(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle ``negotiate_accept``: 2-party first-accept closes; N-party uses consent_by.

    For 2-party deals, any party's accept closes the deal. For 3+ party
    deals (P7 consent ledger pattern), we append the actor to ``consent_by``
    and only flip ``status=accepted`` when the unanimous rule is met.
    """
    deal_id = str(input_data.get("deal_id") or "")
    if not deal_id:
        return _error("deal_id required")

    deal = _find_deal(state, deal_id)
    if deal is None:
        return _error(f"deal {deal_id} not found")

    actor_id = _extract_actor_id(input_data)
    parties = list(deal.get("parties") or [])
    now_iso = _now_iso()

    # 2-party: first accept closes
    if len(parties) <= 2:
        deltas: list[StateDelta] = [
            StateDelta(
                entity_type="negotiation_deal",
                entity_id=EntityId(deal_id),
                operation="update",
                fields={
                    "status": "accepted",
                    "accepted_by": actor_id,
                    "accepted_at": now_iso,
                },
            ),
        ]
        return ResponseProposal(
            response_body={
                "object": "negotiation_deal",
                "id": deal_id,
                "status": "accepted",
                "accepted_by": actor_id,
            },
            proposed_state_deltas=deltas,
        )

    # N-party: consent ledger pattern (P7-ready)
    consent_by = list(deal.get("consent_by") or [])
    if actor_id and actor_id not in consent_by:
        consent_by.append(actor_id)
    consent_rule = str(deal.get("consent_rule") or "unanimous").lower()
    if consent_rule == "majority":
        consent_met = len(consent_by) * 2 > len(parties)
    else:
        # Match by role prefix (consent_by contains actor_ids like "buyer-abc",
        # parties contains roles like "buyer").
        def _actor_matches_role(aid: str, role: str) -> bool:
            return aid == role or aid.startswith(role + "-")

        consent_met = all(
            any(_actor_matches_role(aid, role) for aid in consent_by) for role in parties
        )

    if consent_met:
        deltas = [
            StateDelta(
                entity_type="negotiation_deal",
                entity_id=EntityId(deal_id),
                operation="update",
                fields={
                    "status": "accepted",
                    "accepted_by": actor_id,
                    "accepted_at": now_iso,
                    "consent_by": consent_by,
                },
            ),
        ]
        status_out = "accepted"
    else:
        deltas = [
            StateDelta(
                entity_type="negotiation_deal",
                entity_id=EntityId(deal_id),
                operation="update",
                fields={"consent_by": consent_by},
            ),
        ]
        status_out = str(deal.get("status", "proposed"))

    return ResponseProposal(
        response_body={
            "object": "negotiation_deal",
            "id": deal_id,
            "status": status_out,
            "consent_by": consent_by,
        },
        proposed_state_deltas=deltas,
    )


async def handle_negotiate_reject(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle ``negotiate_reject``: set deal.status=rejected."""
    deal_id = str(input_data.get("deal_id") or "")
    if not deal_id:
        return _error("deal_id required")

    deal = _find_deal(state, deal_id)
    if deal is None:
        return _error(f"deal {deal_id} not found")

    actor_id = _extract_actor_id(input_data)
    now_iso = _now_iso()

    return ResponseProposal(
        response_body={
            "object": "negotiation_deal",
            "id": deal_id,
            "status": "rejected",
            "rejected_by": actor_id,
        },
        proposed_state_deltas=[
            StateDelta(
                entity_type="negotiation_deal",
                entity_id=EntityId(deal_id),
                operation="update",
                fields={
                    "status": "rejected",
                    "rejected_by": actor_id,
                    "rejected_at": now_iso,
                },
            ),
        ],
    )
