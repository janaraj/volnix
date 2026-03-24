# F4a: Run Report Page — Shell + Summary Tabs

## Context

F0-F3 complete (198 tests pass). F4 is the largest page (8 files, 6 tabs). Splitting into F4a (shell + summary tabs) and F4b (data-heavy tabs) with a validation audit between.

**F4a scope:** Page shell + ReportHeader + Overview tab + Scorecard tab + Conditions tab (5 source files + tests)
**F4b scope (next):** Events tab (TanStack Table) + Entities tab + Gaps tab + remaining tests

**Spec source:** `internal_docs/terrarium-frontend-spec.md` lines 484-796

**Deferred to future:**
- MissionResult component (needs structured mission criteria from backend — not in Run type)
- Scorecard cell click → modal (needs dedicated API for events by score dimension — deferred to F7)

---

## F4a Files (5 source + 1 test)

1. `src/pages/run-report/report-header.tsx`
2. `src/pages/run-report/index.tsx`
3. `src/pages/run-report/tabs/overview-tab.tsx`
4. `src/pages/run-report/tabs/scorecard-tab.tsx`
5. `src/pages/run-report/tabs/conditions-tab.tsx`
6. `tests/pages/run-report.test.tsx` (partial — shell + 3 tab tests)

---

## Step 1: ReportHeader

**File:** MODIFY `src/pages/run-report/report-header.tsx`

**Spec (line 494-497):**
```
Terrarium › exp-3-hostile-audit › Report
Support Organization · hostile · dynamic · governed · Score: 87
```

**Props:**
```tsx
import type { Run } from '@/types/domain';

interface ReportHeaderProps {
  run: Run;
}
```

**Implementation detail:**

```tsx
import type { Run } from '@/types/domain';
import { ScoreGrade } from '@/components/domain/score-grade';
import { ScoreBar } from '@/components/domain/score-bar';
import { RunStatusBadge } from '@/components/domain/run-status-badge';
import { truncateId } from '@/lib/formatters';

interface ReportHeaderProps {
  run: Run;
}

export function ReportHeader({ run }: ReportHeaderProps) {
  const tagName = run.tags[0] || truncateId(run.id, 16);

  return (
    <div className="mb-6">
      {/* Title row */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold text-text-primary">{tagName}</h1>
            <RunStatusBadge status={run.status} />
          </div>
          <p className="mt-1 text-sm text-text-secondary">{run.world_name}</p>
        </div>
        {/* Governance score (right side) */}
        {run.governance_score != null && (
          <div className="flex items-center gap-3">
            <ScoreGrade score={run.governance_score} />
            <div className="w-32">
              <ScoreBar value={run.governance_score} />
            </div>
          </div>
        )}
      </div>

      {/* Badge row */}
      <div className="mt-2 flex flex-wrap gap-1.5">
        {[run.reality_preset, run.behavior, run.fidelity, run.mode].map((badge) => (
          <span
            key={badge}
            className="rounded-full bg-bg-elevated px-2 py-0.5 text-xs text-text-secondary"
          >
            {badge}
          </span>
        ))}
        {run.seed != null && (
          <span className="rounded-full bg-bg-elevated px-2 py-0.5 font-mono text-xs text-text-muted">
            seed: {run.seed}
          </span>
        )}
      </div>
    </div>
  );
}
```

**Reuses:** ScoreGrade, ScoreBar, RunStatusBadge, truncateId
**No hooks:** Pure presentational, receives run as prop

---

## Step 2: Page Shell (index.tsx)

**File:** MODIFY `src/pages/run-report/index.tsx`

**Spec (lines 490-502):** Tabbed single-page with 6 tabs. Active tab from URL `?tab=`.

**Implementation detail:**

```tsx
import { useParams } from 'react-router';
import type { ReportTabId } from '@/types/ui';
import type { Run } from '@/types/domain';
import { useRun } from '@/hooks/queries/use-runs';
import { useUrlTabs } from '@/hooks/use-url-tabs';
import { QueryGuard } from '@/components/feedback/query-guard';
import { cn } from '@/lib/cn';
import { ReportHeader } from './report-header';
import { OverviewTab } from './tabs/overview-tab';
import { ScorecardTab } from './tabs/scorecard-tab';
import { EventsTab } from './tabs/events-tab';
import { EntitiesTab } from './tabs/entities-tab';
import { GapsTab } from './tabs/gaps-tab';
import { ConditionsTab } from './tabs/conditions-tab';

// Data-driven tab configuration
const TAB_ORDER: ReportTabId[] = [
  'overview', 'scorecard', 'events', 'entities', 'gaps', 'conditions',
];

const TAB_LABELS: Record<ReportTabId, string> = {
  overview: 'Overview',
  scorecard: 'Scorecard',
  events: 'Events',
  entities: 'Entities',
  gaps: 'Gaps',
  conditions: 'Conditions',
};

function ActiveTab({ tabId, run }: { tabId: ReportTabId; run: Run }) {
  switch (tabId) {
    case 'overview':   return <OverviewTab runId={run.id} run={run} />;
    case 'scorecard':  return <ScorecardTab runId={run.id} services={run.services} />;
    case 'events':     return <EventsTab runId={run.id} />;
    case 'entities':   return <EntitiesTab runId={run.id} />;
    case 'gaps':       return <GapsTab runId={run.id} />;
    case 'conditions': return <ConditionsTab conditions={run.conditions} />;
  }
}

export function RunReportPage() {
  const { id } = useParams<{ id: string }>();
  const runQuery = useRun(id!);
  const [activeTab, setTab] = useUrlTabs('overview');

  return (
    <div>
      <QueryGuard query={runQuery} emptyMessage="Run not found">
        {(run) => (
          <>
            <ReportHeader run={run} />

            {/* Tab bar */}
            <nav className="mb-4 flex gap-1 border-b border-border">
              {TAB_ORDER.map((tabId) => (
                <button
                  key={tabId}
                  type="button"
                  onClick={() => setTab(tabId)}
                  className={cn(
                    'px-3 py-2 text-sm font-medium transition-colors',
                    activeTab === tabId
                      ? 'border-b-2 border-info text-text-primary'
                      : 'text-text-secondary hover:text-text-primary',
                  )}
                >
                  {TAB_LABELS[tabId]}
                </button>
              ))}
            </nav>

            {/* Active tab content */}
            <ActiveTab tabId={activeTab as ReportTabId} run={run} />
          </>
        )}
      </QueryGuard>
    </div>
  );
}
```

**Key patterns:**
- Data-driven TAB_ORDER + TAB_LABELS (Record, not if/switch)
- Only active tab renders (lazy loading)
- All buttons have `type="button"`
- Active tab: `border-b-2 border-info` indicator
- QueryGuard wraps entire content (run is needed for header + all tabs)

---

## Step 3: Overview Tab

**File:** MODIFY `src/pages/run-report/tabs/overview-tab.tsx`

**Spec (lines 505-558):** Four metric cards + Key Events list + Agent Summary cards

Note: MissionResult is SKIPPED (backend doesn't have mission criteria fields — marked in IMPLEMENTATION_STATUS.md for future).

**Props:**
```tsx
interface OverviewTabProps {
  runId: string;
  run: Run;
}
```

**Sub-components (local to this file):**

**A. MetricCard:**
```tsx
function MetricCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-bg-surface p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-text-muted">{title}</p>
      <div className="mt-1">{children}</div>
    </div>
  );
}
```

**B. Four metrics from spec (line 513-518):**
- Score: governance_score → ScoreGrade + "GOOD"/"FAIR"/etc label
- Events: `run.event_count` as large number
- Actors: `run.actor_count` as large number
- Services: `run.services.length` with tier breakdown

**C. Key Events (spec line 527-537):**
Filter events by "interesting" types:
```tsx
const KEY_EVENT_TYPES = new Set([
  'policy_hold', 'policy_block', 'policy_escalate',
  'permission_denied', 'capability_gap', 'budget_exhausted', 'budget_warning',
]);
```
Each key event shows: OutcomeIcon + TimestampCell + action description + ActorBadge

**D. Agent Summary Cards (spec lines 539-547):**
From `useScorecard(runId)` — per agent card showing:
- ActorBadge (actor_id)
- ScoreBar (overall_score)
- Action count text
- Budget bar (budget used percentage — derived from budget data if available, else just show score)
- Policy hits count + violations count

**Full implementation:**
```tsx
import type { Run, WorldEvent } from '@/types/domain';
import { useScorecard } from '@/hooks/queries/use-scorecard';
import { useRunEvents } from '@/hooks/queries/use-events';
import { ScoreGrade } from '@/components/domain/score-grade';
import { ScoreBar } from '@/components/domain/score-bar';
import { OutcomeIcon } from '@/components/domain/outcome-icon';
import { ActorBadge } from '@/components/domain/actor-badge';
import { TimestampCell } from '@/components/domain/timestamp-cell';
import { EventTypeBadge } from '@/components/domain/event-type-badge';
import { QueryGuard } from '@/components/feedback/query-guard';
import { SectionLoading } from '@/components/feedback/section-loading';
import { EmptyState } from '@/components/feedback/empty-state';
import { formatScore } from '@/lib/formatters';
import { computeGrade } from '@/lib/score-utils';

const KEY_EVENT_TYPES = new Set([
  'policy_hold', 'policy_block', 'policy_escalate',
  'permission_denied', 'capability_gap', 'budget_exhausted', 'budget_warning',
]);
```

Sections render in order: MetricCards grid → Key Events → Agent Summary.
Each data-dependent section wrapped in its own `QueryGuard` with `SectionLoading` fallback.

---

## Step 4: Scorecard Tab

**File:** MODIFY `src/pages/run-report/tabs/scorecard-tab.tsx`

**Spec (lines 560-600):** Governance heatmap matrix + fidelity basis card.

**Props:**
```tsx
interface ScorecardTabProps {
  runId: string;
  services: ServiceSummary[];
}
```

**A. Scorecard Grid (HTML table):**
- Rows = score dimension names (from scores[].name)
- Columns = actor_id from each GovernanceScorecard entry
- Cells = `formatScore(value)` with `scoreToColorClass(value)` for bg color
- Overall row with `overall_score` per actor
- Header: ActorBadge for each column
- Left column: dimension names with underscore→space, capitalized
- Empty cells show "--" for null/missing scores (e.g., coordination for individual agents)

Format dimension name:
```tsx
function formatDimensionName(name: string): string {
  return name.replace(/_/g, ' ');
}
```

**B. Fidelity Basis Card (spec lines 582-591):**
- Service count
- Service list: ✓/~ prefix + ServiceBadge + FidelityIndicator + "Benchmark-grade"/"Score-reliable"
- Score basis: "78% Tier 1, 22% Tier 2"
- Confidence: badge with HIGH/MODERATE/LOW

Tier-to-label mapping (data-driven):
```tsx
const TIER_LABELS: Record<number, { prefix: string; label: string }> = {
  1: { prefix: '✓', label: 'Benchmark-grade' },
  2: { prefix: '~', label: 'Score-reliable' },
};
```

Confidence color (data-driven):
```tsx
const CONFIDENCE_COLORS: Record<string, string> = {
  high: 'text-success',
  moderate: 'text-warning',
  low: 'text-error',
};
```

Reuses: ActorBadge, ServiceBadge, FidelityIndicator, QueryGuard, SectionLoading
Imports: scoreToColorClass, formatScore, cn

---

## Step 5: Conditions Tab

**File:** MODIFY `src/pages/run-report/tabs/conditions-tab.tsx`

**Spec (lines 748-795):** 5 dimension cards with per-field values.

**Props:**
```tsx
interface ConditionsTabProps {
  conditions: WorldConditions;
}
```

**No API calls.** Data from run.conditions passed as prop.

**Data-driven dimension config:**
```tsx
interface DimensionField {
  key: string;
  label: string;
  type: 'number' | 'text';
}

const DIMENSION_CONFIG: Record<string, { title: string; fields: DimensionField[] }> = {
  information: {
    title: 'Information Quality',
    fields: [
      { key: 'staleness', label: 'Staleness', type: 'number' },
      { key: 'incompleteness', label: 'Incompleteness', type: 'number' },
      { key: 'inconsistency', label: 'Inconsistency', type: 'number' },
      { key: 'noise', label: 'Noise', type: 'number' },
    ],
  },
  reliability: {
    title: 'Service Reliability',
    fields: [
      { key: 'failures', label: 'Failures', type: 'number' },
      { key: 'timeouts', label: 'Timeouts', type: 'number' },
      { key: 'degradation', label: 'Degradation', type: 'number' },
    ],
  },
  friction: {
    title: 'Social Friction',
    fields: [
      { key: 'uncooperative', label: 'Uncooperative', type: 'number' },
      { key: 'deceptive', label: 'Deceptive', type: 'number' },
      { key: 'hostile', label: 'Hostile', type: 'number' },
      { key: 'sophistication', label: 'Sophistication', type: 'text' },
    ],
  },
  complexity: {
    title: 'Task Complexity',
    fields: [
      { key: 'ambiguity', label: 'Ambiguity', type: 'number' },
      { key: 'edge_cases', label: 'Edge Cases', type: 'number' },
      { key: 'contradictions', label: 'Contradictions', type: 'number' },
      { key: 'urgency', label: 'Urgency', type: 'number' },
      { key: 'volatility', label: 'Volatility', type: 'number' },
    ],
  },
  boundaries: {
    title: 'Governance Boundaries',
    fields: [
      { key: 'access_limits', label: 'Access Limits', type: 'number' },
      { key: 'rule_clarity', label: 'Rule Clarity', type: 'number' },
      { key: 'boundary_gaps', label: 'Boundary Gaps', type: 'number' },
    ],
  },
};
```

Each numeric field renders as: label + small bar (percentage width) + value.
Text fields render as: label + text badge.

5 cards in responsive grid: `grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3`

Local `DimensionCard` component:
```tsx
function DimensionCard({ title, dimension, fields }: {
  title: string;
  dimension: Record<string, unknown>;
  fields: DimensionField[];
}) {
  return (
    <div className="rounded-lg border border-border bg-bg-surface p-4">
      <h3 className="mb-3 text-sm font-semibold text-text-primary">{title}</h3>
      <div className="space-y-2">
        {fields.map((field) => {
          const value = dimension[field.key];
          return (
            <div key={field.key} className="flex items-center justify-between">
              <span className="text-xs text-text-secondary">{field.label}</span>
              {field.type === 'number' ? (
                <div className="flex items-center gap-2">
                  <div className="h-1.5 w-20 rounded-full bg-bg-elevated">
                    <div
                      className="h-full rounded-full bg-info"
                      style={{ width: `${Math.min(100, Number(value))}%` }}
                    />
                  </div>
                  <span className="w-6 text-right font-mono text-xs text-text-muted">
                    {String(value)}
                  </span>
                </div>
              ) : (
                <span className="rounded bg-bg-elevated px-1.5 py-0.5 text-xs text-text-secondary">
                  {String(value)}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

---

## Step 6: F4a Tests

**File:** MODIFY `tests/pages/run-report.test.tsx`

Wrapper (needs Routes/Route for useParams):
```tsx
function renderPage(runId = 'run-test-001', searchParams = '') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/runs/${runId}${searchParams}`]}>
        <Routes>
          <Route path="/runs/:id" element={<RunReportPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
```

**F4a test cases (~15):**

Shell:
1. shows loading state initially
2. renders report header with world name after load
3. renders governance score in header
4. renders all 6 tab buttons
5. overview tab is active by default
6. respects ?tab= URL parameter

Tab switching:
7. switches to scorecard tab when clicked
8. switches to conditions tab when clicked

Overview tab:
9. shows metric cards (event count, actor count, services count)
10. shows governance score metric card
11. shows agent summary cards from scorecard data

Scorecard tab:
12. renders dimension names (policy compliance, etc.)
13. renders actor columns
14. renders fidelity basis with confidence

Conditions tab:
15. renders all 5 dimension titles

---

## Step 7: Update docs

- Save plan to `internal_docs/plans/F4a-report-shell.md`
- Update `IMPLEMENTATION_STATUS.md`:
  - Current focus: F4a in progress
  - Add "Deferred" section noting MissionResult + scorecard modal
  - Session log for F4a

---

## Verification (F4a checkpoint)

1. `npm run typecheck` — 0 errors
2. `npm run lint` — 0 errors
3. `npm run test` — F1-F3 (198) + F4a (~15) = ~213 tests pass
4. `npm run build` — succeeds
5. Visual: navigate to `/runs/test-1` → see header with score, switch Overview/Scorecard/Conditions tabs

After F4a passes audit, proceed to F4b (Events + Entities + Gaps tabs).

---

## File Manifest

**Modify — Source (5):**
- `src/pages/run-report/index.tsx`
- `src/pages/run-report/report-header.tsx`
- `src/pages/run-report/tabs/overview-tab.tsx`
- `src/pages/run-report/tabs/scorecard-tab.tsx`
- `src/pages/run-report/tabs/conditions-tab.tsx`

**Modify — Tests (1):**
- `tests/pages/run-report.test.tsx`

**Modify — Docs (2):**
- `IMPLEMENTATION_STATUS.md`
- `internal_docs/plans/F4a-report-shell.md`

**NOT touched in F4a (deferred to F4b):**
- `src/pages/run-report/tabs/events-tab.tsx`
- `src/pages/run-report/tabs/entities-tab.tsx`
- `src/pages/run-report/tabs/gaps-tab.tsx`
