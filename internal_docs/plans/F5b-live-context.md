# F5b: Live Console — ContextView + Inspector

## Context

F5a complete (248 tests pass). F5b implements the center (ContextView) and right (Inspector) panels of the Live Console 3-panel layout. Both are currently typed stubs with correct prop interfaces.

**F5b scope:** ContextView (3 modes: overview/event/agent) + Inspector + tests
**Spec source:** `internal_docs/terrarium-frontend-spec.md` lines 434-447

**Decisions from F5a:**
- 3 context modes (overview + event + agent). Entity mode deferred.
- Causal links in event detail are CLICKABLE (update selectedEventId via onSelectEvent callback)
- Inspector shows agent budget bars when actor selected, run metadata when nothing selected

---

## Current State of Stubs

**context-view.tsx** — Has `ContextViewProps` interface with 7 props (runId, run, selectedEventId, selectedActorId, eventCount, onSelectEvent, onClearSelection). Renders placeholder text based on which selection is active.

**inspector.tsx** — Has `InspectorProps` interface with 3 props (runId, selectedActorId, run). Renders placeholder text.

**Page shell (index.tsx)** — Already passes all correct props to both components. No changes needed.

---

## Step 1: ContextView — 3 Modes (~200 lines)

**File:** MODIFY `src/pages/live-console/context-view.tsx`

### Props (already defined, keep as-is):
```tsx
interface ContextViewProps {
  runId: string;
  run: Run;
  selectedEventId: string | null;
  selectedActorId: string | null;
  eventCount: number;
  onSelectEvent: (eventId: string) => void;
  onClearSelection: () => void;
}
```

### Imports needed:
```tsx
import { X, GitBranch } from 'lucide-react';
import type { Run, WorldEvent } from '@/types/domain';
import { useRunEvent } from '@/hooks/queries/use-events';
import { useActor } from '@/hooks/queries/use-actors';
import { QueryGuard } from '@/components/feedback/query-guard';
import { SectionLoading } from '@/components/feedback/section-loading';
import { OutcomeIcon } from '@/components/domain/outcome-icon';
import { ActorBadge } from '@/components/domain/actor-badge';
import { TimestampCell } from '@/components/domain/timestamp-cell';
import { EventTypeBadge } from '@/components/domain/event-type-badge';
import { EnforcementBadge } from '@/components/domain/enforcement-badge';
import { JsonViewer } from '@/components/domain/json-viewer';
import { EntityLink } from '@/components/domain/entity-link';
import { FidelityIndicator } from '@/components/domain/fidelity-indicator';
import { ScoreBar } from '@/components/domain/score-bar';
import { ServiceBadge } from '@/components/domain/service-badge';
import { RunStatusBadge } from '@/components/domain/run-status-badge';
import { formatTick, truncateId, formatCurrency } from '@/lib/formatters';
```

### Mode selection logic:
```tsx
export function ContextView(props: ContextViewProps) {
  const { selectedEventId, selectedActorId } = props;

  if (selectedEventId) return <EventDetailView {...props} />;
  if (selectedActorId) return <AgentDetailView {...props} />;
  return <RunOverviewView {...props} />;
}
```

### Mode 1: RunOverviewView (spec line 440: "Run status overview")

Shows when nothing is selected. Displays:
- Header: "Run Overview"
- RunStatusBadge for run.status
- Metric grid (2x2): Tick, Agents, Events, Services
- Services list: each with ServiceBadge
- Reality badges: reality_preset, behavior, mode

**Sub-component:**
```tsx
function RunOverviewView({ run, eventCount }: ContextViewProps) {
  return (
    <div className="flex h-full flex-col">
      <h2 className="border-b border-border pb-2 text-sm font-semibold">Run Overview</h2>
      <div className="mt-3 flex-1 overflow-y-auto space-y-4">
        {/* Status */}
        <div className="flex items-center gap-2">
          <RunStatusBadge status={run.status} />
          <span className="text-xs text-text-muted">{run.world_name}</span>
        </div>

        {/* Metrics grid */}
        <div className="grid grid-cols-2 gap-3">
          <MetricCard title="Tick" value={run.current_tick} />
          <MetricCard title="Agents" value={`${run.actor_count} active`} />
          <MetricCard title="Events" value={eventCount} />
          <MetricCard title="Services" value={run.services.length} />
        </div>

        {/* Services list */}
        <div>
          <h3 className="mb-2 text-xs font-medium uppercase text-text-muted">Services</h3>
          <div className="space-y-1">
            {run.services.map((s) => (
              <div key={s.service_id} className="flex items-center gap-2">
                <ServiceBadge serviceId={s.service_id} tier={s.fidelity_tier} />
              </div>
            ))}
          </div>
        </div>

        {/* Conditions */}
        <div className="flex flex-wrap gap-1.5">
          {[run.reality_preset, run.behavior, run.mode].map((badge) => (
            <span key={badge} className="rounded-full bg-bg-elevated px-2 py-0.5 text-xs text-text-secondary">{badge}</span>
          ))}
        </div>
      </div>
    </div>
  );
}

function MetricCard({ title, value }: { title: string; value: React.ReactNode }) {
  return (
    <div className="rounded border border-bg-elevated bg-bg-surface p-3 transition-colors hover:border-border">
      <p className="text-xs font-medium uppercase text-text-muted">{title}</p>
      <p className="mt-0.5 font-mono text-lg font-semibold">{value}</p>
    </div>
  );
}
```

### Mode 2: EventDetailView (spec line 441: "Full event detail")

Shows when event is selected. Follows EXACT pattern from F4b events-tab.tsx EventDetail (lines 326-491). Key sections:

1. Header: "Event: {truncateId}" + EventTypeBadge + close button (X, type="button", aria-label="Close detail")
2. Summary: `actor → action → OUTCOME`
3. Input/Output: two JsonViewer panels in grid-cols-1 md:grid-cols-2
4. Budget impact: budget_delta + budget_remaining
5. Policy section (if policy_hit): EnforcementBadge + policy details
6. Entity IDs: EntityLink components
7. Causal chain: **CLICKABLE** CausalLink buttons that call `onSelectEvent(eventId)` — NOT the shared CausalChain component (which copies)
8. FidelityIndicator
9. "[View causal chain →]" label

**Custom CausalLink (local to this file, same as events-tab.tsx):**
```tsx
function CausalLink({ eventId, onSelect }: { eventId: string; onSelect: (id: string) => void }) {
  return (
    <button type="button" onClick={() => onSelect(eventId)}
      className="font-mono text-xs text-info hover:underline underline-offset-2" title={eventId}>
      {truncateId(eventId, 12)}
    </button>
  );
}
```

**EventDetailView sub-component:**
```tsx
function EventDetailView({ runId, selectedEventId, onSelectEvent, onClearSelection }: ContextViewProps) {
  const eventQuery = useRunEvent(runId, selectedEventId!);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border pb-2">
        <h2 className="text-sm font-semibold">
          Event: <span className="font-mono">{truncateId(selectedEventId!, 16)}</span>
        </h2>
        <button type="button" onClick={onClearSelection} aria-label="Close detail"
          className="rounded p-1 text-text-muted hover:bg-bg-hover hover:text-text-primary transition-colors">
          <X size={16} />
        </button>
      </div>
      <div className="mt-3 flex-1 overflow-y-auto">
        <QueryGuard query={eventQuery} loadingFallback={<SectionLoading />}>
          {(event) => (
            <div className="space-y-4">
              {/* Summary */}
              <p className="text-sm text-text-secondary">
                <span className="text-text-primary">{event.actor_id}</span> → {event.action} →{' '}
                <span className="uppercase font-medium">{event.outcome}</span>
              </p>

              {/* Input / Output */}
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <div>
                  <p className="mb-1 text-xs font-medium uppercase text-text-muted">Input</p>
                  <JsonViewer data={event.input_data} />
                </div>
                <div>
                  <p className="mb-1 text-xs font-medium uppercase text-text-muted">Output</p>
                  <JsonViewer data={event.output_data} />
                </div>
              </div>

              {/* Budget impact */}
              {(event.budget_delta !== 0 || event.budget_remaining > 0) && (
                <div className="text-sm text-text-secondary">
                  <span className="text-xs font-medium uppercase text-text-muted">Budget: </span>
                  <span className="font-mono">{event.budget_delta < 0 ? '-' : '+'}{formatCurrency(Math.abs(event.budget_delta))}</span>
                  <span className="text-text-muted"> → </span>
                  <span className="font-mono">{formatCurrency(event.budget_remaining)} remaining</span>
                </div>
              )}

              {/* Policy section */}
              {event.policy_hit && (
                <div className="rounded border border-bg-elevated p-3">
                  <p className="mb-1 text-xs font-medium uppercase text-text-muted">Policy</p>
                  <p className="text-sm text-text-secondary">
                    {event.policy_hit.policy_name}: <EnforcementBadge enforcement={event.policy_hit.enforcement} />
                  </p>
                  {event.policy_hit.resolution && <p className="text-xs text-text-muted mt-1">→ {event.policy_hit.resolution}</p>}
                </div>
              )}

              {/* Entity IDs */}
              {event.entity_ids.length > 0 && (
                <div>
                  <p className="mb-1 text-xs font-medium uppercase text-text-muted">Entities</p>
                  <div className="flex flex-wrap gap-2">
                    {event.entity_ids.map((eid) => <EntityLink key={eid} runId={runId} entityId={eid} />)}
                  </div>
                </div>
              )}

              {/* Causal chain — CLICKABLE */}
              {(event.caused_by || event.causal_parent_ids.length > 0) && (
                <div>
                  <div className="flex items-center gap-1 text-xs text-text-muted mb-1">
                    <GitBranch size={12} /><span>Caused by:</span>
                  </div>
                  <div className="ml-3 flex flex-wrap gap-2">
                    {event.caused_by && <CausalLink eventId={event.caused_by} onSelect={onSelectEvent} />}
                    {event.causal_parent_ids.filter(id => id !== event.caused_by).map((id) => (
                      <CausalLink key={id} eventId={id} onSelect={onSelectEvent} />
                    ))}
                  </div>
                </div>
              )}
              {event.causal_child_ids.length > 0 && (
                <div>
                  <div className="flex items-center gap-1 text-xs text-text-muted mb-1">
                    <GitBranch size={12} /><span>Caused:</span>
                  </div>
                  <div className="ml-3 flex flex-wrap gap-2">
                    {event.causal_child_ids.map((id) => (
                      <CausalLink key={id} eventId={id} onSelect={onSelectEvent} />
                    ))}
                  </div>
                </div>
              )}

              {/* Fidelity */}
              <FidelityIndicator tier={event.fidelity_tier} source={event.fidelity?.fidelity_source ?? undefined} />
            </div>
          )}
        </QueryGuard>
      </div>
    </div>
  );
}
```

### Mode 3: AgentDetailView (spec line 443: "Agent profile")

Shows when agent is selected (no event selected). Displays:
- Header: "Agent: {actorId}" + close button
- `useActor(runId, selectedActorId!)` wrapped in QueryGuard
- Role + actor_type
- Budget bars: one ScoreBar per budget type (api_calls, llm_spend_usd, world_actions) with ratio `remaining/total`
- Action count
- Governance score (if available)

**Budget bar keys (data-driven Record):**
```tsx
const BUDGET_LABELS: Record<string, string> = {
  api_calls: 'API Calls',
  llm_spend_usd: 'LLM Spend',
  world_actions: 'World Actions',
};
```

**AgentDetailView sub-component:**
```tsx
function AgentDetailView({ runId, selectedActorId, onClearSelection }: ContextViewProps) {
  const actorQuery = useActor(runId, selectedActorId!);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border pb-2">
        <h2 className="text-sm font-semibold">
          Agent: <span className="font-mono">{truncateId(selectedActorId!, 16)}</span>
        </h2>
        <button type="button" onClick={onClearSelection} aria-label="Close detail"
          className="rounded p-1 text-text-muted hover:bg-bg-hover hover:text-text-primary transition-colors">
          <X size={16} />
        </button>
      </div>
      <div className="mt-3 flex-1 overflow-y-auto">
        <QueryGuard query={actorQuery} loadingFallback={<SectionLoading />}>
          {(agent) => (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <ActorBadge actorId={agent.actor_id} role={agent.role} />
                <span className="rounded-full bg-bg-elevated px-2 py-0.5 text-xs text-text-muted">{agent.actor_type}</span>
              </div>

              {/* Budget bars */}
              <div>
                <h3 className="mb-2 text-xs font-medium uppercase text-text-muted">Budget</h3>
                <div className="space-y-2">
                  {Object.entries(BUDGET_LABELS).map(([key, label]) => {
                    const remaining = agent.budget_remaining[key as keyof typeof agent.budget_remaining] ?? 0;
                    const total = agent.budget_total[key as keyof typeof agent.budget_total] ?? 1;
                    return <ScoreBar key={key} value={total > 0 ? remaining / total : 0} label={label} />;
                  })}
                </div>
              </div>

              {/* Stats */}
              <div className="flex gap-4 text-xs text-text-muted">
                <span>Actions: <span className="font-mono text-text-primary">{agent.action_count}</span></span>
                {agent.governance_score != null && (
                  <span>Score: <span className="font-mono text-text-primary">{Math.round(agent.governance_score * 100)}</span></span>
                )}
              </div>
            </div>
          )}
        </QueryGuard>
      </div>
    </div>
  );
}
```

---

## Step 2: Inspector — Right Panel (~100 lines)

**File:** MODIFY `src/pages/live-console/inspector.tsx`

### Props (keep existing interface):
```tsx
interface InspectorProps {
  runId: string;
  selectedActorId: string | null;
  run: Run;
}
```

### Two modes:

**When selectedActorId provided:**
- `useActor(runId, selectedActorId)` wrapped in QueryGuard
- Shows: "AGENT INSPECTOR" header, ActorBadge, role, actor_type, budget bars (ScoreBar per type), action count, governance score

**When null:**
- Shows: "INSPECTOR" header, static run summary: mode, preset, actor count, services list

### Full implementation:
```tsx
import type { Run } from '@/types/domain';
import { useActor } from '@/hooks/queries/use-actors';
import { QueryGuard } from '@/components/feedback/query-guard';
import { SectionLoading } from '@/components/feedback/section-loading';
import { ActorBadge } from '@/components/domain/actor-badge';
import { ScoreBar } from '@/components/domain/score-bar';
import { ServiceBadge } from '@/components/domain/service-badge';

interface InspectorProps {
  runId: string;
  selectedActorId: string | null;
  run: Run;
}

const BUDGET_LABELS: Record<string, string> = {
  api_calls: 'API Calls',
  llm_spend_usd: 'LLM Spend',
  world_actions: 'World Actions',
};

export function Inspector({ runId, selectedActorId, run }: InspectorProps) {
  if (selectedActorId) {
    return <AgentInspector runId={runId} actorId={selectedActorId} />;
  }
  return <RunInspector run={run} />;
}

function AgentInspector({ runId, actorId }: { runId: string; actorId: string }) {
  const actorQuery = useActor(runId, actorId);
  return (
    <div className="flex h-full flex-col">
      <h2 className="border-b border-border pb-2 text-xs font-medium uppercase text-text-muted">
        Agent Inspector
      </h2>
      <div className="mt-3 flex-1 overflow-y-auto">
        <QueryGuard query={actorQuery} loadingFallback={<SectionLoading />}>
          {(agent) => (
            <div className="space-y-4">
              <ActorBadge actorId={agent.actor_id} role={agent.role} />
              <span className="rounded-full bg-bg-elevated px-2 py-0.5 text-xs text-text-muted">{agent.actor_type}</span>

              <div>
                <h3 className="mb-2 text-xs font-medium uppercase text-text-muted">Budget</h3>
                <div className="space-y-2">
                  {Object.entries(BUDGET_LABELS).map(([key, label]) => {
                    const remaining = agent.budget_remaining[key as keyof typeof agent.budget_remaining] ?? 0;
                    const total = agent.budget_total[key as keyof typeof agent.budget_total] ?? 1;
                    return <ScoreBar key={key} value={total > 0 ? remaining / total : 0} label={label} />;
                  })}
                </div>
              </div>

              <div className="space-y-1 text-xs text-text-muted">
                <p>Actions: <span className="font-mono text-text-primary">{agent.action_count}</span></p>
                {agent.governance_score != null && (
                  <p>Score: <span className="font-mono text-text-primary">{Math.round(agent.governance_score * 100)}</span></p>
                )}
              </div>
            </div>
          )}
        </QueryGuard>
      </div>
    </div>
  );
}

function RunInspector({ run }: { run: Run }) {
  return (
    <div className="flex h-full flex-col">
      <h2 className="border-b border-border pb-2 text-xs font-medium uppercase text-text-muted">
        Inspector
      </h2>
      <div className="mt-3 flex-1 overflow-y-auto space-y-4">
        <div className="flex flex-wrap gap-1.5">
          {[run.mode, run.reality_preset, run.behavior].map((badge) => (
            <span key={badge} className="rounded-full bg-bg-elevated px-2 py-0.5 text-xs text-text-secondary">{badge}</span>
          ))}
        </div>
        <div className="text-xs text-text-muted">
          <p>Actors: <span className="font-mono text-text-primary">{run.actor_count}</span></p>
          <p className="mt-1">Services: <span className="font-mono text-text-primary">{run.services.length}</span></p>
        </div>
        <div>
          <h3 className="mb-2 text-xs font-medium uppercase text-text-muted">Services</h3>
          <div className="space-y-1">
            {run.services.map((s) => (
              <ServiceBadge key={s.service_id} serviceId={s.service_id} tier={s.fidelity_tier} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
```

---

## Step 3: Tests (~12 new cases)

**File:** MODIFY `tests/pages/live-console.test.tsx`

Add to existing `describe('LiveConsolePage')` block. New test sections:

### ContextView tests (6):
1. default center view shows run overview (RunStatusBadge text, metric cards)
2. click event in feed shows event detail in center (click tr → "Event:" appears)
3. event detail shows input/output section ("Input", "Output" labels)
4. close button in context view clears selection (aria-label "Close detail" → click → overview returns)
5. click actor in feed shows agent detail (useActor fires → "Agent:" header)
6. agent detail shows budget bars ("Budget" heading)

### Inspector tests (4):
7. inspector shows run metadata when no actor selected ("Inspector" heading)
8. inspector shows services list (ServiceBadge data)
9. inspector shows agent data when actor selected ("Agent Inspector" heading)
10. inspector shows budget labels when actor selected ("API Calls" etc.)

### Interaction tests (2):
11. click event → then click close → returns to overview
12. selection state wires correctly (click event → both center + inspector update)

**Test implementation follows exact patterns from F4b and F5a tests.**

---

## Step 4: Update Docs

- IMPLEMENTATION_STATUS.md: F5=done, session log, Live Console → ✅ done
- `internal_docs/plans/F5b-live-context.md`: save plan

---

## Verification

1. `npm run typecheck` — 0 errors
2. `npm run lint` — 0 errors
3. `npm run test` — F1-F5a (248) + F5b (~12) = ~260 tests pass, ~2 remaining todos (F6 compare)
4. `npm run build` — succeeds
5. Visual: `/runs/test-1/live` → 3-panel with working event detail, agent inspector, run overview

---

## File Manifest

**Modify — Source (2):**
- `src/pages/live-console/context-view.tsx` — full 3-mode implementation (~200 lines)
- `src/pages/live-console/inspector.tsx` — full 2-mode implementation (~100 lines)

**Modify — Tests (1):**
- `tests/pages/live-console.test.tsx` — add ~12 new test cases

**Modify — Docs (1):**
- `IMPLEMENTATION_STATUS.md`

**No changes to index.tsx** — page shell already passes correct props.

**Total: 4 files.**
