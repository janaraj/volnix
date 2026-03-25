# Backend Integration — Align Frontend to Actual API Responses

## Context

Backend APIs are live at localhost:8200. Response shapes differ from frontend types. Fix types and every access site directly — no adapter/transform layer. Missing fields become optional with graceful fallbacks.

---

## Layer 1: Types (`src/types/`)

### 1A. `src/types/api.ts` — Replace PaginatedResponse with endpoint-specific types

**DELETE** lines 5-11 (`PaginatedResponse<T>`). **ADD**:

```ts
export interface RunsListResponse {
  runs: Run[];
  total: number;
}

export interface EventsListResponse {
  events: WorldEvent[];
  total: number;
}

export interface EntitiesListResponse {
  entities: Entity[];
  total: number;
}

export interface GapsResponse {
  run_id: string;
  gaps: CapabilityGap[];
  summary: Record<string, unknown>;
}

export interface ScorecardResponse {
  run_id: string;
  per_actor: Record<string, Record<string, number>>;
  collective: Record<string, number>;
}

export interface CompareResponse {
  run_ids: string[];
  labels: Record<string, string>;
  scores: {
    metrics: Record<string, { values: Record<string, number>; deltas: Record<string, number> }>;
  };
  events: {
    totals: Record<string, number>;
    by_type: Record<string, Record<string, number>>;
  };
  entity_states: Record<string, unknown>;
}
```

Add imports for `Run`, `WorldEvent`, `Entity`, `CapabilityGap` from `@/types/domain`.

### 1B. `src/types/domain.ts` — Fix Run interface (lines 20-41)

**REPLACE** Run interface with:

```ts
export interface ConfigSnapshot {
  seed?: number | null;
  mode?: string;
  behavior?: 'static' | 'reactive' | 'dynamic';
}

export interface WorldDef {
  name: string;
}

export interface Run {
  run_id: string;                    // was: id
  status: RunStatus;
  world_def: WorldDef;               // was: world_name: string
  mode: 'governed' | 'ungoverned';
  reality_preset: string;            // relaxed from union — backend may return other values
  fidelity_mode: string;             // was: fidelity
  tag: string;                       // was: tags: string[]
  config_snapshot: ConfigSnapshot;    // was: seed, behavior at top level
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  // Backend will add these — optional until then:
  description?: string;
  current_tick?: number;
  actor_count?: number;
  event_count?: number;
  governance_score?: number | null;
  services?: ServiceSummary[];
  conditions?: WorldConditions;
  error?: string | null;
}
```

**REPLACE** WorldEvent interface (lines 130-152) — make all except `event_type` and `actor_id` optional:

```ts
export interface WorldEvent {
  event_type: EventType | string;    // relaxed — backend sends "world.email_send" etc.
  actor_id: string;
  // Backend will add these — optional until then:
  event_id?: string;
  timestamp?: EventTimestamp;
  caused_by?: string | null;
  actor_role?: string;
  service_id?: string | null;
  action?: string;
  outcome?: Outcome;
  entity_ids?: string[];
  input_data?: Record<string, unknown>;
  output_data?: Record<string, unknown>;
  policy_hit?: PolicyHit | null;
  budget_delta?: number;
  budget_remaining?: number;
  causal_parent_ids?: string[];
  causal_child_ids?: string[];
  fidelity_tier?: 1 | 2;
  fidelity?: FidelityMetadata | null;
  run_id?: string;
  metadata?: Record<string, unknown>;
}
```

**REPLACE** Entity interface (lines 165-173) — rename `entity_id` → `id`, make rest optional:

```ts
export interface Entity {
  id: string;                        // was: entity_id
  entity_type: string;
  service_id?: string;
  fields?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
  state_history?: StateChange[];
}
```

**REMOVE** `GovernanceScorecard`, `RunComparison`, `ComparisonMetric`, `DivergencePoint` types (lines 220-274). These are replaced by `ScorecardResponse` and `CompareResponse` in api.ts.

**KEEP** `Score`, `FidelityBasis`, `PolicyHit`, `CapabilityGap`, `EntityUpdate`, `AgentSummary` as-is.

### 1C. `src/types/ws.ts` — Fix WsRunCompleteMessage

The `data` field is typed as `Run`. After Run rename, `message.data.run_id` (was `.id`).

---

## Layer 2: Services (`src/services/api-client.ts`)

**Change imports** (line 1-8):
```ts
import type { Run, WorldEvent, Entity, AgentSummary, CapabilityGap } from '@/types/domain';
import type {
  RunsListResponse, EventsListResponse, EntitiesListResponse,
  GapsResponse, ScorecardResponse, CompareResponse,
  RunListParams, EventFilterParams, EntityFilterParams,
} from '@/types/api';
import { ApiError } from '@/types/api';
```

**Change return types**:
- Line 52: `getRuns()` → `Promise<RunsListResponse>`
- Line 61: `getRunEvents()` → `Promise<EventsListResponse>`
- Line 70: `getScorecard()` → `Promise<ScorecardResponse>`
- Line 75: `getEntities()` → `Promise<EntitiesListResponse>`
- Line 84: `getCapabilityGaps()` → `Promise<GapsResponse>`
- Line 94: `getComparison()` → `Promise<CompareResponse>`

---

## Layer 3: Hooks (`src/hooks/`)

### 3A. `src/hooks/queries/use-runs.ts` — No code change needed
The hook calls `api.getRuns()` which now returns `RunsListResponse`. TanStack Query infers the type.

### 3B. `src/hooks/queries/use-events.ts` — No code change needed
Same pattern — inferred from api-client return type.

### 3C. `src/hooks/queries/use-scorecard.ts` — No code change needed

### 3D. `src/hooks/queries/use-gaps.ts` — No code change needed

### 3E. `src/hooks/queries/use-compare.ts` — No code change needed

### 3F. `src/hooks/queries/use-entities.ts` — No code change needed

### 3G. `src/hooks/use-live-events.ts` — Fix wrapper keys + field names

**Line 7**: Change `import type { PaginatedResponse } from '@/types/api'` to `import type { EventsListResponse, EntitiesListResponse } from '@/types/api'`

**Line 35**: Change `PaginatedResponse<WorldEvent>` to `EventsListResponse`
**Line 39**: Change `old.items.some((e) => e.event_id` to `old.events.some((e) => e.event_id`
**Line 40**: Change `{ ...old, items: [...old.items, newEvent]` to `{ ...old, events: [...old.events, newEvent]`

**Line 97**: Change `PaginatedResponse<Entity>` to `EntitiesListResponse`
**Line 103**: Change `old.items.map` to `old.entities.map`
**Line 104**: Change `e.entity_id` to `e.id`

**Line 116**: Change `message.data.id` to `message.data.run_id`

---

## Layer 4: Pages — Run Field Renames

### 4A. `src/pages/run-list/run-row.tsx` — BADGE_KEYS refactor + field renames

**Lines 24-30**: Replace BADGE_KEYS with accessor-based BADGE_ITEMS:
```ts
const BADGE_ITEMS: Array<{ label: string; value: (r: Run) => string | number | null | undefined }> = [
  { label: 'Preset', value: (r) => r.reality_preset },
  { label: 'Behavior', value: (r) => r.config_snapshot?.behavior },
  { label: 'Fidelity', value: (r) => r.fidelity_mode },
  { label: 'Mode', value: (r) => r.mode },
  { label: 'Seed', value: (r) => r.config_snapshot?.seed },
];
```

**Lines 32-49**: Replace BadgeRow to use accessor functions:
```ts
function BadgeRow({ run }: { run: Run }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {BADGE_ITEMS.map(({ label, value }) => {
        const v = value(run);
        if (v === null || v === undefined) return null;
        return (
          <span key={label} className="rounded bg-bg-elevated px-1.5 py-0.5 text-[11px] text-text-secondary">
            {label}: {String(v)}
          </span>
        );
      })}
    </div>
  );
}
```

**Line 17**: `onToggleSelect: (id: string)` — no change (still takes string)
**Line 65**: `run.actor_count` → `run.actor_count ?? 0`
**Line 66**: `run.event_count` → `run.event_count ?? 0`
**Line 67**: `run.services.length` → `(run.services ?? []).length`
**Line 81**: `run.tags.length > 0 ? run.tags[0] : truncateId(run.id)` → `run.tag || truncateId(run.run_id)`
**Line 85**: `liveConsolePath(run.id)` → `liveConsolePath(run.run_id)`
**Line 87**: `runReportPath(run.id)` → `runReportPath(run.run_id)`
**Line 104**: `onToggleSelect(run.id)` → `onToggleSelect(run.run_id)`
**Line 115**: `liveConsolePath(run.id)` → `liveConsolePath(run.run_id)`
**Line 135**: `run.world_name` → `run.world_def.name`

### 4B. `src/pages/run-list/run-table.tsx`

**Line 24**: `key={run.id}` → `key={run.run_id}`
**Line 26**: `selectedRunIds.includes(run.id)` → `selectedRunIds.includes(run.run_id)`

### 4C. `src/pages/run-list/index.tsx`

**Line 7**: Remove `import type { PaginatedResponse } from '@/types/api'`
**Line 14**: Remove `import type { PaginatedResponse } from '@/types/api'`
**Line 28**: Change `function hasRunningRun(data: PaginatedResponse<Run> | undefined)` to `function hasRunningRun(data: RunsListResponse | undefined)` — import `RunsListResponse` from `@/types/api`
**Line 29**: `data?.items.some` → `data?.runs.some`
**Line 56**: `PaginatedResponse<Run>` → `RunsListResponse`
**Line 73**: `data.items.length` → `data.runs.length`
**Line 89**: `data.items` → `data.runs`

### 4D. `src/pages/run-report/report-header.tsx`

**Line 12**: Replace `BADGE_KEYS` with accessor-based BADGE_ITEMS (same pattern as run-row):
```ts
const BADGE_ITEMS: Array<{ label: string; value: (r: Run) => string | number | null | undefined }> = [
  { label: 'Preset', value: (r) => r.reality_preset },
  { label: 'Behavior', value: (r) => r.config_snapshot?.behavior },
  { label: 'Fidelity', value: (r) => r.fidelity_mode },
  { label: 'Mode', value: (r) => r.mode },
];
```

**Line 14-18**: Remove `getBadgeValue` function.

**Line 21**: `run.tags.length > 0 ? run.tags[0] : run.id` → `run.tag || run.run_id`
**Line 38**: `run.world_name` → `run.world_def.name`
**Lines 42-49**: Replace badge rendering:
```ts
{BADGE_ITEMS.map(({ label, value }) => {
  const v = value(run);
  if (v == null) return null;
  return (
    <span key={label} className="rounded-full bg-bg-elevated px-2 py-0.5 text-xs text-text-secondary">
      {String(v)}
    </span>
  );
})}
```
**Lines 50-53**: `run.seed` → `run.config_snapshot?.seed`

### 4E. `src/pages/run-report/index.tsx`

**Line 39**: `run.services` → `run.services ?? []`
**Line 47**: `run.conditions` → guard:
```ts
case 'conditions':
  return run.conditions
    ? <ConditionsTab conditions={run.conditions} realityPreset={run.reality_preset} behavior={run.config_snapshot?.behavior ?? 'static'} />
    : <EmptyState title="Conditions data not available" description="Backend has not provided conditions for this run." />;
```
Also add `import { EmptyState } from '@/components/feedback/empty-state'`.

### 4F. `src/pages/live-console/run-header-bar.tsx`

**Line 23**: `run.tags.length > 0 ? run.tags[0] : run.id` → `run.tag || run.run_id`
**Line 39**: `run.world_name` → `run.world_def.name`
**Line 51**: `run.current_tick` → `run.current_tick ?? 0`
**Line 54**: `run.actor_count` → `run.actor_count ?? 0`

### 4G. `src/pages/live-console/index.tsx`

**Line 29** (outer `events`): `eventsQuery.data?.items` → `eventsQuery.data?.events`
**Line 45** (inner): already fixed via outer declaration — remove duplicate if exists.

### 4H. `src/pages/live-console/context-view.tsx`

**Line 64**: `run.world_name` → `run.world_def.name`
**Line 68**: `run.current_tick` → `run.current_tick ?? 0`
**Line 69**: `run.actor_count ?? 0` (add fallback)
**Line 71**: `run.services.length` → `(run.services ?? []).length`
**Line 74**: `run.services.length > 0` → `(run.services ?? []).length > 0`
**Line 78-80**: `run.services.map` → `(run.services ?? []).map`
**Line 87-93**: `run.reality_preset`, `run.behavior` → `run.reality_preset`, `run.config_snapshot?.behavior ?? 'static'`
**Line 90**: `run.behavior` → `run.config_snapshot?.behavior ?? 'static'`
**Line 93**: `run.mode` — no change

### 4I. `src/pages/live-console/inspector.tsx`

**Line 74**: `run.mode` — no change
**Line 77**: `run.reality_preset` — no change
**Line 80**: `run.behavior` → `run.config_snapshot?.behavior ?? 'static'`
**Line 87**: `run.actor_count` → `run.actor_count ?? 0`
**Line 90**: `run.services.length` → `(run.services ?? []).length`
**Line 95**: `run.services.length > 0` → `(run.services ?? []).length > 0`
**Line 99**: `run.services.map` → `(run.services ?? []).map`

### 4J. `src/pages/run-report/tabs/overview-tab.tsx`

**Line 48**: `run.governance_score != null` — no change (already optional)
**Line 56**: `run.event_count` → `run.event_count ?? 0`
**Line 57**: `run.actor_count` → `run.actor_count ?? 0`
**Line 58**: `run.services.length` → `(run.services ?? []).length`

---

## Layer 5: Pages — Scorecard Restructure

### 5A. `src/pages/run-report/tabs/scorecard-tab.tsx`

**Complete rewrite of ScorecardGrid** to work with `ScorecardResponse`:

```ts
import type { ScorecardResponse } from '@/types/api';

// Replace props
interface ScorecardGridProps {
  data: ScorecardResponse;
}

function ScorecardGrid({ data }: ScorecardGridProps) {
  const actorIds = Object.keys(data.per_actor);
  const dimensions = Object.keys(data.collective).filter((k) => k !== 'overall_score');

  if (actorIds.length === 0) {
    return <EmptyState title="No scorecard data available" />;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-bg-elevated">
            <th className="px-3 py-2 text-left text-xs font-medium uppercase text-text-muted">Dimension</th>
            {actorIds.map((id) => (
              <th key={id} className="px-3 py-2 text-center text-xs font-medium uppercase text-text-muted">{id}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {dimensions.map((dim) => (
            <tr key={dim} className="border-b border-bg-elevated">
              <td className="px-3 py-2 text-text-secondary">{formatDimensionName(dim)}</td>
              {actorIds.map((actorId) => {
                const value = data.per_actor[actorId]?.[dim];
                return (
                  <td key={actorId} className="px-3 py-2 text-center">
                    {value != null ? (
                      <span className={cn('inline-block rounded px-2 py-0.5 font-mono text-xs', scoreToColorClass(value / 100))}>
                        {formatScore(value / 100)}
                      </span>
                    ) : (
                      <span className="text-text-muted">--</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
          {data.collective.overall_score != null && (
            <tr className="border-t-2 border-bg-elevated font-semibold">
              <td className="px-3 py-2 text-text-primary">Overall</td>
              {actorIds.map((actorId) => (
                <td key={actorId} className="px-3 py-2 text-center">
                  <span className={cn('inline-block rounded px-2 py-0.5 font-mono text-xs', scoreToColorClass(data.collective.overall_score / 100))}>
                    {formatScore(data.collective.overall_score / 100)}
                  </span>
                </td>
              ))}
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
```

**ScorecardTab**: Change `QueryGuard` callback from `(scorecards)` to `(data: ScorecardResponse)`. Remove Dialog (no violations data from backend yet). Remove FidelityBasisCard (no fidelity_basis from backend yet) or guard.

**Remove** `findScore`, `CellSelection`, Dialog-related code. Simplify.

### 5B. `src/pages/run-report/tabs/overview-tab.tsx` — Guard scorecard access

Overview tab fetches scorecard for agent summaries. Update to handle `ScorecardResponse` shape. Iterate `Object.entries(data.per_actor)` instead of `scorecards.map()`.

---

## Layer 6: Pages — Compare Restructure

### 6A. `src/pages/compare/index.tsx`

**Line 11**: Change `import type { RunComparison }` to `import type { CompareResponse } from '@/types/api'`

**Lines 19-26**: Replace `data.runs` with `data.labels` and `data.run_ids`:
```ts
{(data: CompareResponse) => {
  const tagLine = data.run_ids.map((id) => data.labels[id] ?? id).join(' vs ');
  // No world line available from compare endpoint — remove or fetch separately
```

**Line 51**: Replace `MetricDiffTable` props:
```ts
<MetricDiffTable metrics={data.scores.metrics} labels={data.labels} runIds={data.run_ids} />
```

**Line 52**: Remove `DivergenceTimeline` (backend doesn't return divergence_points yet) — or render conditionally.

**Line 53**: Replace `ScoreComparisonBars` props similarly.

### 6B. `src/pages/compare/metric-diff-table.tsx`

**Replace entire props and rendering**:
```ts
interface MetricDiffTableProps {
  metrics: Record<string, { values: Record<string, number>; deltas: Record<string, number> }>;
  labels: Record<string, string>;
  runIds: string[];
}

export function MetricDiffTable({ metrics, labels, runIds }: MetricDiffTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-bg-elevated text-left text-text-secondary">
            <th className="py-2 pr-4 font-medium">Metric</th>
            {runIds.map((id) => (
              <th key={id} className="py-2 pr-4 font-medium">{labels[id] ?? id}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Object.entries(metrics).map(([name, metric]) => {
            const bestId = findBestValue(metric.values);
            return (
              <tr key={name} className="border-b border-bg-elevated">
                <td className="py-2 pr-4 text-text-secondary">{formatDimensionName(name)}</td>
                {runIds.map((id) => {
                  const value = metric.values[id];
                  const isBest = bestId === id;
                  return (
                    <td key={id} className={cn('py-2 pr-4 font-mono', isBest && 'text-success font-medium')}>
                      {value != null ? String(value) : '—'}
                      {isBest && <span className="ml-1 text-xs">✓best</span>}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
```

### 6C. `src/pages/compare/entity-diff.tsx` (ScoreComparisonBars)

**Replace props**:
```ts
interface ScoreComparisonBarsProps {
  metrics: Record<string, { values: Record<string, number> }>;
  labels: Record<string, string>;
  runIds: string[];
}
```

Iterate `Object.entries(metrics)` and `runIds.map()` using `labels[id]` for display.

### 6D. `src/pages/compare/divergence-timeline.tsx`

**Guard**: Since backend doesn't return divergence points, the compare page won't pass them. Remove from compare page import or make props optional with empty default.

---

## Layer 7: Pages — Gaps + Entities Wrapper Fix

### 7A. `src/pages/run-report/tabs/gaps-tab.tsx`

**Line 71**: QueryGuard callback changes from `(gaps)` to `(data: GapsResponse)`.
**All inner refs**: `gaps.length` → `data.gaps.length`, `gaps.map` → `data.gaps.map`, etc.

### 7B. `src/pages/run-report/tabs/entities-tab.tsx`

**Lines 191-217**: Change `data.items` → `data.entities`, `data.total` stays.
**Line 140,219,220,221**: Change `entity.entity_id` → `entity.id`.
**Line 168**: Guard `entity.updated_at` → `entity.updated_at ?? ''`
**Line 126**: Guard `entity.fields` → `entity.fields ?? {}`

### 7C. `src/pages/run-report/tabs/events-tab.tsx`

**Lines 533,537,541**: Change `data.items` → `data.events`, `data.total` stays.

**Guard all optional WorldEvent fields in EventTableView and EventDetail**:
- `row.timestamp?.tick ?? 0`, `row.timestamp?.wall_time ?? ''`
- `event.action ?? event.event_type`
- `event.outcome ?? 'success'`
- `event.event_id ?? ''`
- `event.entity_ids ?? []`
- `event.causal_parent_ids ?? []`, `event.causal_child_ids ?? []`
- `event.budget_delta ?? 0`, `event.budget_remaining ?? 0`
- `event.input_data ?? {}`, `event.output_data ?? {}`

### 7D. `src/pages/live-console/event-feed.tsx`

**Line 55**: `e.actor_id` — no change (always present)
**Line 60**: `e.service_id` → `e.service_id ?? ''` (now optional)
**Line 66-69**: Guard optional fields in filter logic

### 7E. `src/pages/live-console/event-feed-item.tsx`

**Line 21**: `event.event_id` → `event.event_id ?? ''`
**Line 31**: `event.timestamp.tick` → `event.timestamp?.tick ?? 0`
**Line 56**: `event.action` → `event.action ?? event.event_type`
**Line 61-62**: Guard `event.policy_hit?.enforcement`, `event.policy_hit?.policy_name`

---

## Layer 8: Test Mocks

### 8A. `tests/mocks/data/runs.ts`

**Replace** `createMockRun`:
```ts
export function createMockRun(overrides?: Partial<Run>): Run {
  return {
    run_id: 'run-test-001',
    status: 'completed',
    world_def: { name: 'Acme Support Organization' },
    mode: 'governed',
    reality_preset: 'messy',
    fidelity_mode: 'auto',
    tag: 'exp-1-baseline',
    config_snapshot: { seed: 42, mode: 'governed', behavior: 'dynamic' },
    created_at: '2026-03-01T09:00:00Z',
    started_at: '2026-03-01T09:00:05Z',
    completed_at: '2026-03-01T09:15:02Z',
    current_tick: 234,
    actor_count: 4,
    event_count: 847,
    governance_score: 0.87,
    services: [
      { service_id: 'email', service_name: 'Email', category: 'communication', fidelity_tier: 1, fidelity_source: 'verified_pack', entity_count: 50 },
      { service_id: 'chat', service_name: 'Chat', category: 'communication', fidelity_tier: 1, fidelity_source: 'verified_pack', entity_count: 30 },
      { service_id: 'payments', service_name: 'Stripe', category: 'money', fidelity_tier: 2, fidelity_source: 'curated_profile', entity_count: 200 },
    ],
    conditions: { /* same as before */ },
    ...overrides,
  };
}
```

Update `createMockRunList` similarly — change `id` → `run_id`, `tags` → `tag`, etc.

### 8B. `tests/mocks/data/entities.ts`

Change `entity_id` → `id` in mock entity.

### 8C. `tests/mocks/data/scorecard.ts`

Replace mock to return `ScorecardResponse` shape:
```ts
export function createMockScorecardResponse(): ScorecardResponse {
  return {
    run_id: 'run-test-001',
    per_actor: {
      'agent-alpha': { policy_compliance: 90, governance: 85 },
      'agent-beta': { policy_compliance: 81, governance: 78 },
    },
    collective: { overall_score: 85, policy_compliance: 85, governance: 81 },
  };
}
```

### 8D. `tests/mocks/data/comparison.ts`

Replace mock to return `CompareResponse` shape:
```ts
export function createMockCompareResponse(): CompareResponse {
  return {
    run_ids: ['run-1', 'run-2'],
    labels: { 'run-1': 'exp-1-baseline', 'run-2': 'exp-2-variant' },
    scores: {
      metrics: {
        overall_score: { values: { 'run-1': 78, 'run-2': 94 }, deltas: { 'run-1→run-2': 16 } },
        policy_compliance: { values: { 'run-1': 70, 'run-2': 95 }, deltas: { 'run-1→run-2': 25 } },
      },
    },
    events: { totals: { 'run-1': 4, 'run-2': 3 }, by_type: {} },
    entity_states: {},
  };
}
```

### 8E. `tests/mocks/handlers.ts`

**Line 11-17**: Change `items` → `runs`, remove `limit`, `offset`, `has_more`
**Line 21**: Change `createMockRun({ id: ...})` → `createMockRun({ run_id: ...})`
**Line 25-31**: Change `items` → `events`, remove pagination fields
**Line 38-43**: Change to return `createMockScorecardResponse()`
**Line 47-53**: Change `items` → `entities`, remove pagination fields
**Line 60-62**: Change to return `{ run_id: '...', gaps: [...], summary: {} }`
**Line 76-78**: Change to return `createMockCompareResponse()`

### 8F. Update test assertions

Tests that check for `run.id` in text need updating to match new `run.run_id` display. Tests that check `data.items` patterns need updating. Walk through each test file after type changes — TypeScript errors will guide.

---

## Execution Order

1. **Types** (1A, 1B, 1C) — breaks everything intentionally
2. **API client** (Layer 2) — fix return types
3. **Hooks** (Layer 3) — fix use-live-events wrapper keys
4. **Run field renames** (Layer 4: 4A-4J) — bulk rename across all pages
5. **Scorecard restructure** (Layer 5)
6. **Compare restructure** (Layer 6)
7. **Gaps + Entities wrapper fix** (Layer 7)
8. **Test mocks** (Layer 8) — fix all mock data + handlers
9. `npm run typecheck` → fix remaining errors
10. `npm run test` → fix failing assertions
11. `npm run build` → verify production build

---

## Verification

```bash
npm run typecheck   # 0 errors
npm run test        # all pass
npm run build       # succeeds
# Then start Vite dev server and verify against live backend:
npm run dev         # open http://localhost:3000, verify run list renders
```

---

## Backend Team Handoff — Fields to Add

**On each Run object:** `current_tick`, `actor_count`, `event_count`, `governance_score`, `services[]`, `conditions`, `error`, `description`

**On each Event object:** `event_id`, `timestamp { world_time, wall_time, tick }`, `action`, `outcome`, `actor_role`, `service_id`, `entity_ids[]`, `input_data`, `output_data`, `policy_hit`, `budget_delta`, `budget_remaining`, `causal_parent_ids[]`, `causal_child_ids[]`, `fidelity_tier`, `run_id`

**On each Entity object:** `service_id`, `fields`, `created_at`, `updated_at`, `state_history[]`

**On Scorecard:** Add per-actor `scores[]` array with `name`, `value`, `weight`, `formula`, `violations`. Add `fidelity_basis`.

**On Compare:** Add `divergence_points[]`. Optionally include full `Run` objects.

**Actors endpoint:** Needs to return actor data (currently returns 404).
