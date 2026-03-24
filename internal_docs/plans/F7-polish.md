# F7: Polish — Complete Implementation Plan

## Context

F0-F6 complete (269 tests, 0 todos, all 4 pages). F7 covers ALL remaining frontend-only polish items from the spec. CLI integration documented but NOT implemented.

**Split: F7a (quick wins, ~5 items) → audit → F7b (substantial features, ~6 items)**

**Spec items covered:** 31 (loading skeletons), 32 (responsive), 33 (keyboard shortcuts), 35 (virtualized lists)
**Key interactions covered:** 1071 (scorecard modal), 1072 (divergence expand), 1076 (score bar formula hover)
**Already done:** 34 (URL state), 1067-1070 (click interactions), 1073-1075 (export/hover), 1077-1078 (filters/compare)

---

## F7a: Quick Wins (5 items)

### Item 1: Hover states on report cards (TRIVIAL)

**File:** MODIFY `src/pages/run-report/tabs/overview-tab.tsx`

Current AgentSummary cards (line 132) have `hover:border-border` but missing `hover:bg-bg-hover`. Add:

```tsx
// Change line 132 from:
className="rounded-lg border border-bg-elevated bg-bg-surface p-4 transition-colors hover:border-border"
// To:
className="rounded-lg border border-bg-elevated bg-bg-surface p-4 transition-colors hover:border-border hover:bg-bg-hover"
```

### Item 2: Layout persistence (LOW)

**File:** MODIFY `src/stores/layout-store.ts`

Re-add Zustand persist. Handle jsdom by wrapping storage access:

```tsx
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

interface LayoutStore {
  sidebarCollapsed: boolean;
  livePanelSizes: [number, number, number];
  toggleSidebar: () => void;
  setPanelSizes: (sizes: [number, number, number]) => void;
}

// Safe storage wrapper — handles jsdom/SSR environments
function safeStorage() {
  try {
    // Test if localStorage is available
    const testKey = '__zustand_test__';
    localStorage.setItem(testKey, '1');
    localStorage.removeItem(testKey);
    return createJSONStorage(() => localStorage);
  } catch {
    // Fallback: in-memory only (jsdom, SSR)
    return undefined;
  }
}

export const useLayoutStore = create<LayoutStore>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      livePanelSizes: [25, 50, 25] as [number, number, number],
      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      setPanelSizes: (sizes: [number, number, number]) => set({ livePanelSizes: sizes }),
    }),
    {
      name: 'terrarium-layout',
      storage: safeStorage(),
    },
  ),
);
```

Update test `tests/stores/layout-store.test.ts` to verify persist config exists.

### Item 3: Divergence expand/collapse (LOW-MED)

**File:** MODIFY `src/pages/compare/divergence-timeline.tsx`

Add useState for expanded set + toggle:

```tsx
import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { DivergencePoint, Run } from '@/types/domain';
import { formatTick } from '@/lib/formatters';

interface DivergenceTimelineProps {
  points: DivergencePoint[];
  runs: Run[];
}

export function DivergenceTimeline({ points, runs }: DivergenceTimelineProps) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  if (points.length === 0) return null;

  const toggle = (idx: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx); else next.add(idx);
      return next;
    });
  };

  return (
    <div>
      <h2 className="mb-3 text-lg font-semibold">Divergence Points</h2>
      <div className="space-y-3">
        {points.map((point, idx) => {
          const isExpanded = expanded.has(idx);
          return (
            <div key={idx} className="rounded-lg border border-border bg-bg-surface">
              {/* Clickable header */}
              <button
                type="button"
                onClick={() => toggle(idx)}
                className="flex w-full items-center gap-2 px-4 py-3 text-left transition-colors hover:bg-bg-hover"
              >
                {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                <span className="font-mono text-xs text-text-muted">{formatTick(point.tick)}</span>
                <span className="text-sm font-medium text-text-primary">{point.description}</span>
              </button>
              {/* Expandable detail */}
              {isExpanded && (
                <div className="border-t border-bg-elevated px-4 py-3 space-y-2">
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
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

### Item 4: Score bar formula on hover (QUICK — spec interaction 1076)

**File:** MODIFY `src/components/domain/score-bar.tsx`

Add optional `formula` prop. Show as `title` attribute on hover:

```tsx
interface ScoreBarProps {
  value: number;
  label?: string;
  formula?: string;  // NEW — shown on hover
}

export function ScoreBar({ value, label, formula }: ScoreBarProps) {
  const pct = Math.max(0, Math.min(100, value * 100));
  const hoverText = formula ? `${formatScore(value)} — ${formula}` : undefined;
  return (
    <div className="flex items-center gap-2" title={hoverText}>
      {label && <span className="w-32 truncate text-sm text-text-secondary">{label}</span>}
      <div className="h-2 flex-1 rounded-full bg-bg-elevated">
        <div className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: interpolateScoreColor(value) }} />
      </div>
      <span className="w-8 text-right font-mono text-xs text-text-primary">{formatScore(value)}</span>
    </div>
  );
}
```

Then update scorecard-tab.tsx to pass `formula` when rendering score cells. The `Score` type has `formula: string`.

### Item 5: Keyboard shortcuts (MED)

**File:** MODIFY `src/pages/live-console/index.tsx`

Wire `useKeyboard` hook with bindings:

```tsx
import { useKeyboard } from '@/hooks/use-keyboard';

// Inside LiveConsolePage, after selection state:
useKeyboard({
  Escape: () => handleClearSelection(),
  ArrowDown: () => {
    if (!selectedEventId && events.length > 0) {
      handleSelectEvent(events[0].event_id);
    } else if (selectedEventId) {
      const idx = events.findIndex((e) => e.event_id === selectedEventId);
      if (idx < events.length - 1) handleSelectEvent(events[idx + 1].event_id);
    }
  },
  ArrowUp: () => {
    if (selectedEventId) {
      const idx = events.findIndex((e) => e.event_id === selectedEventId);
      if (idx > 0) handleSelectEvent(events[idx - 1].event_id);
    }
  },
});
```

Also wire Escape in Run Report Events tab (`src/pages/run-report/tabs/events-tab.tsx`):
```tsx
useKeyboard({ Escape: clearSelection });
```

---

## F7b: Substantial Features (6 items)

### Item 6: Loading skeletons — shape-matched (MED)

**File:** CREATE `src/components/feedback/skeletons.tsx`

Multiple exported skeleton components:

```tsx
// MetricCardSkeleton — matches 4-column metric grid
export function MetricCardsSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="animate-pulse rounded-lg border border-bg-elevated bg-bg-surface p-4">
          <div className="h-3 w-16 rounded bg-bg-elevated" />
          <div className="mt-2 h-6 w-12 rounded bg-bg-elevated" />
        </div>
      ))}
    </div>
  );
}

// EventFeedSkeleton — matches multi-line event cards
export function EventFeedSkeleton() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="animate-pulse rounded px-3 py-2">
          <div className="h-3 w-24 rounded bg-bg-elevated" />
          <div className="mt-1 h-3 w-32 rounded bg-bg-elevated" />
          <div className="mt-1 h-3 w-20 rounded bg-bg-elevated" />
        </div>
      ))}
    </div>
  );
}

// ScorecardGridSkeleton — matches table rows
export function ScorecardGridSkeleton() {
  return (
    <div className="animate-pulse space-y-2">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="flex gap-4">
          <div className="h-4 w-40 rounded bg-bg-elevated" />
          <div className="h-4 w-16 rounded bg-bg-elevated" />
          <div className="h-4 w-16 rounded bg-bg-elevated" />
        </div>
      ))}
    </div>
  );
}

// EntityCardSkeleton — matches entity card list
export function EntityCardSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="animate-pulse rounded-lg border border-bg-elevated bg-bg-surface p-4">
          <div className="h-4 w-24 rounded bg-bg-elevated" />
          <div className="mt-2 space-y-1">
            <div className="h-3 w-full rounded bg-bg-elevated" />
            <div className="h-3 w-3/4 rounded bg-bg-elevated" />
          </div>
        </div>
      ))}
    </div>
  );
}
```

Then update page tabs to use specific skeletons as `loadingFallback` in QueryGuard.

### Item 7: Scorecard cell → event modal (MED)

**File:** CREATE `src/components/feedback/dialog.tsx`

Lightweight modal:

```tsx
import { useEffect, useCallback } from 'react';
import { X } from 'lucide-react';

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}

export function Dialog({ open, onClose, title, children }: DialogProps) {
  // Close on Escape
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') onClose();
  }, [onClose]);

  useEffect(() => {
    if (open) document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, handleKeyDown]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-bg-base/80" onClick={onClose} />
      {/* Content */}
      <div className="relative z-10 w-full max-w-lg rounded-lg border border-border bg-bg-surface p-6 shadow-lg">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Close dialog"
            className="rounded p-1 text-text-muted hover:bg-bg-hover hover:text-text-primary transition-colors">
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
```

Then update `src/pages/run-report/tabs/scorecard-tab.tsx`:
- Add `useState<{ dimension: string; violations: string[] } | null>(null)` for selected cell
- Wrap score cells in `<button type="button" onClick={() => setSelected(...)}>`
- Render `<Dialog>` showing dimension name + violation event IDs (truncated, with copy)

### Item 8: Activity Timeline sparkline (MED)

**File:** CREATE `src/pages/live-console/activity-timeline.tsx`

```tsx
import { useMemo } from 'react';
import { BarChart, Bar, XAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import type { WorldEvent } from '@/types/domain';
import { interpolateScoreColor } from '@/lib/color-utils';

interface ActivityTimelineProps {
  events: WorldEvent[];
  onJumpToTick: (tick: number) => void;
}

const BUCKET_COUNT = 50;

export function ActivityTimeline({ events, onJumpToTick }: ActivityTimelineProps) {
  const chartData = useMemo(() => {
    if (events.length === 0) return [];
    const maxTick = Math.max(...events.map((e) => e.timestamp.tick));
    const bucketSize = Math.max(1, Math.ceil(maxTick / BUCKET_COUNT));
    const buckets: Array<{ tick: number; count: number; successRate: number }> = [];

    for (let i = 0; i < BUCKET_COUNT; i++) {
      const startTick = i * bucketSize;
      const endTick = (i + 1) * bucketSize;
      const bucketEvents = events.filter((e) => e.timestamp.tick >= startTick && e.timestamp.tick < endTick);
      const successCount = bucketEvents.filter((e) => e.outcome === 'success').length;
      buckets.push({
        tick: startTick,
        count: bucketEvents.length,
        successRate: bucketEvents.length > 0 ? successCount / bucketEvents.length : 1,
      });
    }
    return buckets;
  }, [events]);

  if (chartData.length === 0) return null;

  return (
    <div className="h-12 w-full border-t border-border bg-bg-surface px-4 py-1">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} onClick={(data) => {
          if (data?.activePayload?.[0]) onJumpToTick(data.activePayload[0].payload.tick);
        }}>
          <XAxis dataKey="tick" hide />
          <Tooltip content={({ active, payload }) => {
            if (!active || !payload?.[0]) return null;
            const d = payload[0].payload;
            return (
              <div className="rounded bg-bg-elevated px-2 py-1 text-xs">
                Tick {d.tick}: {d.count} events
              </div>
            );
          }} />
          <Bar dataKey="count" cursor="pointer">
            {chartData.map((entry, idx) => (
              <Cell key={idx} fill={interpolateScoreColor(entry.successRate)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
```

Wire into Live Console `index.tsx` below PanelLayout.

### Item 9: Virtualized lists (MED-HIGH)

**Install:** `npm install @tanstack/react-virtual`

**File:** MODIFY `src/pages/live-console/event-feed.tsx`

Replace `filteredEvents.map()` with virtualized rendering:

```tsx
import { useVirtualizer } from '@tanstack/react-virtual';

// Inside EventFeed component, after filteredEvents:
const virtualizer = useVirtualizer({
  count: filteredEvents.length,
  getScrollElement: () => scrollRef.current,
  estimateSize: () => 80, // estimated 80px per multi-line event card
  overscan: 10,
});

// Replace the map() with virtualized items:
<div ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto relative"
  style={{ height: '100%' }}>
  <div style={{ height: `${virtualizer.getTotalSize()}px`, position: 'relative' }}>
    {virtualizer.getVirtualItems().map((virtualItem) => {
      const event = filteredEvents[virtualItem.index];
      return (
        <div key={virtualItem.key} ref={virtualizer.measureElement}
          data-index={virtualItem.index}
          style={{ position: 'absolute', top: 0, left: 0, width: '100%',
            transform: `translateY(${virtualItem.start}px)` }}>
          <EventFeedItem event={event} isSelected={selectedEventId === event.event_id}
            onSelect={onSelectEvent} onSelectActor={onSelectActor} />
        </div>
      );
    })}
  </div>
</div>
```

Auto-scroll with virtualization: `virtualizer.scrollToIndex(filteredEvents.length - 1)` instead of manual scrollTop.

### Item 10: Responsive 1280px (MED)

**Files:** Multiple layout components

Key changes:
- **Sidebar:** Auto-collapse at `lg` breakpoint (add media query check or Tailwind responsive)
- **PanelLayout:** Below `md`, stack panels vertically instead of horizontal
- **Report grids:** Verify 2-col at `md`, 3-col at `lg`

PanelLayout responsive update:
```tsx
export function PanelLayout({ left, center, right }: PanelLayoutProps) {
  return (
    <div className="flex h-full flex-col md:flex-row">
      <div className="min-w-0 md:w-1/4 overflow-auto bg-bg-surface p-4 border-b md:border-b-0 md:border-r border-border">{left}</div>
      <div className="min-w-0 flex-1 overflow-auto bg-bg-surface p-4">{center}</div>
      <div className="min-w-0 md:w-1/4 overflow-auto bg-bg-surface p-4 border-t md:border-t-0 md:border-l border-border">{right}</div>
    </div>
  );
}
```

### Item 11: CLI documentation (DOCUMENT ONLY)

**File:** MODIFY `IMPLEMENTATION_STATUS.md`

Add section:
```
## CLI Integration Requirements (for backend team)

The `terrarium dashboard` CLI command should:
1. Build frontend: `cd terrarium-dashboard && npm run build` → produces `dist/`
2. Serve `dist/` as static files from the backend server (FastAPI/Uvicorn)
3. Proxy `/api/v1/*` and `/ws/*` to the Terrarium backend API
4. Port config from `terrarium.toml` `[dashboard]` section (host: 127.0.0.1, port: 8200)
5. In development: run `npm run dev` (Vite dev server on port 3000) with proxy to backend

Vite proxy already configured in vite.config.ts:
- `/api` → http://localhost:8200
- `/ws` → ws://localhost:8200
```

---

## Implementation Order

**F7a (quick wins):**
1. Hover states (trivial)
2. Score bar formula hover (quick)
3. Layout persistence (low)
4. Divergence expand/collapse (low-med)
5. Keyboard shortcuts (med)

**Audit break**

**F7b (substantial):**
6. Responsive 1280px (med)
7. Loading skeletons (med)
8. Dialog component + scorecard modal (med)
9. Activity Timeline sparkline (med)
10. Virtualized lists (med-high — npm install)
11. CLI documentation

---

## Tests

**F7a tests (~8 new):**
- Layout store persist test (verify persist config)
- Divergence expand/collapse (click header toggles content)
- Keyboard Escape clears selection in Live Console
- Keyboard ArrowDown selects next event
- Score bar with formula shows title attribute

**F7b tests (~10 new):**
- Dialog opens/closes on trigger
- Dialog closes on Escape
- Dialog closes on backdrop click
- Scorecard cell click opens dialog
- Skeleton components render without crash (smoke tests)
- Activity Timeline renders with events
- Responsive: PanelLayout stacks vertically below md

**Total new tests: ~18**

---

## Verification

After F7a:
- `npm run typecheck` — 0 errors
- `npm run test` — ~277 tests pass
- Visual: keyboard shortcuts work, divergence toggles, score bar shows formula

After F7b:
- `npm run typecheck` — 0 errors
- `npm run test` — ~287 tests pass
- `npm run build` — succeeds
- Visual: scorecard modal, sparkline chart, responsive layout at 1280px

---

## File Manifest

**F7a (modify ~7 files):**
- `src/pages/run-report/tabs/overview-tab.tsx` — hover states
- `src/components/domain/score-bar.tsx` — formula prop
- `src/pages/run-report/tabs/scorecard-tab.tsx` — pass formula to ScoreBar
- `src/stores/layout-store.ts` — persist middleware
- `src/pages/compare/divergence-timeline.tsx` — expand/collapse
- `src/pages/live-console/index.tsx` — keyboard shortcuts
- `src/pages/run-report/tabs/events-tab.tsx` — Escape shortcut

**F7b (create ~3 new + modify ~5 + install 1):**
- CREATE: `src/components/feedback/dialog.tsx`
- CREATE: `src/components/feedback/skeletons.tsx`
- CREATE: `src/pages/live-console/activity-timeline.tsx`
- MODIFY: `src/pages/run-report/tabs/scorecard-tab.tsx` — modal trigger
- MODIFY: `src/pages/live-console/event-feed.tsx` — virtualization
- MODIFY: `src/pages/live-console/index.tsx` — timeline slot
- MODIFY: `src/components/layout/panel-layout.tsx` — responsive
- MODIFY: `IMPLEMENTATION_STATUS.md` — CLI docs + F7 session log
- INSTALL: `@tanstack/react-virtual`

**Save plan:** `internal_docs/plans/F7-polish.md`

**Total: ~15 files modified/created, ~18 new tests, 1 npm install**
