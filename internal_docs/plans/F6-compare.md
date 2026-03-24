# F6: Compare Page — Implementation Plan

## Context

F0-F5 complete (257 tests pass). F6 is the LAST page — side-by-side comparison of 2-3 runs. Simpler than F4/F5 (no WebSocket, no tabs, no 3-panel). Single-page with 3 sections + PNG export.

**Spec source:** `internal_docs/terrarium-frontend-spec.md` lines 800-884
**Route:** `/compare?runs=id1,id2` or `/compare?runs=id1,id2,id3`

---

## Spec Cross-Check — ALL Items

### Page Header (spec lines 809-812):
- [x] Breadcrumb: "Terrarium › Compare"
- [x] "Comparing: tag1 vs tag2 vs tag3"
- [x] "World: {world_name} · {reality} · {behavior} · {mode}"
- [x] [Export Image] button (top right)

### ComparisonTable (spec lines 815-829, component line 871):
- [x] Rows = metrics, Columns = runs
- [x] Best values highlighted with "✓best"
- [x] Adapts to 2-way or 3-way
- [x] "This is the exportable view" — included in export ref

### DivergenceList (spec lines 831-850, component line 872):
- [x] List of divergence points
- [x] Each: tick + description + per-run decisions/consequences
- [x] "Click to expand into full event detail for all runs" — for v1: all details shown inline (no collapse). Document expand as F7.

### ScoreComparisonBars (spec lines 852-863, component line 873):
- [x] Horizontal bars per scorecard dimension
- [x] All runs overlaid per dimension
- [x] Uses ScoreBar component

### ExportButton (spec lines 874-884):
- [x] PNG of comparison table with branding
- [x] Includes: Terrarium name, world info, comparison table, footer
- [x] captureElementAsPng from lib/export.ts
- [x] Filename: terrarium-comparison.png

### Key Interactions (spec line 1072-1073):
- [x] "Click divergence point → Expands to show full event detail" — v1: show inline, defer expand/collapse to F7
- [x] "Click Export Image → Generates PNG" — wired to captureElementAsPng

### Backend dependency:
- DivergencePoint has no per-run `success: boolean` field — decisions/consequences are plain strings. No heuristic color coding — render all text neutrally. Document as backend dependency.

---

## Files to Implement (6 source + 1 test)

### Step 1: MetricDiffTable — Headline Comparison Table

**File:** MODIFY `src/pages/compare/metric-diff-table.tsx`

```tsx
import type { ComparisonMetric, Run } from '@/types/domain';
import { findBestValue } from '@/lib/comparison';
import { cn } from '@/lib/cn';

interface MetricDiffTableProps {
  metrics: ComparisonMetric[];
  runs: Run[];
}

export function MetricDiffTable({ metrics, runs }: MetricDiffTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border">
            <th className="px-4 py-3 text-left text-xs font-medium uppercase text-text-muted">Metric</th>
            {runs.map((run) => (
              <th key={run.id} className="px-4 py-3 text-center text-xs font-medium text-text-secondary">
                {run.tags[0] || run.id}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metrics.map((metric) => {
            const numericValues: Record<string, number> = {};
            for (const [runId, val] of Object.entries(metric.values)) {
              if (typeof val === 'number') numericValues[runId] = val;
            }
            const winnerId = metric.winner || findBestValue(numericValues);
            return (
              <tr key={metric.name} className="border-b border-bg-elevated">
                <td className="px-4 py-3 text-text-secondary">{metric.name}</td>
                {runs.map((run) => {
                  const value = metric.values[run.id];
                  const isWinner = run.id === winnerId;
                  return (
                    <td key={run.id} className={cn(
                      'px-4 py-3 text-center font-mono',
                      isWinner ? 'text-success font-medium' : 'text-text-primary',
                    )}>
                      {String(value ?? '--')}
                      {isWinner && <span className="ml-1 text-xs text-success">✓best</span>}
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

### Step 2: DivergenceTimeline — Divergence Points

**File:** MODIFY `src/pages/compare/divergence-timeline.tsx`

NO heuristics for positive/negative — render all decisions neutrally. Per-run text displayed as-is.

```tsx
import type { DivergencePoint, Run } from '@/types/domain';
import { formatTick } from '@/lib/formatters';

interface DivergenceTimelineProps {
  points: DivergencePoint[];
  runs: Run[];
}

export function DivergenceTimeline({ points, runs }: DivergenceTimelineProps) {
  if (points.length === 0) return null;
  return (
    <div>
      <h2 className="mb-3 text-lg font-semibold">Divergence Points</h2>
      <div className="space-y-3">
        {points.map((point, idx) => (
          <div key={idx} className="rounded-lg border border-border bg-bg-surface p-4">
            <div className="mb-3">
              <span className="font-mono text-xs text-text-muted">{formatTick(point.tick)}</span>
              <span className="ml-2 text-sm font-medium text-text-primary">{point.description}</span>
            </div>
            <div className="space-y-2">
              {runs.map((run) => {
                const decision = point.decisions[run.id];
                const consequence = point.consequences[run.id];
                if (!decision) return null;
                return (
                  <div key={run.id} className="text-sm">
                    <span className="font-medium text-text-secondary">{run.tags[0] || run.id}:</span>
                    <span className="ml-1 text-text-primary">{decision}</span>
                    {consequence && <span className="ml-1 text-text-muted">— {consequence}</span>}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

### Step 3: ScoreComparisonBars (entity-diff.tsx)

**File:** MODIFY `src/pages/compare/entity-diff.tsx`

```tsx
import type { ComparisonMetric, Run } from '@/types/domain';
import { ScoreBar } from '@/components/domain/score-bar';

interface ScoreComparisonBarsProps {
  metrics: ComparisonMetric[];
  runs: Run[];
}

export function ScoreComparisonBars({ metrics, runs }: ScoreComparisonBarsProps) {
  const scoreMetrics = metrics.filter((m) => {
    const vals = Object.values(m.values);
    return vals.every((v) => typeof v === 'number' && v >= 0 && v <= 100);
  });
  if (scoreMetrics.length === 0) return null;
  return (
    <div>
      <h2 className="mb-3 text-lg font-semibold">Score Comparison</h2>
      <div className="space-y-4">
        {scoreMetrics.map((metric) => (
          <div key={metric.name} className="rounded-lg border border-bg-elevated bg-bg-surface p-4">
            <h3 className="mb-2 text-sm font-medium text-text-secondary">{metric.name}</h3>
            <div className="space-y-1.5">
              {runs.map((run) => {
                const value = metric.values[run.id];
                const numValue = typeof value === 'number' ? value / 100 : 0;
                return <ScoreBar key={run.id} value={numValue} label={run.tags[0] || run.id} />;
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

### Step 4: ExportButton

**File:** MODIFY `src/pages/compare/export-button.tsx`

```tsx
import { useCallback } from 'react';
import { Download } from 'lucide-react';
import { captureElementAsPng } from '@/lib/export';

interface ExportButtonProps {
  targetRef: React.RefObject<HTMLDivElement | null>;
}

export function ExportButton({ targetRef }: ExportButtonProps) {
  const handleExport = useCallback(async () => {
    if (targetRef.current) {
      await captureElementAsPng(targetRef.current, 'terrarium-comparison.png');
    }
  }, [targetRef]);

  return (
    <button type="button" onClick={handleExport}
      className="inline-flex items-center gap-1.5 rounded border border-border px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors">
      <Download size={14} />
      Export Image
    </button>
  );
}
```

### Step 5: ComparisonGrid — no-op

**File:** MODIFY `src/pages/compare/comparison-grid.tsx`

```tsx
export function ComparisonGrid() { return null; }
```

### Step 6: Page Index — Orchestrator

**File:** MODIFY `src/pages/compare/index.tsx`

The exportRef wraps a styled container that includes branding elements for the PNG export:

```tsx
import { useRef } from 'react';
import { useSearchParams, Link } from 'react-router';
import { ChevronRight, Hexagon } from 'lucide-react';
import { useComparison } from '@/hooks/queries/use-compare';
import { QueryGuard } from '@/components/feedback/query-guard';
import { EmptyState } from '@/components/feedback/empty-state';
import { MetricDiffTable } from './metric-diff-table';
import { DivergenceTimeline } from './divergence-timeline';
import { ScoreComparisonBars } from './entity-diff';
import { ExportButton } from './export-button';

export function ComparePage() {
  const [searchParams] = useSearchParams();
  const runIds = searchParams.get('runs')?.split(',').filter(Boolean) ?? [];
  const exportRef = useRef<HTMLDivElement>(null);

  if (runIds.length < 2) {
    return (
      <div>
        <Breadcrumb />
        <EmptyState title="Select 2 or more runs to compare"
          description="Go to the Runs page and select runs using the checkboxes." />
      </div>
    );
  }

  return <CompareContent runIds={runIds} exportRef={exportRef} />;
}

function CompareContent({ runIds, exportRef }: { runIds: string[]; exportRef: React.RefObject<HTMLDivElement | null> }) {
  const comparisonQuery = useComparison(runIds);

  return (
    <div>
      <Breadcrumb />
      <QueryGuard query={comparisonQuery} emptyMessage="Comparison not available">
        {(data) => (
          <div>
            {/* Header */}
            <div className="mb-6 flex items-start justify-between">
              <div>
                <h1 className="text-2xl font-semibold">
                  Comparing: {data.runs.map((r) => r.tags[0] || r.id).join(' vs ')}
                </h1>
                {data.runs[0] && (
                  <p className="mt-1 text-sm text-text-secondary">
                    World: {data.runs[0].world_name} · {data.runs[0].reality_preset} · {data.runs[0].behavior} · {data.runs[0].mode}
                  </p>
                )}
              </div>
              <ExportButton targetRef={exportRef} />
            </div>

            {/* Exportable area — includes branding for PNG capture */}
            <div ref={exportRef} className="space-y-8 rounded-lg bg-bg-base p-4">
              {/* Branding header (visible in PNG) */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Hexagon size={20} className="text-accent" />
                  <span className="text-lg font-semibold">Terrarium</span>
                </div>
                {data.runs[0] && (
                  <span className="text-xs text-text-muted">
                    {data.runs[0].world_name} · {data.runs[0].reality_preset} · {data.runs[0].behavior} · {data.runs[0].mode}
                  </span>
                )}
              </div>

              {/* Comparison table */}
              <MetricDiffTable metrics={data.metrics} runs={data.runs} />

              {/* Divergence points */}
              <DivergenceTimeline points={data.divergence_points} runs={data.runs} />

              {/* Score bars */}
              <ScoreComparisonBars metrics={data.metrics} runs={data.runs} />

              {/* Footer (visible in PNG) */}
              <div className="border-t border-border pt-2 text-xs text-text-muted">
                Generated by Terrarium Dashboard
              </div>
            </div>
          </div>
        )}
      </QueryGuard>
    </div>
  );
}

function Breadcrumb() {
  return (
    <div className="mb-4 flex items-center gap-1 text-sm text-text-muted">
      <Link to="/" className="hover:text-text-primary transition-colors">Terrarium</Link>
      <ChevronRight size={14} />
      <span className="text-text-secondary">Compare</span>
    </div>
  );
}
```

**Key design choices:**
- `exportRef` wraps content WITH branding header + footer (spec lines 878-882)
- Branding: Hexagon icon + "Terrarium" text (matches sidebar logo)
- World info repeated inside export area
- Footer: "Generated by Terrarium Dashboard"
- `CompareContent` separated from `ComparePage` so hooks are conditionally called (useComparison needs runIds.length >= 2)
- No heuristic color coding on divergence decisions — plain text rendering

### Step 7: Tests (~12 cases)

**File:** MODIFY `tests/pages/compare.test.tsx`

```tsx
function renderPage(runIds = 'run-1,run-2') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/compare?runs=${runIds}`]}>
        <Routes>
          <Route path="/compare" element={<ComparePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
```

Tests:
1. shows empty state when < 2 runs
2. renders breadcrumb with "Compare"
3. renders "Comparing:" header with run tags
4. renders world info line
5. renders Export Image button
6. renders comparison table column headers (run tags)
7. renders metric rows from mock data (Governance Score)
8. highlights winner with "✓best"
9. renders divergence points heading
10. renders divergence point description
11. renders score comparison heading
12. shows loading state initially

### Step 8: Update Docs

- IMPLEMENTATION_STATUS.md: F6=done, Compare → ✅ done, 0 remaining todos
- `internal_docs/plans/F6-compare.md`: save plan

---

## Deferred Items (document in IMPLEMENTATION_STATUS.md)

| Feature | Reason | Target |
|---------|--------|--------|
| Divergence point expand/collapse | Spec says "Click to expand into full event detail" — v1 shows all inline | F7 (Polish) |
| DivergencePoint success/fail coloring | Type has no per-run boolean field — decisions/consequences are plain strings | Backend dependency |

---

## Verification

1. `npm run typecheck` — 0 errors
2. `npm run lint` — 0 errors
3. `npm run test` — F1-F5 (257) + F6 (~12) = ~269 tests pass, **0 remaining todos**
4. `npm run build` — succeeds
5. Visual: `/compare?runs=run-1,run-2` → table + divergence + bars + export button

---

## File Manifest

**Modify — Source (6):**
- `src/pages/compare/index.tsx` — orchestrator with branding export area
- `src/pages/compare/metric-diff-table.tsx` — comparison table
- `src/pages/compare/divergence-timeline.tsx` — divergence list (no heuristics)
- `src/pages/compare/entity-diff.tsx` — score bars (repurposed)
- `src/pages/compare/export-button.tsx` — PNG export
- `src/pages/compare/comparison-grid.tsx` — no-op

**Modify — Tests (1):**
- `tests/pages/compare.test.tsx` (2 todos → ~12 real tests)

**Modify — Docs (1):**
- `IMPLEMENTATION_STATUS.md`

**Total: 8 files.**
