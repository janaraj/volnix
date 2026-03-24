# F3: Run List Page — Implementation Plan

## Context

F0-F2 complete (182 tests pass). F3 is the first real page — it proves the full data flow: URL filters → API query → QueryGuard → rendered cards → compare selection → navigation. This pattern is reused by all subsequent pages.

**Spec source:** `internal_docs/terrarium-frontend-spec.md` lines 307-357
**Backend APIs:** All paths use `/api/v1/` prefix (alignment decision made this session)

---

## Key Decisions

1. **Switch ApiClient to `/api/v1/` prefix** — Backend convention. Update all 11 endpoint paths + all 10 MSW handlers.
2. **Add `governance_score?: number | null` to Run type** — Backend populates summary score in list response. Card shows ScoreBar when present, "Score: --" when null.
3. **Card layout, not data table** — Spec shows multi-line cards, not a grid. TanStack Table reserved for F4 Events tab.
4. **Conditional polling** — `refetchInterval` enabled (10s) when any run has `status === 'running'`, disabled otherwise.
5. **Run-level URL filters** — status, preset, tag via `useUrlState` (separate from event-level `useUrlFilters`).

---

## Steps

### Step 1: Update ApiClient to /api/v1/ prefix + Add governance_score to Run

**Files:**
- MODIFY: `src/services/api-client.ts` — change all 11 endpoint paths from `/api/` to `/api/v1/`
- MODIFY: `src/types/domain.ts` — add `governance_score?: number | null` to Run interface
- MODIFY: `tests/mocks/handlers.ts` — update all 10 MSW handler paths from `/api/` to `/api/v1/`
- MODIFY: `tests/mocks/data/runs.ts` — add `governance_score` to mock data, create varied runs

**ApiClient path changes:**
```
/api/runs           → /api/v1/runs
/api/runs/:id       → /api/v1/runs/:id
/api/runs/:id/events      → /api/v1/runs/:id/events
/api/runs/:id/events/:eid → /api/v1/runs/:id/events/:eid
/api/runs/:id/scorecard   → /api/v1/runs/:id/scorecard
/api/runs/:id/entities    → /api/v1/runs/:id/entities
/api/runs/:id/entities/:eid → /api/v1/runs/:id/entities/:eid
/api/runs/:id/gaps        → /api/v1/runs/:id/gaps
/api/runs/:id/actors/:aid → /api/v1/runs/:id/actors/:aid
/api/compare              → /api/v1/compare
```

**Also update existing report endpoints to use backend's actual paths:**
```
/api/v1/runs/:id/scorecard  → /api/v1/report/scorecard (backend actual)
/api/v1/runs/:id/gaps       → /api/v1/report/gaps (backend actual)
```
Note: Keep the run-scoped paths for now since the backend team will create those. The report endpoints (`/api/v1/report/*`) are global (not run-scoped). We can map later in F4 when we wire the report page.

**Mock data enrichment:**
```typescript
// createMockRunList should produce varied runs:
// Run 1: completed, tags: ['exp-1-baseline'], governance_score: 0.87, reality: 'messy'
// Run 2: running, tags: ['exp-2-hostile'], governance_score: null, reality: 'hostile'
// Run 3: failed, tags: ['exp-3-edge'], governance_score: 0.42, reality: 'ideal'
```

**Done:** TypeScript compiles. All existing tests still pass (MSW paths updated).

### Step 2: Extend useRuns hook to support refetchInterval

**File:** MODIFY `src/hooks/queries/use-runs.ts`

Add optional `queryOptions` parameter for passing `refetchInterval`:

```typescript
import type { UseQueryOptions } from '@tanstack/react-query';

export function useRuns(
  params?: RunListParams,
  queryOptions?: Pick<UseQueryOptions, 'refetchInterval'>,
) {
  const api = useApiClient();
  return useQuery({
    queryKey: queryKeys.runs.list(params),
    queryFn: () => api.getRuns(params),
    staleTime: STALE_TIME_RUNS_LIST,
    ...queryOptions,
  });
}
```

The page will call:
```typescript
useRuns(params, {
  refetchInterval: (query) => {
    const data = query.state.data;
    return data?.items.some(r => r.status === 'running') ? 10_000 : false;
  },
});
```

**Done:** Hook accepts optional refetchInterval. Backward compatible.

### Step 3: Implement RunFilters

**File:** MODIFY `src/pages/run-list/run-filters.tsx`

**Spec:** "Filter bar: status dropdown, reality dropdown, free-text tag search. Filters applied via URL params for shareability."

```tsx
import { useState, useEffect } from 'react';
import { Search } from 'lucide-react';
import { useUrlState } from '@/hooks/use-url-state';
import { DEBOUNCE_MS_SEARCH } from '@/constants/defaults';

// Module-level constant for useUrlState stability
const RUN_FILTER_DEFAULTS = { status: '', preset: '', tag: '' };

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'created', label: 'Created' },
  { value: 'running', label: 'Running' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
  { value: 'stopped', label: 'Stopped' },
];

const PRESET_OPTIONS = [
  { value: '', label: 'All presets' },
  { value: 'ideal', label: 'Ideal' },
  { value: 'messy', label: 'Messy' },
  { value: 'hostile', label: 'Hostile' },
];

export function RunFilters() {
  const [filters, setFilters] = useUrlState(RUN_FILTER_DEFAULTS);
  const [tagInput, setTagInput] = useState(filters.tag);

  // Debounce tag search
  useEffect(() => {
    const timer = setTimeout(() => {
      if (tagInput !== filters.tag) {
        setFilters({ tag: tagInput });
      }
    }, DEBOUNCE_MS_SEARCH);
    return () => clearTimeout(timer);
  }, [tagInput, filters.tag, setFilters]);

  // Sync URL → local input when URL changes externally (browser back)
  useEffect(() => {
    setTagInput(filters.tag);
  }, [filters.tag]);

  const selectClass = 'rounded border border-border bg-bg-surface px-3 py-1.5 text-sm text-text-primary focus:border-ring focus:outline-none';

  return (
    <div className="mb-4 flex flex-wrap items-center gap-3">
      <select
        value={filters.status}
        onChange={(e) => setFilters({ status: e.target.value })}
        className={selectClass}
        aria-label="Filter by status"
      >
        {STATUS_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>

      <select
        value={filters.preset}
        onChange={(e) => setFilters({ preset: e.target.value })}
        className={selectClass}
        aria-label="Filter by reality preset"
      >
        {PRESET_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>

      <div className="relative flex-1 min-w-[200px]">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
        <input
          type="text"
          value={tagInput}
          onChange={(e) => setTagInput(e.target.value)}
          placeholder="Search tags..."
          className="w-full rounded border border-border bg-bg-surface pl-8 pr-3 py-1.5 text-sm text-text-primary placeholder-text-muted focus:border-ring focus:outline-none"
          aria-label="Search by tag"
        />
      </div>
    </div>
  );
}
```

**Data-driven:** Status and preset options are Record arrays, not if/switch. Debounce uses constant from defaults.ts.

**Done:** Filter controls render. URL params update on change. Debounced tag search.

### Step 4: Implement RunCard (run-row.tsx)

**File:** MODIFY `src/pages/run-list/run-row.tsx`

**Spec layout per card:**
```
[ ] ● exp-3-hostile-audit          hostile · dynamic · strict    [View] [↗]
    Support Organization           governed · seed: 42
    Score: 87  ██████████████░░    3 agents · 287 entities
    Completed 2h ago · 847 events · 4m 23s duration
```

```tsx
import { Link } from 'react-router';
import { ExternalLink, Eye, Radio } from 'lucide-react';
import type { Run } from '@/types/domain';
import { RunStatusBadge } from '@/components/domain/run-status-badge';
import { ScoreBar } from '@/components/domain/score-bar';
import { TimestampCell } from '@/components/domain/timestamp-cell';
import { cn } from '@/lib/cn';
import { formatDuration, truncateId } from '@/lib/formatters';
import { runReportPath, liveConsolePath } from '@/constants/routes';

interface RunCardProps {
  run: Run;
  isSelected: boolean;
  onToggleSelect: () => void;
}

export function RunCard({ run, isSelected, onToggleSelect }: RunCardProps) {
  const entityCount = run.services.reduce((sum, s) => sum + s.entity_count, 0);
  const isActive = run.status === 'running' || run.status === 'created';
  const duration = run.started_at && run.completed_at
    ? formatDuration(new Date(run.completed_at).getTime() - new Date(run.started_at).getTime())
    : null;

  return (
    <div className={cn(
      'rounded border bg-bg-surface p-4 transition-colors',
      isSelected ? 'border-accent/50' : 'border-border',
      'hover:border-border/80',
    )}>
      {/* Row 1: Checkbox + Status + Tag + Actions */}
      <div className="flex items-center gap-3">
        <input
          type="checkbox"
          checked={isSelected}
          onChange={onToggleSelect}
          className="h-4 w-4 rounded border-border accent-accent"
          aria-label={`Select ${run.tags[0] || run.id} for comparison`}
        />
        <RunStatusBadge status={run.status} />
        <span className="font-mono text-sm font-medium text-text-primary">
          {run.tags[0] || truncateId(run.id, 16)}
        </span>
        <span className="flex-1" />
        {/* Action buttons */}
        {isActive ? (
          <Link
            to={liveConsolePath(run.id)}
            className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-info hover:bg-bg-hover transition-colors"
          >
            <Radio size={12} />
            Watch Live
          </Link>
        ) : (
          <>
            <Link
              to={runReportPath(run.id)}
              className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors"
            >
              <Eye size={12} />
              View
            </Link>
            <Link
              to={runReportPath(run.id)}
              className="rounded p-1 text-text-muted hover:bg-bg-hover hover:text-text-primary transition-colors"
              title="Open report"
            >
              <ExternalLink size={12} />
            </Link>
          </>
        )}
      </div>

      {/* Row 2: World name */}
      <p className="mt-1 ml-7 text-sm text-text-secondary">{run.world_name}</p>

      {/* Row 3: Badges */}
      <div className="mt-2 ml-7 flex flex-wrap gap-2">
        {[run.reality_preset, run.behavior, run.fidelity, run.mode].map((badge) => (
          <span key={badge} className="rounded-full bg-bg-elevated px-2 py-0.5 text-xs text-text-secondary">
            {badge}
          </span>
        ))}
        {run.seed != null && (
          <span className="rounded-full bg-bg-elevated px-2 py-0.5 font-mono text-xs text-text-muted">
            seed: {run.seed}
          </span>
        )}
      </div>

      {/* Row 4: Score */}
      <div className="mt-2 ml-7">
        {run.governance_score != null ? (
          <ScoreBar value={run.governance_score} label="Score" />
        ) : (
          <span className="text-xs text-text-muted">Score: --</span>
        )}
      </div>

      {/* Row 5: Stats */}
      <div className="mt-2 ml-7 flex flex-wrap items-center gap-3 font-mono text-xs text-text-muted">
        <span>{run.actor_count} actors</span>
        <span className="text-text-muted/40">·</span>
        <span>{run.event_count} events</span>
        <span className="text-text-muted/40">·</span>
        <span>{entityCount} entities</span>
        {duration && (
          <>
            <span className="text-text-muted/40">·</span>
            <span>{duration}</span>
          </>
        )}
        <span className="text-text-muted/40">·</span>
        <TimestampCell iso={run.created_at} />
      </div>
    </div>
  );
}
```

**Reuses:** RunStatusBadge, ScoreBar, TimestampCell, cn, formatDuration, truncateId, route builders.
**Data-driven:** Badges from run fields, no hardcoded values. Score conditional on `governance_score`.

### Step 5: Implement RunTable (card list)

**File:** MODIFY `src/pages/run-list/run-table.tsx`

```tsx
import type { Run } from '@/types/domain';
import { RunCard } from './run-row';
import { useCompareStore } from '@/stores/compare-store';

interface RunTableProps {
  runs: Run[];
}

export function RunTable({ runs }: RunTableProps) {
  const { isSelected, toggleRun } = useCompareStore();

  return (
    <div className="flex flex-col gap-3">
      {runs.map((run) => (
        <RunCard
          key={run.id}
          run={run}
          isSelected={isSelected(run.id)}
          onToggleSelect={() => toggleRun(run.id)}
        />
      ))}
    </div>
  );
}
```

### Step 6: Implement CompareToolbar

**File:** MODIFY `src/pages/run-list/compare-toolbar.tsx`

**Spec:** "Checkbox on each run card. When 2+ selected, 'Compare Selected' button activates."

```tsx
import { useNavigate } from 'react-router';
import { GitCompareArrows, X } from 'lucide-react';
import { useCompareStore } from '@/stores/compare-store';
import { comparePath } from '@/constants/routes';
import { cn } from '@/lib/cn';

export function CompareToolbar() {
  const { selectedRunIds, clearSelection } = useCompareStore();
  const navigate = useNavigate();
  const count = selectedRunIds.length;

  if (count === 0) return null;

  const canCompare = count >= 2;

  return (
    <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2">
      <div className="flex items-center gap-4 rounded-lg border border-border bg-bg-elevated px-6 py-3 shadow-lg">
        <span className="text-sm text-text-secondary">
          {count} run{count !== 1 ? 's' : ''} selected
        </span>

        <button
          type="button"
          onClick={clearSelection}
          className="inline-flex items-center gap-1 text-sm text-text-muted hover:text-text-primary transition-colors"
        >
          <X size={14} />
          Clear
        </button>

        <button
          type="button"
          disabled={!canCompare}
          onClick={() => navigate(comparePath(selectedRunIds))}
          className={cn(
            'inline-flex items-center gap-2 rounded px-4 py-1.5 text-sm font-medium transition-colors',
            canCompare
              ? 'bg-accent text-text-primary hover:bg-accent/80'
              : 'bg-bg-hover text-text-muted cursor-not-allowed',
          )}
        >
          <GitCompareArrows size={14} />
          Compare Selected
        </button>
      </div>
    </div>
  );
}
```

### Step 7: Implement Page Index (orchestrator)

**File:** MODIFY `src/pages/run-list/index.tsx`

```tsx
import { PageHeader } from '@/components/layout/page-header';
import { QueryGuard } from '@/components/feedback/query-guard';
import { EmptyState } from '@/components/feedback/empty-state';
import { useRuns } from '@/hooks/queries/use-runs';
import { useUrlState } from '@/hooks/use-url-state';
import { PAGE_SIZE_RUNS } from '@/constants/defaults';
import { RunFilters } from './run-filters';
import { RunTable } from './run-table';
import { CompareToolbar } from './compare-toolbar';
import type { RunListParams } from '@/types/api';
import type { PaginatedResponse } from '@/types/api';
import type { Run } from '@/types/domain';
import { ListChecks } from 'lucide-react';

// Module-level constant to avoid useUrlState re-render loop
const FILTER_DEFAULTS = { status: '', preset: '', tag: '' };

function NewRunHint() {
  return (
    <span className="rounded border border-border bg-bg-elevated px-3 py-1.5 font-mono text-xs text-text-muted">
      terrarium create ...
    </span>
  );
}

export function RunListPage() {
  const [filters] = useUrlState(FILTER_DEFAULTS);

  const params: RunListParams = {
    ...(filters.status && { status: filters.status }),
    ...(filters.preset && { preset: filters.preset }),
    ...(filters.tag && { tag: filters.tag }),
    limit: PAGE_SIZE_RUNS,
  };

  const runsQuery = useRuns(params, {
    refetchInterval: (query) => {
      const data = query.state.data as PaginatedResponse<Run> | undefined;
      return data?.items.some((r) => r.status === 'running') ? 10_000 : false;
    },
  });

  return (
    <div>
      <PageHeader title="Runs" subtitle="All simulation runs" actions={<NewRunHint />} />
      <RunFilters />
      <QueryGuard query={runsQuery} emptyMessage="No runs found">
        {(data) =>
          data.items.length === 0 ? (
            <EmptyState
              title="No runs match your filters"
              description="Try adjusting your filters or create a new run via CLI"
              icon={ListChecks}
            />
          ) : (
            <RunTable runs={data.items} />
          )
        }
      </QueryGuard>
      <CompareToolbar />
    </div>
  );
}
```

**Key patterns:**
- Filter defaults as module-level constant (prevents useMemo instability)
- Conditional polling via `refetchInterval` function
- QueryGuard for loading/error, manual empty check for filtered-empty-list
- CompareToolbar always rendered (it self-hides when selection is empty)

### Step 8: Implement Tests

**File:** MODIFY `tests/pages/run-list.test.tsx`

Tests need: `MemoryRouter` (URL state), `QueryClientProvider` (queries), MSW server (API), mocked `useApiClient`.

```tsx
import { describe, it, expect, vi, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { server } from '../mocks/server';
import { http, HttpResponse } from 'msw';
import { ApiClient } from '@/services/api-client';
import { RunListPage } from '@/pages/run-list';
import type { ReactNode } from 'react';

const testApi = new ApiClient('');
vi.mock('@/providers/services-provider', () => ({
  useApiClient: () => testApi,
}));

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderPage(route = '/') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>
        <RunListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
```

**Test cases (replacing 2 todos + comprehensive coverage):**

1. `renders page header with title "Runs"` — check `getByText('Runs')`
2. `shows loading state initially` — check for loading spinner
3. `renders run cards after data loads` — waitFor cards to appear
4. `shows empty state when no runs` — override MSW to return empty items
5. `renders status filter dropdown` — check for select with status options
6. `renders preset filter dropdown` — check for select with preset options
7. `renders tag search input` — check for text input
8. `shows RunStatusBadge on each card` — check status text appears
9. `shows compare checkbox on each card` — check for checkboxes
10. `shows compare toolbar when runs selected` — click checkbox, verify toolbar
11. `compare button disabled with < 2 selected` — verify disabled state
12. `compare button enabled with >= 2 selected` — click 2 checkboxes, verify enabled
13. `shows score bar for runs with governance_score` — check score display
14. `shows "Score: --" for runs without governance_score` — check null score
15. `renders View button for completed runs` — check link text
16. `renders Watch Live button for running runs` — check link text

### Step 9: Update docs + save plan

**Files:**
- MODIFY: `terrarium-dashboard/IMPLEMENTATION_STATUS.md` — F3=done, session log
- CREATE: `internal_docs/plans/F3-run-list.md` — copy of this plan
- MODIFY: `terrarium-dashboard/IMPLEMENTATION_STATUS.md` — add Backend API section documenting actual endpoints

---

## Backend API Documentation (add to IMPLEMENTATION_STATUS.md)

```
## Backend API Endpoints (available)

### Core APIs (agent-facing)
GET  /api/v1/health                  — Health check
GET  /api/v1/tools                   — List available tools
POST /api/v1/actions/{tool_name}     — Execute tool call
GET  /api/v1/entities/{entity_type}  — Query entities
WS   /api/v1/events/stream           — Live event streaming

### Report APIs (dashboard-facing)
GET  /api/v1/report                  — Full simulation report
GET  /api/v1/report/scorecard        — Governance scorecard
GET  /api/v1/report/gaps             — Capability gap log
GET  /api/v1/report/causal/{event_id} — Causal trace
GET  /api/v1/report/challenges       — Two-direction observation

### Dashboard APIs (to be built by backend team)
GET  /api/v1/runs                    — List all runs (paginated, filterable)
GET  /api/v1/runs/:id                — Single run detail
GET  /api/v1/runs/:id/events         — Run events (paginated, filterable)
GET  /api/v1/runs/:id/events/:eid    — Single event with causal chain
GET  /api/v1/runs/:id/entities       — Run entities (paginated)
GET  /api/v1/runs/:id/entities/:eid  — Single entity with history
GET  /api/v1/runs/:id/actors/:aid    — Actor detail with history
GET  /api/v1/compare?runs=id1,id2    — Run comparison
WS   /ws/runs/:id/live               — Run-scoped live event stream
```

---

## File Manifest

**Modify — Source (8):**
- `src/services/api-client.ts` — all paths → `/api/v1/` prefix
- `src/types/domain.ts` — add `governance_score` to Run
- `src/hooks/queries/use-runs.ts` — add queryOptions parameter
- `src/pages/run-list/index.tsx` — full page orchestrator
- `src/pages/run-list/run-table.tsx` — card list wrapper
- `src/pages/run-list/run-row.tsx` — RunCard component
- `src/pages/run-list/run-filters.tsx` — filter bar
- `src/pages/run-list/compare-toolbar.tsx` — compare selection toolbar

**Modify — Tests/Mocks (3):**
- `tests/mocks/handlers.ts` — all paths → `/api/v1/` prefix
- `tests/mocks/data/runs.ts` — add governance_score, varied mock data
- `tests/pages/run-list.test.tsx` — 16 real tests replacing 2 todos

**Modify — Docs (1):**
- `IMPLEMENTATION_STATUS.md` — F3=done, session log, backend API docs

**Total: 12 files modified.**

---

## Verification

1. `npm run typecheck` — 0 errors
2. `npm run lint` — 0 errors
3. `npm run test` — F1 (124) + F2 (56) + F3 (~16) = ~198 tests pass, ~6 remaining page todos (F4-F6)
4. `npm run build` — succeeds
5. Visual: `npm run dev` → navigate to `/` → see run cards with filters, badges, scores, compare toolbar
