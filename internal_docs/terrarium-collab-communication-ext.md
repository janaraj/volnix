# Terrarium — Collaborative Communication Extension

**Extends:** AgencyEngine Implementation Spec (v2)

**Purpose:** Enable internal actors to communicate with each other through services, creating the foundation for collaborative intelligence. This is the missing piece that turns autonomous actors from independent decision-makers into collaborators who build on each other's work.

**Scope:** Additions and modifications to existing AgencyEngine interfaces only. No new systems.

---

## The Gap

Today, when Actor A posts a message in a shared channel, Actor B has no way to know it happened. The AgencyEngine activates actors when their `watched_entities` are touched, but there's no mechanism to say "B is listening to the #research channel" and route A's message as a notification to B.

Without this, actors are deaf to each other. They can act in the same world but can't collaborate.

---

## Addition 1: Subscriptions

Each actor declares what they're listening to. Set at compile time based on the actor's role, permissions, and world structure.

```python
@dataclass
class Subscription:
    """What this actor is listening to in the world."""
    service_id: str                                     # "chat" | "email" | "documents" | "tickets" | etc.
    filter: dict                                        # service-specific match criteria
    sensitivity: Literal["immediate", "batch", "passive"]

# Examples:
# Researcher subscribed to shared chat channel
Subscription(service_id="chat", filter={"channel": "#research"}, sensitivity="immediate")

# Support agent subscribed to ticket assignments
Subscription(service_id="tickets", filter={"assigned_to": "self"}, sensitivity="immediate")

# Supervisor subscribed to all escalations
Subscription(service_id="tickets", filter={"status": "escalated"}, sensitivity="immediate")

# Social media user subscribed to their feed
Subscription(service_id="feed", filter={"type": "following"}, sensitivity="batch")

# Researcher subscribed to shared document changes
Subscription(service_id="documents", filter={"folder": "shared-research"}, sensitivity="immediate")
```

**Sensitivity levels:**

| Level | Behavior |
|-------|----------|
| `immediate` | Actor activates on the same tick the event is committed. Use for direct messages, mentions, critical updates. |
| `batch` | Notifications accumulate. Actor activates after N notifications or a time window. Use for feed updates, low-priority channels. |
| `passive` | Notification stored but actor doesn't auto-activate. Only seen when actor checks manually (via scheduled check). Use for background awareness. |

**Add to ActorState:**

```python
# New field on ActorState
subscriptions: list[Subscription]
```

**Compile-time generation:** The world compiler generates subscriptions based on the actor's role and the world's service topology. A researcher in a world with a `#research` channel automatically gets a subscription to it. A customer in a support world gets subscriptions to their own tickets and email. The compiler infers these from the world definition — no manual configuration needed.

---

## Addition 2: Notification Routing in AgencyEngine.notify()

Modify the existing `notify()` method to check subscriptions after every committed event.

```python
def notify(self, committed_event: WorldEvent):
    """Extended: now checks subscriptions in addition to watched_entities."""
    
    activated = []
    
    # EXISTING: actors whose watched_entities were touched
    affected = self.find_affected_actors(committed_event)
    for actor in affected:
        actor.pending_notifications.append(self.summarize_event(committed_event))
        activated.append((actor, "event_affected"))
    
    # NEW: actors whose subscriptions match this event
    for actor in self.actors:
        if actor.actor_id == committed_event.actor_id:
            continue  # don't notify yourself
        
        for sub in actor.subscriptions:
            if self.matches_subscription(committed_event, sub):
                actor.pending_notifications.append(self.summarize_event(committed_event))
                
                if sub.sensitivity == "immediate":
                    activated.append((actor, "subscription_triggered"))
                elif sub.sensitivity == "batch":
                    actor.batch_notification_count += 1
                    if actor.batch_notification_count >= actor.batch_threshold:
                        activated.append((actor, "batch_triggered"))
                        actor.batch_notification_count = 0
                # passive: notification stored, no activation
                
                break  # one match per actor per event is enough
    
    # EXISTING: scheduled actions, threshold checks
    # ... (unchanged)
    
    # EXISTING: generate actions for activated actors
    for actor, reason in activated:
        self.activate_actor(actor, reason, committed_event)


def matches_subscription(self, event: WorldEvent, sub: Subscription) -> bool:
    """Check if a committed event matches an actor's subscription."""
    
    if event.target_service != sub.service_id:
        return False
    
    # Match filter criteria against event payload and entity attributes
    for key, value in sub.filter.items():
        if key == "self":
            # Special: matches events targeting this actor specifically
            continue
        
        # Check event payload
        if key in event.output and event.output[key] == value:
            continue
        
        # Check event metadata
        if key in event.metadata and event.metadata[key] == value:
            continue
        
        # No match on this filter key
        return False
    
    return True
```

**Key behavior:** The actor who CREATED the event is never notified of their own action. The `actor_id == committed_event.actor_id` check prevents self-notification loops.

---

## Addition 3: Richer Interaction Records

Replace the flat string list with structured records that track WHO said WHAT and whether the actor observed it directly or was notified.

```python
@dataclass
class InteractionRecord:
    """One interaction this actor is aware of."""
    tick: int
    actor_id: str                                       # who performed the action
    actor_role: str                                     # "researcher-A" | "customer" | "supervisor"
    action: str                                         # "chat_send" | "doc_update" | "ticket_comment"
    summary: str                                        # compact natural language description
    source: Literal["self", "observed", "notified"]     # how this actor learned about it
    event_id: str                                       # reference to the original WorldEvent
    reply_to: str | None                                # if this was a reply, what it replied to
```

**Modify on ActorState:**

```python
# Replace
recent_interactions: list[str]

# With
recent_interactions: list[InteractionRecord]
max_interactions: int = 20                              # keep last N, compact older ones
```

**How this feeds into prompts:**

When the ActorPromptBuilder assembles context for an actor, it renders `recent_interactions` as a conversation-like context:

```
Recent activity you're aware of:
- [tick 23] Researcher-A (atmospheric physics): "Initial analysis suggests 
  the jet stream pattern is anomalous" (posted in #research)
- [tick 25] Researcher-C (statistics): "A's sample size is too small for 
  that conclusion" (reply to A's post)  
- [tick 27] You posted: "I found supporting ocean temperature data that 
  strengthens A's hypothesis" (posted in #research)
- [tick 30] Researcher-D (data analysis): Shared new dataset in 
  shared-research/ocean-temps-2024.csv
```

The LLM sees a collaborative context — who said what, who challenged whom, what's been shared — and generates actions that build on it naturally. No explicit coordination mechanism needed. The coordination emerges from shared awareness.

---

## Addition 4: Pending Tasks

Allow actors to accumulate tasks across activations for multi-step coherence.

```python
# Add to ActorState
pending_tasks: list[str]                                # populated by LLM during action generation
goal_context: str | None                                # broader context for the current goal
```

**How it works:**

When the LLM generates an action for an actor, it can also return pending tasks:

```json
{
    "action_type": "chat_send",
    "payload": {
        "channel": "#research",
        "content": "I found a correlation between ocean temps and jet stream anomaly..."
    },
    "state_updates": {
        "pending_tasks": [
            "Cross-reference with Researcher-D's new dataset",
            "Review Researcher-C's statistical objection"
        ],
        "frustration_delta": 0,
        "waiting_for": null
    }
}
```

Next activation, the LLM sees the pending tasks in the prompt context and picks the most relevant one. Tasks are completed or replaced as the actor progresses. This gives coherent multi-step behavior ("I posted my finding, now I need to verify it against D's data, then address C's challenge") without a planner.

**Prompt integration:**

```
Your current goal: Contribute atmospheric physics expertise to climate 
modeling research
Goal context: Collaborative research with 4 other specialists

Your pending tasks:
1. Cross-reference with Researcher-D's new dataset (ocean-temps-2024.csv)
2. Review Researcher-C's statistical objection to your analysis

Choose your next action based on priority and available information.
```

---

## Addition 5: Reply-To in Action Payloads

Enable actors to explicitly reference prior messages/events when responding, creating threaded conversations and traceable causal chains.

```python
# In ActionEnvelope.payload, any communication action can include:
{
    "channel": "#research",
    "content": "Building on A's analysis, I found additional evidence...",
    "reply_to_event_id": "evt_00234"    # A's original message
}
```

**What this does:**

1. The committed WorldEvent gets `parent_event_ids` populated with `evt_00234`. The causal graph now shows B's message was a direct response to A's.

2. When someone traces the final conclusion backward, they see the full chain: Synthesis → built on B's evidence → which replied to A's analysis → which was triggered by the initial problem statement.

3. The dashboard's causal chain view becomes a readable collaborative narrative, not just a list of events.

**Implementation:** The pipeline already supports `parent_event_ids` on WorldEvent. The `reply_to_event_id` in the payload just needs to be copied into `parent_event_ids` during envelope → event conversion. Minimal change.

---

## Addition 6: Scheduled Periodic Checks

For collaborative roles, actors need periodic "thinking time" — moments where they proactively review shared state rather than waiting for a notification.

**This uses the existing scheduled activation mechanism.** The only change is at compile time: the world compiler generates periodic check schedules for actors in collaborative roles.

```python
# At compile time, for a researcher actor:
scheduled_actions = [
    ScheduledAction(
        logical_time=10.0,
        action_type="review_shared_state",
        description="Check #research channel and shared documents for updates",
        payload={"services": ["chat", "documents"], "scope": "subscriptions"}
    ),
    ScheduledAction(
        logical_time=20.0,
        action_type="review_shared_state",
        description="Check #research channel and shared documents for updates",
        payload={"services": ["chat", "documents"], "scope": "subscriptions"}
    ),
    # ... every N ticks
]
```

When this scheduled action fires, the actor reads their subscribed services, updates their `recent_interactions` with anything they missed, and the LLM decides if there's anything worth responding to. If not, the actor does nothing and the next check is already scheduled.

**Compile-time generation rule:** Any actor whose role involves collaboration (detected from the world definition — shared channels, shared documents, team membership) gets periodic checks generated automatically. The interval is influenced by the complexity.urgency dimension — higher urgency = more frequent checks.

---

## Summary of All Changes

### New Types

| Type | Description |
|------|------------|
| `Subscription` | Service + filter + sensitivity. What an actor is listening to. |
| `InteractionRecord` | Structured record of an interaction this actor is aware of. |

### Modified on ActorState

| Field | Change |
|-------|--------|
| `subscriptions: list[Subscription]` | **NEW.** What this actor listens to. |
| `recent_interactions: list[InteractionRecord]` | **MODIFIED.** Was `list[str]`, now structured records with source tracking. |
| `pending_tasks: list[str]` | **NEW.** LLM-populated task list for multi-step coherence. |
| `goal_context: str \| None` | **NEW.** Broader context for the current goal. |
| `batch_notification_count: int` | **NEW.** Counter for batch sensitivity subscriptions. |
| `batch_threshold: int` | **NEW.** How many batch notifications before activation. |

### Modified Methods

| Method | Change |
|--------|--------|
| `AgencyEngine.notify()` | **EXTENDED.** Now checks subscriptions in addition to watched_entities. Routes notifications by sensitivity level. |
| `AgencyEngine.matches_subscription()` | **NEW method.** Matches committed events against actor subscriptions. |
| `ActorPromptBuilder.build_individual_prompt()` | **EXTENDED.** Renders `recent_interactions` as conversational context with attribution. Includes `pending_tasks`. |

### Modified on ActionEnvelope

| Field | Change |
|-------|--------|
| `payload.reply_to_event_id` | **CONVENTION.** Any communication action can include this. Pipeline copies it to `parent_event_ids` on the committed WorldEvent. |

### Compile-Time Changes

| Change | Description |
|--------|------------|
| Subscription generation | Compiler infers subscriptions from actor role + service topology. |
| Periodic check scheduling | Compiler generates scheduled `review_shared_state` actions for collaborative roles. |
| Pending tasks initialization | Compiler can seed initial pending_tasks from the world definition seeds. |

---

## What This Does NOT Add

- No new engine or system. All changes are modifications to AgencyEngine and ActorState.
- No direct actor-to-actor communication channel. Everything still goes through services and the pipeline.
- No coordination protocol or alliance system. Coordination emerges from shared awareness.
- No ambient random activity. Periodic checks are deterministic scheduled actions.
- No multi-goal planner. Pending tasks are a flat list managed by the LLM.
- No new activation triggers. Subscription-triggered activation is a specialization of the existing event-affected trigger.
