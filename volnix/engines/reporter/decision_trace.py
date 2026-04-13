"""Decision trace builder — per-run activation-based trace artifact.

Stateless computation: no constructor state. Call build() with run events.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

_PREFERRED_FIELDS: frozenset[str] = frozenset({
    "id", "status", "name", "title", "price", "value", "count",
    "severity", "level", "total", "amount", "quantity", "rate",
})

_SYSTEM_ACTORS: frozenset[str] = frozenset({
    "world_compiler", "animator", "system", "policy",
    "budget", "state", "permission", "responder", "environment",
})

_GOVERNANCE_TYPES: frozenset[str] = frozenset({
    "permission.denied", "permission.allow",
    "policy.block", "policy.hold", "policy.flag",
    "budget.deduction", "budget.warning",
})


@runtime_checkable
class DomainInterpreter(Protocol):
    """Read-only narrative generator. Receives trace data, returns strings."""

    def interpret(
        self,
        activations: list[dict[str, Any]],
        game_result: dict[str, Any] | None,
    ) -> list[str]: ...


def _get_val(obj: Any, key: str, default: Any = None) -> Any:
    """Get a field from a dict or Pydantic/attr object transparently."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _get_str(obj: Any, key: str) -> str:
    v = _get_val(obj, key)
    return str(v) if v is not None else ""


def _ts_str(ts: Any) -> str:
    """Extract ISO wall_time string from timestamp dict or Timestamp object."""
    if isinstance(ts, dict):
        return str(ts.get("wall_time") or ts.get("world_time") or "")
    if ts is not None:
        # Pydantic Timestamp object
        val = getattr(ts, "wall_time", None) or getattr(ts, "world_time", None)
        return str(val) if val is not None else ""
    return ""


def _extract_scalar_fields(body: Any, cap: int = 5) -> dict[str, Any]:
    """Extract up to `cap` scalar fields from a response dict.

    Preferred fields (id, status, price, etc.) are extracted first.
    Nested dicts, lists, and keys starting with "_" are skipped.
    Falls back to any scalar fields if no preferred fields exist.
    """
    if not isinstance(body, dict):
        return {}
    result: dict[str, Any] = {}
    # Pass 1: preferred fields
    for key in _PREFERRED_FIELDS:
        if len(result) >= cap:
            return result
        val = body.get(key)
        if val is not None and isinstance(val, (str, int, float, bool)):
            result[key] = val
    # Pass 2: any remaining scalars
    for key, val in body.items():
        if len(result) >= cap:
            break
        if key.startswith("_") or key in result:
            continue
        if isinstance(val, (str, int, float, bool)):
            result[key] = val
    return result


class DecisionTraceBuilder:
    """Builds a structured decision trace from run events.

    No constructor dependencies. Single public async method: build().
    Follows the same sub-component pattern as ScorecardComputer.
    """

    async def build(
        self,
        events: list[dict[str, Any]],
        actors: list[dict[str, Any]],
        state_engine: Any,
        game_result: dict[str, Any] | None = None,
        interpreter: DomainInterpreter | None = None,
    ) -> dict[str, Any]:
        """Build complete trace artifact.

        Args:
            events: Raw event dicts from persistence.query_raw(filters={"run_id":...})
            actors: [{id, type, role}] — already filtered to non-HUMAN by caller
            state_engine: For entity count queries (count_entities method, optional)
            game_result: Game outcome dict; auto-extracted from events if None
                         and a "game.terminated" event is present
            interpreter: Optional DomainInterpreter for narrative strings
        """
        # Step 1: Build lookup indexes in one pass
        by_actor, by_type = self._index_events(events)

        # Step 2: Agent actor IDs — exclude system infrastructure
        agent_ids: list[str] = [
            str(a["id"])
            for a in actors
            if str(a.get("id", "")) and str(a.get("id", "")) not in _SYSTEM_ACTORS
        ]

        # Step 3: Extract game_result from events if not provided
        if game_result is None:
            for e in events:
                if str(_get_val(e, "event_type") or "") == "game.terminated":
                    winner = _get_val(e, "winner")
                    game_result = {
                        "reason": str(_get_val(e, "reason", "")),
                        "winner": str(winner) if winner else None,
                        "final_standings": _get_val(e, "final_standings", []),
                        "total_events": int(_get_val(e, "total_events", 0)),
                        "wall_clock_seconds": float(_get_val(e, "wall_clock_seconds", 0.0)),
                        "scoring_mode": str(_get_val(e, "scoring_mode", "")),
                    }
                    break

        # Step 4: Group events into activations by timeline
        all_activations = self._group_activations(events, agent_ids)

        # Step 5: Build action list for each activation
        for act in all_activations:
            act["actions"] = self._build_actions(act["_raw_events"])

        # Step 6: Build world_response — slice the original events list between
        # this activation's last event and the same actor's next activation start.
        # This captures both other-agent events AND system/animator events.
        for i, act in enumerate(all_activations):
            # Find where the same actor next activates
            same_actor_next_start = next(
                (all_activations[j]["_first_event_idx"]
                 for j in range(i + 1, len(all_activations))
                 if all_activations[j]["actor_id"] == act["actor_id"]),
                len(events),  # end of events list if no next activation
            )
            window_start = act["_last_event_idx"] + 1
            window_events = events[window_start:same_actor_next_start]
            act["world_response"] = self._build_world_response(act, window_events)

        # Step 7: Strip internal keys for output
        output_activations = [
            {k: v for k, v in act.items() if not k.startswith("_")}
            for act in all_activations
        ]

        # Step 8: Run-level aggregates
        info_analysis = await self._build_information_analysis(
            events, agent_ids, actors, state_engine
        )
        gov_summary = self._build_governance_summary(events, agent_ids, actors)

        # Step 9: Assemble trace
        trace: dict[str, Any] = {
            "activations": output_activations,
            "information_analysis": info_analysis,
            "governance_summary": gov_summary,
        }
        if game_result is not None:
            trace["game_outcome"] = game_result
        if interpreter is not None:
            trace["domain_narrative"] = interpreter.interpret(
                output_activations, game_result
            )
        return trace

    # ── Internal methods ──────────────────────────────────────────────────────

    def _index_events(
        self,
        events: list[dict[str, Any]],
    ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
        """Build by_actor and by_type lookup dicts in a single pass."""
        by_actor: dict[str, list[dict[str, Any]]] = {}
        by_type: dict[str, list[dict[str, Any]]] = {}
        for e in events:
            aid = _get_str(e, "actor_id")
            etype = _get_str(e, "event_type")
            if aid:
                by_actor.setdefault(aid, []).append(e)
            if etype:
                by_type.setdefault(etype, []).append(e)
        return by_actor, by_type

    def _group_activations(
        self,
        events: list[dict[str, Any]],
        agent_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Group events into per-actor activations by timeline order.

        Walk events in chronological order (events list is asc from query_raw).
        Consecutive events by the same agent form one activation.
        When a different agent's event appears, the current activation ends.
        Governance events (permission.*, policy.*, budget.*) are attached to
        the current activation in progress (not a new activation boundary).
        """
        agent_id_set = set(agent_ids)
        activations: list[dict[str, Any]] = []
        activation_counts: dict[str, int] = {}

        current_actor: str | None = None
        current_batch: list[dict[str, Any]] = []
        batch_start_idx: int = 0
        batch_last_idx: int = 0  # last event's index in events list (incl. governance)

        def _flush(
            actor: str | None,
            batch: list[dict[str, Any]],
            start: int,
            last_idx: int,
        ) -> None:
            if not batch or actor is None:
                return
            n = activation_counts.get(actor, 0) + 1
            activation_counts[actor] = n
            act_id = f"act-{actor}-{n}"

            t_start = _get_val(batch[0], "timestamp") or {}
            t_end = _get_val(batch[-1], "timestamp") or {}
            reason = "kickstart" if n == 1 else "game_event"

            # Cause: last non-system non-same-actor event before batch_start
            cause_event_id: str | None = None
            for pe in reversed(events[:start]):
                pe_aid = _get_str(pe, "actor_id")
                if pe_aid and pe_aid != actor and pe_aid not in _SYSTEM_ACTORS:
                    cause_event_id = _get_str(pe, "event_id")
                    break

            # terminated_by: examine last world.* event in batch
            last_world = next(
                (e for e in reversed(batch)
                 if _get_str(e, "event_type").startswith("world.")),
                batch[-1],
            )
            svc = _get_str(last_world, "service_id")
            action = _get_str(last_world, "action")
            if svc == "game":
                terminated_by = "game_move"
            elif action == "do_nothing":
                terminated_by = "do_nothing"
            else:
                terminated_by = "turn_complete"

            activations.append({
                "activation_id": act_id,
                "actor_id": actor,
                "reason": reason,
                "cause_event_id": cause_event_id,
                "time_start": _ts_str(t_start),
                "time_end": _ts_str(t_end),
                "terminated_by": terminated_by,
                "_raw_events": list(batch),    # stripped before output in build()
                "_first_event_idx": start,     # index in events list
                "_last_event_idx": last_idx,   # index of last event (incl. governance)
            })

        for idx, e in enumerate(events):
            aid = _get_str(e, "actor_id")
            etype = _get_str(e, "event_type")

            if aid not in agent_id_set:
                # Governance event — attach to current batch if one is open
                if etype in _GOVERNANCE_TYPES and current_actor and current_batch:
                    current_batch.append(e)
                    batch_last_idx = idx  # governance event extends the window
                # System/animator events are not activations
                continue

            if aid != current_actor:
                _flush(current_actor, current_batch, batch_start_idx, batch_last_idx)
                current_actor = aid
                current_batch = [e]
                batch_start_idx = idx
                batch_last_idx = idx
            else:
                current_batch.append(e)
                batch_last_idx = idx

        _flush(current_actor, current_batch, batch_start_idx, batch_last_idx)
        return activations

    def _build_actions(
        self,
        events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Build action list from one activation's events.

        Each world.* event = one action entry.
        Governance events (permission.*, policy.*, budget.*) that follow
        a world.* event within 3 positions are overlaid onto that action.
        """
        actions: list[dict[str, Any]] = []
        step = 0

        for i, e in enumerate(events):
            etype = _get_str(e, "event_type")
            # Governance events are overlaid on the preceding world.* event
            if etype in _GOVERNANCE_TYPES:
                continue
            if not etype.startswith("world."):
                continue

            service = _get_str(e, "service_id")
            action = _get_str(e, "action")
            tool_name = f"{service}.{action}" if service and action else (action or service)
            outcome = _get_str(e, "outcome") or "success"
            committed = outcome == "success"
            actor_id = _get_str(e, "actor_id")

            # Governance overlay: scan next 3 events for governance entries
            # matching this actor — pipeline runs synchronously so they appear
            # immediately after in the event stream
            gov: dict[str, Any] = {
                "permission": "allow",
                "policy": "pass",
                "budget_deducted": 0,
            }
            for g in events[i + 1: i + 4]:
                g_etype = _get_str(g, "event_type")
                if _get_str(g, "actor_id") != actor_id:
                    continue
                if g_etype == "permission.denied":
                    gov["permission"] = "deny"
                elif g_etype == "policy.block":
                    gov["policy"] = "block"
                elif g_etype in ("policy.hold", "policy.flag"):
                    gov["policy"] = "flag"
                elif g_etype == "budget.deduction":
                    gov["budget_deducted"] = int(_get_val(g, "amount", 0))

            # Arguments: compact scalars from input_data
            input_data = _get_val(e, "input_data") or {}
            arguments = _extract_scalar_fields(input_data, cap=8)

            state_deltas: list[dict[str, Any]] = _get_val(e, "state_deltas") or []
            response_body = _get_val(e, "response_body")

            effect: dict[str, Any] | None = None
            learned: dict[str, Any] | None = None

            if committed and state_deltas:
                # Write action: extract effect from first state delta
                delta = state_deltas[0] if isinstance(state_deltas[0], dict) else {}
                effect = {
                    "entity_type": str(delta.get("entity_type", "")),
                    "entity_id": str(delta.get("entity_id", "")),
                    "operation": str(delta.get("operation", "update")),
                    "key_changes": _extract_scalar_fields(
                        delta.get("fields", {}), cap=5
                    ),
                }
            elif response_body:
                # Read action: summarize response
                if isinstance(response_body, list):
                    n = len(response_body)
                    first = (
                        response_body[0]
                        if n > 0 and isinstance(response_body[0], dict)
                        else {}
                    )
                    et = str(first.get("entity_type", ""))
                    learned = {
                        "summary": f"{n} entities" + (f" of type {et}" if et else "")
                    }
                elif isinstance(response_body, dict):
                    scalars = _extract_scalar_fields(response_body, cap=5)
                    if scalars:
                        learned = scalars

            entry: dict[str, Any] = {
                "step_index": step,
                "tool_name": tool_name,
                "service": service,
                "arguments": arguments,
                "governance": gov,
                "outcome": outcome,
                "committed": committed,
            }
            if effect is not None:
                entry["effect"] = effect
            if learned is not None:
                entry["learned"] = learned

            actions.append(entry)
            step += 1

        return actions

    def _build_world_response(
        self,
        activation: dict[str, Any],
        interleaved_events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build world_response from events that occurred after this activation.

        interleaved_events: all events from activations between this one and
        the same actor's next activation (other agents' actions + system events).
        """
        direct_cascades: list[dict[str, Any]] = []
        animator_reactions: list[dict[str, Any]] = []

        for e in interleaved_events:
            aid = _get_str(e, "actor_id")
            etype = _get_str(e, "event_type")
            if not etype.startswith("world."):
                continue

            if aid in _SYSTEM_ACTORS:
                svc = _get_str(e, "service_id")
                action = _get_str(e, "action")
                response = _get_val(e, "response_body") or {}
                summary = ""
                if isinstance(response, dict):
                    for key in ("text", "content", "message", "body"):
                        val = response.get(key)
                        if isinstance(val, str):
                            summary = val[:100]
                            break
                if not summary:
                    target = _get_str(e, "target_entity")
                    summary = action + (f" on {target}" if target else "")
                animator_reactions.append({
                    "action": f"{svc}.{action}" if svc else action,
                    "service": svc,
                    "summary": summary,
                })
            elif aid and aid != activation["actor_id"]:
                direct_cascades.append({
                    "actor_id": aid,
                    "action": _get_str(e, "action"),
                    "service": _get_str(e, "service_id"),
                })

        return {
            "direct_cascades": direct_cascades,
            "animator_reactions": animator_reactions,
        }

    async def _build_information_analysis(
        self,
        events: list[dict[str, Any]],
        agent_ids: list[str],
        actors: list[dict[str, Any]],
        state_engine: Any,
    ) -> dict[str, Any]:
        """Per-actor information coverage metrics.

        coverage_ratio = unique target_entity values queried / total entities.
        Falls back to 0 if state_engine lacks count_entities().
        """
        total_entities = 0
        if state_engine is not None and hasattr(state_engine, "count_entities"):
            try:
                total_entities = await state_engine.count_entities()
            except Exception:
                pass

        result: dict[str, Any] = {}
        for actor_id in agent_ids:
            queried: set[str] = set()
            services_used: set[str] = set()

            for e in events:
                if _get_str(e, "actor_id") != actor_id:
                    continue
                if not _get_str(e, "event_type").startswith("world."):
                    continue
                target = _get_val(e, "target_entity")
                if target:
                    queried.add(str(target))
                svc = _get_str(e, "service_id")
                if svc:
                    services_used.add(svc)

            coverage = (
                round(len(queried) / total_entities, 3) if total_entities > 0 else 0.0
            )
            actor_meta = next(
                (a for a in actors if str(a.get("id", "")) == actor_id), {}
            )
            result[actor_id] = {
                "role": actor_meta.get("role", actor_id),
                "entities_available": total_entities,
                "entities_queried": len(queried),
                "unique_services_used": sorted(services_used),
                "coverage_ratio": coverage,
            }
        return result

    def _build_governance_summary(
        self,
        events: list[dict[str, Any]],
        agent_ids: list[str],
        actors: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Per-actor governance aggregate counts."""
        result: dict[str, Any] = {}
        for actor_id in agent_ids:
            actor_events = [
                e for e in events if _get_str(e, "actor_id") == actor_id
            ]
            perms_checked = sum(
                1 for e in actor_events
                if _get_str(e, "event_type").startswith("permission.")
            )
            perms_denied = sum(
                1 for e in actor_events
                if _get_str(e, "event_type") == "permission.denied"
            )
            policies_triggered = sum(
                1 for e in actor_events
                if _get_str(e, "event_type").startswith("policy.")
            )
            policies_blocked = sum(
                1 for e in actor_events
                if _get_str(e, "event_type") == "policy.block"
            )
            budget_consumed = sum(
                int(_get_val(e, "amount", 0))
                for e in actor_events
                if _get_str(e, "event_type") == "budget.deduction"
            )
            actor_meta = next(
                (a for a in actors if str(a.get("id", "")) == actor_id), {}
            )
            result[actor_id] = {
                "role": actor_meta.get("role", actor_id),
                "permissions_checked": perms_checked,
                "permissions_denied": perms_denied,
                "policies_triggered": policies_triggered,
                "policies_blocked": policies_blocked,
                "budget_consumed": budget_consumed,
                "budget_utilization": None,  # requires total budget from actor config
            }
        return result
