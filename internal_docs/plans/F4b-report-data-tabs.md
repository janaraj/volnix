# F4b: Run Report — Data Tabs (Events + Entities + Gaps)

## Context

F4a complete (215 tests pass). F4b implements the 3 data-heavy tabs. The Events tab is the most complex component in the entire app (~250 lines, TanStack Table v8, URL filters, event detail panel). Implementation order: simplest first (Gaps → Entities → Events).

**Spec source:** `internal_docs/terrarium-frontend-spec.md` lines 602-745

---

## Spec Cross-Check — Items That MUST Be Covered

### Events Tab (spec lines 602-660):
- [x] "EVENTS (847 total)" header with count
- [x] Filter bar: `[Actor ▾] [Service ▾] [Outcome ▾] [Type ▾] [Search…]` — 4 selects + search input
- [x] TanStack Table columns: Tick, Time, Actor, Action, Outcome — sortable
- [x] Row click selects event → detail panel appears below
- [x] "Page 1 of 18 [◀] ... [▶]" pagination
- [x] Event detail: "Event: evt_00051" header
- [x] Event detail: "agent-alpha → refund_create → POLICY HOLD" summary line
- [x] Event detail: Input/Output JSON panels side-by-side
- [x] Event detail: Policy section (policy name, rule/condition, enforcement badge + resolution)
- [x] Event detail: **budget_delta and budget_remaining** display (spec line 659: "budget impact")
- [x] Event detail: Causal chain — "Caused by: evt_00048" + "Caused: evt_00053..."
- [x] Event detail: **Causal links are CLICKABLE** → update `?event=` param (spec line 660, key interactions line 1070)
- [x] Event detail: **entity_ids clickable** → navigate to `?tab=entities&entity=id` (key interactions line 1068)
- [x] "[View causal chain →]" label
- [x] Fidelity tier display on event detail

### Entities Tab (spec lines 662-713):
- [x] "ENTITIES (287 total)" header with count
- [x] Type filter: dropdown with entity types
- [x] Entity card: ID + key fields + state change count + last updated + [View] button
- [x] Selected entity highlighted
- [x] Entity detail: "Entity: TK-2847" header + close button
- [x] Entity detail: Current State as JsonViewer
- [x] Entity detail: History timeline — vertical list with connectors
- [x] History format: "field → new_value: timestamp · by actor_id"

### Gaps Tab (spec lines 716-745):
- [x] "CAPABILITY GAPS (4 detected)" header with count
- [x] Gap table columns: Event/Tick, Agent, Gap (tool + description), Response
- [x] Distribution summary: Hallucinated N (X%), Adapted N (X%), Escalated N (X%), Skipped N (X%)
- [x] Each response type has icon + color
- [x] Empty state: "No capability gaps detected"

### Key Interactions (spec lines 1063-1078) applicable to F4b:
- [x] "Click entity in event detail → Navigates to entity detail in entities tab" — render entity_ids as EntityLink components
- [x] "Click causal parent/child → Navigates to that event" — causal chain items update `?event=` param
- [ ] "Click actor name → Opens agent inspector" — v1: ActorBadge copies ID (full inspector is F5)
- [x] "Filter events → URL updates, shareable filter state"

---

## Step 0: Fix index.tsx

**File:** MODIFY `src/pages/run-report/index.tsx`

Change 3 lines in `ActiveTab`:
```tsx
case 'events':    return <EventsTab runId={runId} />;
case 'entities':  return <EntitiesTab runId={runId} />;
case 'gaps':      return <GapsTab runId={runId} />;
```

---

## Step 1: Gaps Tab (~130 lines)

**File:** MODIFY `src/pages/run-report/tabs/gaps-tab.tsx`

### Full implementation code:

```tsx
import { useMemo } from 'react';
import { AlertTriangle, CheckCircle2, Circle } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useCapabilityGaps } from '@/hooks/queries/use-gaps';
import { QueryGuard } from '@/components/feedback/query-guard';
import { SectionLoading } from '@/components/feedback/section-loading';
import { EmptyState } from '@/components/feedback/empty-state';
import { ActorBadge } from '@/components/domain/actor-badge';
import { TimestampCell } from '@/components/domain/timestamp-cell';
import { gapResponseToLabel } from '@/lib/classifiers';
import { truncateId } from '@/lib/formatters';
import type { CapabilityGap } from '@/types/domain';

interface GapsTabProps {
  runId: string;
}

// Data-driven response styling
const GAP_RESPONSE_COLORS: Record<string, string> = {
  hallucinated: 'text-error',
  adapted: 'text-success',
  escalated: 'text-success',
  skipped: 'text-neutral',
};
const GAP_RESPONSE_BG: Record<string, string> = {
  hallucinated: 'bg-error/10',
  adapted: 'bg-success/10',
  escalated: 'bg-success/10',
  skipped: 'bg-neutral/10',
};
const GAP_RESPONSE_ICONS: Record<string, LucideIcon> = {
  hallucinated: AlertTriangle,
  adapted: CheckCircle2,
  escalated: CheckCircle2,
  skipped: Circle,
};

// -- Distribution Summary --
function GapDistribution({ gaps }: { gaps: CapabilityGap[] }) {
  const distribution = useMemo(() => {
    const counts: Record<string, number> = { hallucinated: 0, adapted: 0, escalated: 0, skipped: 0 };
    for (const g of gaps) counts[g.response] = (counts[g.response] ?? 0) + 1;
    const total = gaps.length;
    return Object.entries(counts).map(([response, count]) => ({
      response, count, pct: total > 0 ? Math.round((count / total) * 100) : 0,
    }));
  }, [gaps]);

  return (
    <div className="mb-4 flex flex-wrap gap-3">
      {distribution.map(({ response, count, pct }) => {
        const Icon = GAP_RESPONSE_ICONS[response] ?? Circle;
        const color = GAP_RESPONSE_COLORS[response] ?? 'text-text-muted';
        const bg = GAP_RESPONSE_BG[response] ?? '';
        return (
          <div key={response} className={`flex items-center gap-2 rounded-lg border border-bg-elevated px-3 py-2 ${bg}`}>
            <Icon size={14} className={color} />
            <span className="text-sm font-medium text-text-primary">{gapResponseToLabel(response)}:</span>
            <span className="font-mono text-sm text-text-secondary">{count} ({pct}%)</span>
          </div>
        );
      })}
    </div>
  );
}

// -- Main Component --
export function GapsTab({ runId }: GapsTabProps) {
  const gapsQuery = useCapabilityGaps(runId);

  return (
    <QueryGuard query={gapsQuery} loadingFallback={<SectionLoading />}>
      {(gaps) => {
        if (gaps.length === 0) {
          return (
            <div>
              <h2 className="mb-3 text-lg font-semibold">
                CAPABILITY GAPS <span className="font-normal text-text-muted">(0 detected)</span>
              </h2>
              <EmptyState title="No capability gaps detected"
                description="All requested tools were available in the world." />
            </div>
          );
        }
        return (
          <div>
            <h2 className="mb-3 text-lg font-semibold">
              CAPABILITY GAPS <span className="font-normal text-text-muted">({gaps.length} detected)</span>
            </h2>
            <GapDistribution gaps={gaps} />
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-bg-elevated">
                    <th className="px-3 py-2 text-left text-xs font-medium uppercase text-text-muted">Event</th>
                    <th className="px-3 py-2 text-left text-xs font-medium uppercase text-text-muted">Agent</th>
                    <th className="px-3 py-2 text-left text-xs font-medium uppercase text-text-muted">Gap</th>
                    <th className="px-3 py-2 text-left text-xs font-medium uppercase text-text-muted">Response</th>
                  </tr>
                </thead>
                <tbody>
                  {gaps.map((gap) => {
                    const Icon = GAP_RESPONSE_ICONS[gap.response] ?? Circle;
                    const color = GAP_RESPONSE_COLORS[gap.response] ?? 'text-text-muted';
                    return (
                      <tr key={gap.event_id} className="border-b border-bg-elevated">
                        <td className="px-3 py-2">
                          <span className="font-mono text-xs text-text-muted">{truncateId(gap.event_id, 12)}</span>
                        </td>
                        <td className="px-3 py-2"><ActorBadge actorId={gap.actor_id} /></td>
                        <td className="px-3 py-2">
                          <span className="font-mono text-xs text-info">{gap.requested_tool}</span>
                          <p className="text-xs text-text-muted">{gap.description}</p>
                        </td>
                        <td className="px-3 py-2">
                          <span className={`inline-flex items-center gap-1 text-xs font-medium ${color}`}>
                            <Icon size={14} />
                            {gapResponseToLabel(gap.response)}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        );
      }}
    </QueryGuard>
  );
}
```

---

## Step 2: Entities Tab (~180 lines)

**File:** MODIFY `src/pages/run-report/tabs/entities-tab.tsx`

### Key code patterns:

**EntityCard sub-component:**
- Shows entity_id (font-mono), entity_type badge, first 4 fields from `entity.fields`, state_history count, updated_at
- [View] button with `type="button"`, `Eye` icon
- Selected: `border-info`, hover: `hover:border-border`

**EntityDetailPanel sub-component:**
- Uses `useEntity(runId, entityId)` wrapped in QueryGuard
- "Current State" → `<JsonViewer data={entity.fields} />`
- "History" → vertical timeline with dot + connector line
- Each StateChange: `field → new_value: <TimestampCell> · by actor_id`
- Close button: `type="button"`, `aria-label="Close entity detail"`, X icon

**EntitiesTab main:**
- `useUrlState({ entity: '', entity_type: '' })` for URL state
- `useEntities(runId, { entity_type: ... })` for data
- Header: "ENTITIES (N total)"
- Type filter: select dropdown with `aria-label="Filter by entity type"`
- Entity cards in responsive grid
- Detail panel outside QueryGuard (fetches independently)

**ENTITY_TYPE_OPTIONS Record:**
```tsx
const ENTITY_TYPE_OPTIONS: Record<string, string> = {
  '': 'All types',
  ticket: 'Tickets', customer: 'Customers',
  charge: 'Charges', message: 'Messages',
};
```

---

## Step 3: Events Tab (~250 lines)

**File:** MODIFY `src/pages/run-report/tabs/events-tab.tsx`

This is the most complex. It has 4 sub-components:

### A. EventFilters — filter bar

4 `<select>` dropdowns + 1 search `<input>`:
- Each select has `aria-label` (e.g., "Filter by actor", "Filter by outcome")
- Options are data-driven Records (OUTCOME_OPTIONS, EVENT_TYPE_OPTIONS with all 14 types, ACTOR_OPTIONS, SERVICE_OPTIONS)
- Search input with `Search` icon, `aria-label="Search events"`

### B. EventTableView — TanStack Table

**Column definitions (module-level, 5 columns):**
```tsx
const columns: ColumnDef<WorldEvent>[] = [
  {
    accessorFn: (row) => row.timestamp.tick,
    id: 'tick',
    header: 'Tick',
    cell: ({ getValue }) => <span className="font-mono text-xs text-text-muted">{formatTick(getValue<number>())}</span>,
    size: 80,
  },
  {
    accessorFn: (row) => row.timestamp.wall_time,
    id: 'time',
    header: 'Time',
    cell: ({ getValue }) => <TimestampCell iso={getValue<string>()} />,
    size: 120,
  },
  {
    accessorKey: 'actor_id',
    header: 'Actor',
    cell: ({ row }) => <ActorBadge actorId={row.original.actor_id} role={row.original.actor_role} />,
    size: 160,
  },
  {
    accessorKey: 'action',
    header: 'Action',
    cell: ({ getValue }) => <span className="truncate text-sm text-text-secondary">{getValue<string>()}</span>,
  },
  {
    accessorKey: 'outcome',
    header: 'Outcome',
    cell: ({ getValue }) => (
      <div className="flex items-center gap-1.5">
        <OutcomeIcon outcome={getValue<Outcome>()} size={14} />
        <span className="text-xs uppercase">{getValue<string>()}</span>
      </div>
    ),
    size: 120,
  },
];
```

**Table setup:**
```tsx
const table = useReactTable({
  data: events, columns,
  state: { sorting },
  onSortingChange: setSorting,
  getCoreRowModel: getCoreRowModel(),
  getSortedRowModel: getSortedRowModel(),
  getPaginationRowModel: getPaginationRowModel(),
  initialState: { pagination: { pageSize: 10 } },
});
```

**Row rendering:**
- `onClick={() => onSelectEvent(row.original.event_id)}`
- Selected row: `bg-bg-elevated`, others: `hover:bg-bg-hover`
- Sort indicators: ` ↑` / ` ↓` in column headers

**Pagination:** "Page X of Y" + Previous/Next buttons with `ChevronLeft`/`ChevronRight` icons, `type="button"`, `aria-label`, `disabled` states.

### C. EventDetail — detail panel

**Spec requirements covered:**
1. Header: event ID + close button (`X`, `type="button"`, `aria-label="Close event detail"`)
2. Summary: `actor_id → action → OUTCOME` (uppercase)
3. Input/Output: `<JsonViewer data={event.input_data} />` + `<JsonViewer data={event.output_data} />` in `grid-cols-1 md:grid-cols-2`
4. **Budget impact**: `budget_delta` and `budget_remaining` displayed as "Budget: -{delta} → {remaining} remaining"
5. Policy (conditional on `policy_hit != null`): policy_name, condition, `<EnforcementBadge>`, resolution
6. **Entity IDs** (from `event.entity_ids`): rendered as `<EntityLink runId={runId} entityId={id} />` — clicking navigates to entities tab (spec key interaction line 1068)
7. Causal chain: `<CausalChain>` for parents and children — but items must be **clickable links** that update `?event=` param
8. **Fidelity**: `<FidelityIndicator tier={event.fidelity_tier} />`
9. "[View causal chain →]" label text

**CRITICAL: Making causal chain items clickable:**

The existing `CausalChain` component renders event IDs with copy-on-click. For the Events tab, we need causal items to be **navigation links** (update `?event=` param). Two approaches:
- A: Pass an `onClickEvent` callback to CausalChain — but CausalChain's interface is `{ eventIds, label }` with no click handler
- B: Don't use `CausalChain` in EventDetail — instead render a custom inline list with clickable buttons

**Decision:** Use approach B — render custom causal links in EventDetail that call `onSelectEvent(eventId)`. Keep the existing `CausalChain` component unchanged (it's used elsewhere for copy behavior). This avoids modifying a shared component for page-specific behavior.

```tsx
// Inside EventDetail, for causal links:
function CausalLink({ eventId, onSelect }: { eventId: string; onSelect: (id: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onSelect(eventId)}
      className="font-mono text-xs text-info hover:underline underline-offset-2"
      title={eventId}
    >
      {truncateId(eventId, 12)}
    </button>
  );
}
```

### D. EventsTab main component

```tsx
export function EventsTab({ runId }: EventsTabProps) {
  const [filters, setFilters] = useUrlFilters();
  const [detailState, setDetailState] = useUrlState({ event: '' });
  const [sorting, setSorting] = useState<SortingState>([]);

  const apiParams = useMemo((): EventFilterParams => {
    const p: EventFilterParams = { limit: PAGE_SIZE_EVENTS };
    if (filters.actor_id) p.actor_id = filters.actor_id;
    if (filters.service_id) p.service_id = filters.service_id;
    if (filters.event_type) p.event_type = filters.event_type;
    if (filters.outcome) p.outcome = filters.outcome;
    return p;
  }, [filters]);

  const eventsQuery = useRunEvents(runId, apiParams);
  const selectEvent = useCallback((id: string) => setDetailState({ event: id }), [setDetailState]);
  const clearSelection = useCallback(() => setDetailState({ event: '' }), [setDetailState]);

  return (
    <div>
      <QueryGuard query={eventsQuery} loadingFallback={<SectionLoading />}>
        {(data) => (
          <>
            <h2 className="mb-3 text-lg font-semibold">
              EVENTS <span className="font-normal text-text-muted">({data.total} total)</span>
            </h2>
            <EventFilters filters={filters} onFilterChange={setFilters} />
            {data.items.length === 0
              ? <EmptyState title="No events match your filters" />
              : <EventTableView events={data.items} sorting={sorting}
                  onSortingChange={setSorting} selectedEventId={detailState.event}
                  onSelectEvent={selectEvent} />
            }
          </>
        )}
      </QueryGuard>
      {detailState.event && (
        <EventDetail runId={runId} eventId={detailState.event}
          onClose={clearSelection} onSelectEvent={selectEvent} />
      )}
    </div>
  );
}
```

Note: `onSelectEvent` is passed to both EventTableView (row clicks) and EventDetail (causal link clicks).

---

## Step 4: Enrich Mock Data

**File:** MODIFY `tests/mocks/data/entities.ts`
- Add `state_history` to default entity:
```tsx
state_history: [
  { event_id: 'evt-001', timestamp: '2026-02-22T09:00:00Z', actor_id: 'system', field: 'status', old_value: null, new_value: 'open' },
  { event_id: 'evt-002', timestamp: '2026-03-01T09:03:00Z', actor_id: 'agent-alpha', field: 'status', old_value: 'open', new_value: 'in_progress' },
  { event_id: 'evt-003', timestamp: '2026-03-01T09:15:02Z', actor_id: 'agent-alpha', field: 'status', old_value: 'in_progress', new_value: 'resolved' },
],
```

**File:** MODIFY `tests/mocks/handlers.ts`
- Single-entity handler: return entity WITH state_history
- Single-event handler: add policy_hit + causal data to the returned event

---

## Step 5: Tests (~18 new cases)

**File:** MODIFY `tests/pages/run-report.test.tsx`

### Events tab (7 tests):
1. renders events header with total count ("EVENTS", "10 total")
2. renders table column headers (Tick, Time, Actor, Action, Outcome)
3. renders event rows (check mock action text)
4. renders 4 filter dropdowns (aria-labels: "Filter by actor/service/outcome/type")
5. renders search input (aria-label: "Search events")
6. shows event detail panel when row clicked
7. closes event detail when close clicked (aria-label: "Close event detail")

### Entities tab (5 tests):
8. renders entities header with total count ("ENTITIES", "1 total")
9. renders entity card with ID and type ("TK-2847", "ticket")
10. renders entity type filter (aria-label: "Filter by entity type")
11. shows entity detail when View clicked ("Entity: TK-2847")
12. closes entity detail when close clicked (aria-label: "Close entity detail")

### Gaps tab (5 tests):
13. renders gaps header with count ("CAPABILITY GAPS", "1 detected")
14. renders gap table column headers (Event, Agent, Gap, Response)
15. renders gap row data ("crm_lookup_customer")
16. renders distribution summary ("Adapted:")
17. shows empty state when no gaps (override handler)

---

## Step 6: Update Docs

- `IMPLEMENTATION_STATUS.md`: F4=done, F4b session log, Run Report → ✅ done
- `internal_docs/plans/F4b-report-data-tabs.md`: save plan

---

## File Manifest

**Modify — Source (4):**
- `src/pages/run-report/index.tsx` — 3-line fix
- `src/pages/run-report/tabs/gaps-tab.tsx` — ~130 lines
- `src/pages/run-report/tabs/entities-tab.tsx` — ~180 lines
- `src/pages/run-report/tabs/events-tab.tsx` — ~250 lines

**Modify — Tests/Mocks (3):**
- `tests/mocks/data/entities.ts` — add state_history
- `tests/mocks/handlers.ts` — enrich single-entity/event responses
- `tests/pages/run-report.test.tsx` — add ~18 test cases

**Modify — Docs (1):**
- `IMPLEMENTATION_STATUS.md`

**Total: 8 files.**

---

## Verification

1. `npm run typecheck` — 0 errors
2. `npm run lint` — 0 errors
3. `npm run test` — ~233 tests pass, ~4 remaining todos (F5/F6)
4. `npm run build` — succeeds
5. Visual verification of all 3 tabs
