# F5a: Live Console — Feed + Header + Banner

## Context

F0-F4 complete (232 tests pass). F5 is the real-time WebSocket-driven 3-panel page. Splitting into F5a (feed side) and F5b (context/inspector side) with validation break.

**F5a scope:** Page shell (index.tsx) + RunHeaderBar + EventFeedItem + EventFeed + TransitionBanner (5 files + partial tests)
**F5b scope (next):** ContextView (3 modes: overview/event/agent) + Inspector + full tests

**Spec source:** `internal_docs/terrarium-frontend-spec.md` lines 360-482

**Decisions:**
- 3 context view modes (overview + event + agent). Entity mode deferred (EntityLink already navigates to F4 entities tab).
- Multi-line event cards per spec mockup (4-5 lines each)
- Activity Timeline sparkline deferred to F7
- Pause/Stop buttons rendered but disabled (no backend support)

---

## Data Flow (recap)

```
useLiveEvents(runId) → patches TanStack Query cache
Page components READ from cache:
  useRun(runId)       → run.current_tick, run.status (patched by WS 'status')
  useRunEvents(runId) → events list (REST backfill + WS 'event' appended)
```

Selection state: local `useState` (not URL — Live Console is ephemeral).

---

## Step 1: EventFeedItem — Multi-line Event Card

**File:** MODIFY `src/pages/live-console/event-feed-item.tsx`

**Spec mockup (lines 376-410) — each card is 4-5 lines:**
```
09:15:02 ✅
agent-α
refund_create
$249 refund
processed
```

**Full implementation:**

```tsx
import type { WorldEvent } from '@/types/domain';
import { OutcomeIcon } from '@/components/domain/outcome-icon';
import { TimestampCell } from '@/components/domain/timestamp-cell';
import { formatTick } from '@/lib/formatters';
import { cn } from '@/lib/cn';

interface EventFeedItemProps {
  event: WorldEvent;
  isSelected: boolean;
  onSelect: (eventId: string) => void;
  onSelectActor: (actorId: string) => void;
}

export function EventFeedItem({ event, isSelected, onSelect, onSelectActor }: EventFeedItemProps) {
  const handleActorClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onSelectActor(event.actor_id);
  };

  // Brief description: for policy events show enforcement, for others show action
  const description = event.policy_hit
    ? `${event.policy_hit.enforcement.toUpperCase()}: ${event.policy_hit.condition}`
    : event.outcome !== 'success'
      ? `${event.outcome.toUpperCase()}`
      : '';

  return (
    <button
      type="button"
      onClick={() => onSelect(event.event_id)}
      className={cn(
        'w-full rounded px-3 py-2 text-left transition-colors',
        isSelected
          ? 'bg-bg-elevated border border-border'
          : 'border border-transparent hover:bg-bg-hover',
      )}
    >
      {/* Line 1: Timestamp + Outcome Icon + Tick */}
      <div className="flex items-center gap-2">
        <TimestampCell iso={event.timestamp.wall_time} />
        <OutcomeIcon outcome={event.outcome} size={14} />
        <span className="font-mono text-xs text-text-muted">{formatTick(event.timestamp.tick)}</span>
      </div>

      {/* Line 2: Actor name (clickable for inspector) */}
      <div className="mt-0.5">
        <span
          role="button"
          tabIndex={0}
          onClick={handleActorClick}
          onKeyDown={(e) => { if (e.key === 'Enter') handleActorClick(e as unknown as React.MouseEvent); }}
          className="text-sm text-text-secondary hover:text-info transition-colors cursor-pointer"
        >
          {event.actor_id}
        </span>
      </div>

      {/* Line 3: Action name */}
      <div className="mt-0.5 font-mono text-xs text-text-primary">
        {event.action}
      </div>

      {/* Line 4: Brief description (conditional) */}
      {description && (
        <div className="mt-0.5 text-xs text-text-muted">
          {description}
        </div>
      )}
    </button>
  );
}
```

**Key patterns:**
- Outer `<button type="button">` for row click (selects event)
- Actor name is a nested `<span role="button">` with `stopPropagation` (selects actor in inspector)
- Multi-line layout: timestamp+icon, actor, action, description
- All data in font-mono where applicable
- Selected state: `bg-bg-elevated border-border`
- No emojis — uses OutcomeIcon (Lucide)

---

## Step 2: EventFeed — Left Panel with Auto-Scroll + Filters

**File:** MODIFY `src/pages/live-console/event-feed.tsx`

**Spec requirements:**
- EventFilter: "Dropdown to filter by: actor, service, outcome type, event type" (line 424)
- AutoScroll: "Toggle. When on, feed scrolls to latest. When off, user can scroll freely. Turns off automatically when user scrolls up." (line 425)
- Event count display

**Full implementation:**

```tsx
import { useState, useRef, useEffect, useMemo } from 'react';
import { ArrowDown, ArrowDownToLine } from 'lucide-react';
import type { WorldEvent } from '@/types/domain';
import { EmptyState } from '@/components/feedback/empty-state';
import { EventFeedItem } from './event-feed-item';
import { cn } from '@/lib/cn';

interface EventFeedProps {
  events: WorldEvent[];
  selectedEventId: string | null;
  onSelectEvent: (eventId: string) => void;
  onSelectActor: (actorId: string) => void;
}

// Data-driven filter options (spec says 4 filter types)
const OUTCOME_FILTER_OPTIONS: Record<string, string> = {
  '': 'All outcomes',
  success: 'Success',
  denied: 'Denied',
  held: 'Held',
  escalated: 'Escalated',
  error: 'Error',
  gap: 'Gap',
  flagged: 'Flagged',
};

const EVENT_TYPE_FILTER_OPTIONS: Record<string, string> = {
  '': 'All types',
  agent_action: 'Agent Action',
  policy_hold: 'Policy Hold',
  policy_block: 'Policy Block',
  permission_denied: 'Permission Denied',
  capability_gap: 'Capability Gap',
  animator_event: 'Animator Event',
  budget_warning: 'Budget Warning',
  budget_exhausted: 'Budget Exhausted',
};

export function EventFeed({ events, selectedEventId, onSelectEvent, onSelectActor }: EventFeedProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [filterOutcome, setFilterOutcome] = useState('');
  const [filterType, setFilterType] = useState('');

  // Filter events locally
  const filteredEvents = useMemo(() => {
    let result = events;
    if (filterOutcome) result = result.filter((e) => e.outcome === filterOutcome);
    if (filterType) result = result.filter((e) => e.event_type === filterType);
    return result;
  }, [events, filterOutcome, filterType]);

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [filteredEvents.length, autoScroll]);

  // Detect user scroll: disable auto-scroll when scrolled up
  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 32;
    setAutoScroll(isAtBottom);
  };

  const selectClass = 'rounded border border-border bg-bg-surface px-2 py-0.5 text-xs text-text-primary';

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="mb-2 flex items-center justify-between border-b border-border pb-2">
        <span className="text-xs font-medium uppercase text-text-muted">
          Event Feed ({filteredEvents.length})
        </span>
        <button
          type="button"
          onClick={() => setAutoScroll(!autoScroll)}
          title={autoScroll ? 'Auto-scroll ON' : 'Auto-scroll OFF'}
          className={cn(
            'rounded px-1.5 py-0.5 text-xs transition-colors',
            autoScroll ? 'bg-info/15 text-info' : 'bg-bg-elevated text-text-muted',
          )}
        >
          <ArrowDownToLine size={12} />
        </button>
      </div>

      {/* Filters */}
      <div className="mb-2 flex flex-wrap gap-2">
        <select
          value={filterOutcome}
          onChange={(e) => setFilterOutcome(e.target.value)}
          className={selectClass}
          aria-label="Filter by outcome"
        >
          {Object.entries(OUTCOME_FILTER_OPTIONS).map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          className={selectClass}
          aria-label="Filter by type"
        >
          {Object.entries(EVENT_TYPE_FILTER_OPTIONS).map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>
      </div>

      {/* Scrollable event list */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 space-y-1 overflow-y-auto"
      >
        {filteredEvents.length === 0 ? (
          <EmptyState title="No events yet" description="Waiting for simulation events..." />
        ) : (
          filteredEvents.map((event) => (
            <EventFeedItem
              key={event.event_id}
              event={event}
              isSelected={selectedEventId === event.event_id}
              onSelect={onSelectEvent}
              onSelectActor={onSelectActor}
            />
          ))
        )}
      </div>
    </div>
  );
}
```

**Key patterns:**
- Auto-scroll: ref + useEffect scrolls when events.length changes and autoScroll is true
- Scroll detection: onScroll checks distance from bottom (32px threshold)
- Filters: outcome + event_type (local state, useMemo filters)
- Data-driven option Records
- All selects have aria-labels
- Toggle button has type="button"

---

## Step 3: RunHeaderBar

**File:** MODIFY `src/pages/live-console/run-header-bar.tsx`

**Spec mockup (lines 370-372):**
```
Terrarium › exp-4-live-test › Live    [⏸ Pause] [⏹ Stop]
tick: 234 · agents: 2 active · events: 234 · budget: α 72% β 85%
```

**Full implementation:**

```tsx
import { Link } from 'react-router';
import { ChevronRight, Pause, Square } from 'lucide-react';
import type { Run } from '@/types/domain';
import type { ConnectionStatus } from '@/types/ui';
import { RunStatusBadge } from '@/components/domain/run-status-badge';
import { cn } from '@/lib/cn';

interface RunHeaderBarProps {
  run: Run;
  connectionStatus: ConnectionStatus;
  eventCount: number;
}

const STATUS_CONFIG: Record<ConnectionStatus, { dot: string; label: string }> = {
  connected: { dot: 'bg-success', label: 'Connected' },
  connecting: { dot: 'bg-info animate-pulse', label: 'Connecting...' },
  disconnected: { dot: 'bg-neutral', label: 'Disconnected' },
  reconnecting: { dot: 'bg-warning animate-pulse', label: 'Reconnecting...' },
};

export function RunHeaderBar({ run, connectionStatus, eventCount }: RunHeaderBarProps) {
  const tagName = run.tags[0] || run.id;
  const statusConfig = STATUS_CONFIG[connectionStatus];

  return (
    <div className="mb-4">
      {/* Breadcrumb */}
      <div className="mb-2 flex items-center gap-1 text-sm text-text-muted">
        <Link to="/" className="hover:text-text-primary transition-colors">Terrarium</Link>
        <ChevronRight size={14} />
        <span className="text-text-secondary">{tagName}</span>
        <ChevronRight size={14} />
        <span className="text-text-secondary">Live</span>
      </div>

      {/* Title row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold">{run.world_name}</h1>
          <RunStatusBadge status={run.status} />
          {/* Connection indicator */}
          <span className="flex items-center gap-1.5 text-xs text-text-muted">
            <span className={cn('h-2 w-2 rounded-full', statusConfig.dot)} />
            {statusConfig.label}
          </span>
        </div>
        {/* Pause/Stop buttons (disabled placeholders) */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled
            title="Pause — not available in v1"
            className="flex items-center gap-1 rounded border border-border px-3 py-1 text-xs text-text-muted opacity-50 cursor-not-allowed"
          >
            <Pause size={12} />
            Pause
          </button>
          <button
            type="button"
            disabled
            title="Stop — not available in v1"
            className="flex items-center gap-1 rounded border border-border px-3 py-1 text-xs text-text-muted opacity-50 cursor-not-allowed"
          >
            <Square size={12} />
            Stop
          </button>
        </div>
      </div>

      {/* Stats row */}
      <div className="mt-2 flex flex-wrap items-center gap-4 font-mono text-xs text-text-muted">
        <span>tick: {run.current_tick}</span>
        <span className="text-text-muted/40">·</span>
        <span>agents: {run.actor_count} active</span>
        <span className="text-text-muted/40">·</span>
        <span>events: {eventCount}</span>
      </div>
    </div>
  );
}
```

---

## Step 4: TransitionBanner

**File:** MODIFY `src/pages/live-console/transition-banner.tsx`

**Spec (line 474-477):** "run_complete → Switch to post-run analysis view"

```tsx
import { Link } from 'react-router';
import { ArrowRight, CheckCircle2 } from 'lucide-react';
import { runReportPath } from '@/constants/routes';

interface TransitionBannerProps {
  runId: string;
  visible: boolean;
}

export function TransitionBanner({ runId, visible }: TransitionBannerProps) {
  if (!visible) return null;

  return (
    <div className="mb-4 flex items-center justify-between rounded-lg border border-success/30 bg-success/10 px-4 py-3">
      <div className="flex items-center gap-2">
        <CheckCircle2 size={16} className="text-success" />
        <span className="text-sm font-medium text-success">Run completed</span>
      </div>
      <Link
        to={runReportPath(runId)}
        className="flex items-center gap-1 text-sm font-medium text-success hover:underline underline-offset-2"
      >
        View Report
        <ArrowRight size={14} />
      </Link>
    </div>
  );
}
```

---

## Step 5: Page Index (orchestrator — F5a version)

**File:** MODIFY `src/pages/live-console/index.tsx`

For F5a, the ContextView and Inspector are placeholder divs. They'll be implemented in F5b.

```tsx
import { useState, useCallback } from 'react';
import { useParams } from 'react-router';
import { useLiveEvents } from '@/hooks/use-live-events';
import { useRun } from '@/hooks/queries/use-runs';
import { useRunEvents } from '@/hooks/queries/use-events';
import { QueryGuard } from '@/components/feedback/query-guard';
import { PanelLayout } from '@/components/layout/panel-layout';
import { RunHeaderBar } from './run-header-bar';
import { EventFeed } from './event-feed';
import { ContextView } from './context-view';
import { Inspector } from './inspector';
import { TransitionBanner } from './transition-banner';

export function LiveConsolePage() {
  const { id } = useParams<{ id: string }>();
  const runId = id!;

  // WS bridge — connects, patches cache, returns connection status
  const connectionStatus = useLiveEvents(runId);

  // Read from cache (patched by WS)
  const runQuery = useRun(runId);
  const eventsQuery = useRunEvents(runId);

  // Selection state (local, not URL — Live Console is ephemeral)
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [selectedActorId, setSelectedActorId] = useState<string | null>(null);

  const handleSelectEvent = useCallback((eventId: string) => {
    setSelectedEventId(eventId);
    // Also update inspector to show the event's actor
    const event = eventsQuery.data?.items.find((e) => e.event_id === eventId);
    if (event) setSelectedActorId(event.actor_id);
  }, [eventsQuery.data]);

  const handleSelectActor = useCallback((actorId: string) => {
    setSelectedActorId(actorId);
  }, []);

  const handleClearSelection = useCallback(() => {
    setSelectedEventId(null);
    setSelectedActorId(null);
  }, []);

  const events = eventsQuery.data?.items ?? [];
  const eventCount = eventsQuery.data?.total ?? 0;

  return (
    <QueryGuard query={runQuery}>
      {(run) => (
        <div className="flex h-full flex-col">
          <RunHeaderBar
            run={run}
            connectionStatus={connectionStatus}
            eventCount={eventCount}
          />
          <TransitionBanner runId={runId} visible={run.status === 'completed'} />
          <div className="min-h-0 flex-1">
            <PanelLayout
              left={
                <EventFeed
                  events={events}
                  selectedEventId={selectedEventId}
                  onSelectEvent={handleSelectEvent}
                  onSelectActor={handleSelectActor}
                />
              }
              center={
                <ContextView
                  runId={runId}
                  run={run}
                  selectedEventId={selectedEventId}
                  selectedActorId={selectedActorId}
                  eventCount={eventCount}
                  onSelectEvent={handleSelectEvent}
                  onClearSelection={handleClearSelection}
                />
              }
              right={
                <Inspector
                  runId={runId}
                  selectedActorId={selectedActorId}
                  run={run}
                />
              }
            />
          </div>
        </div>
      )}
    </QueryGuard>
  );
}
```

**Note:** ContextView and Inspector get their REAL props in F5a (not placeholders), but their implementations will still be stubs until F5b. The stub files already exist and will render placeholder text. The page shell IS complete — it correctly wires useLiveEvents, selection state, PanelLayout, and all callbacks.

---

## Step 6: Update ContextView + Inspector stubs to accept props

The existing stubs accept no props. We need to update them to accept the props the page shell passes, even though the implementations are still placeholders until F5b.

**File:** MODIFY `src/pages/live-console/context-view.tsx`
```tsx
import type { Run } from '@/types/domain';

interface ContextViewProps {
  runId: string;
  run: Run;
  selectedEventId: string | null;
  selectedActorId: string | null;
  eventCount: number;
  onSelectEvent: (eventId: string) => void;
  onClearSelection: () => void;
}

export function ContextView({ selectedEventId, selectedActorId }: ContextViewProps) {
  if (selectedEventId) return <div className="text-sm text-text-muted">Event detail — implementing in F5b</div>;
  if (selectedActorId) return <div className="text-sm text-text-muted">Agent detail — implementing in F5b</div>;
  return <div className="text-sm text-text-muted">Run overview — implementing in F5b</div>;
}
```

**File:** MODIFY `src/pages/live-console/inspector.tsx`
```tsx
import type { Run } from '@/types/domain';

interface InspectorProps {
  runId: string;
  selectedActorId: string | null;
  run: Run;
}

export function Inspector({ selectedActorId }: InspectorProps) {
  return (
    <div className="text-xs text-text-muted">
      {selectedActorId ? `Inspector: ${selectedActorId} — implementing in F5b` : 'Inspector — implementing in F5b'}
    </div>
  );
}
```

These typed stubs ensure TypeScript compiles with the page shell passing correct props. F5b will replace the implementations.

---

## Step 7: F5a Tests

**File:** MODIFY `tests/pages/live-console.test.tsx`

Test setup (needs Routes/Route + MockWebSocket):

```tsx
import { describe, it, expect, vi, beforeAll, beforeEach, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router';
import { server } from '../mocks/server';
import { http, HttpResponse } from 'msw';
import { ApiClient } from '@/services/api-client';
import { WsManager } from '@/services/ws-manager';
import { MockWebSocket } from '../helpers/mock-websocket';
import { LiveConsolePage } from '@/pages/live-console';
import { createMockRun } from '../mocks/data/runs';

const testApi = new ApiClient('');
let testWs: WsManager;

vi.mock('@/providers/services-provider', () => ({
  useApiClient: () => testApi,
  useWsManager: () => testWs,
}));

beforeAll(() => server.listen());
beforeEach(() => {
  MockWebSocket.reset();
  vi.stubGlobal('WebSocket', MockWebSocket);
  testWs = new WsManager('ws://localhost');
  // Default: return a running run
  server.use(
    http.get('/api/v1/runs/:id', () =>
      HttpResponse.json(createMockRun({ status: 'running', completed_at: null })),
    ),
  );
});
afterEach(() => { server.resetHandlers(); vi.restoreAllMocks(); });
afterAll(() => server.close());

function renderPage(runId = 'run-test-001') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/runs/${runId}/live`]}>
        <Routes>
          <Route path="/runs/:id/live" element={<LiveConsolePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
```

**F5a test cases (~12):**

```
1. shows loading state initially
2. renders breadcrumb with "Live" label
3. renders run world_name in header
4. renders tick counter
5. renders agent count
6. renders event count
7. renders connection status indicator
8. renders Pause/Stop buttons (disabled)
9. renders event feed items from mock data
10. renders auto-scroll toggle
11. renders outcome filter dropdown
12. transition banner hidden when running
13. transition banner visible when completed (override mock)
14. shows error state when run fetch fails
```

---

## Step 8: Update Docs

- IMPLEMENTATION_STATUS.md: F5a in progress, session log
- `internal_docs/plans/F5a-live-feed.md`: save plan

---

## Verification (F5a checkpoint)

1. `npm run typecheck` — 0 errors
2. `npm run lint` — 0 errors
3. `npm run test` — F1-F4 (232) + F5a (~14) = ~246 tests pass
4. `npm run build` — succeeds
5. Visual: `/runs/test-1/live` → 3-panel layout with header, event feed, placeholder center/right

After F5a audit passes, proceed to F5b (ContextView + Inspector + full tests).

---

## File Manifest

**Modify — Source (7):**
- `src/pages/live-console/index.tsx` — full page orchestrator
- `src/pages/live-console/run-header-bar.tsx` — breadcrumb + stats + connection
- `src/pages/live-console/event-feed.tsx` — scrolling list + auto-scroll + filters
- `src/pages/live-console/event-feed-item.tsx` — multi-line event card
- `src/pages/live-console/transition-banner.tsx` — run complete banner
- `src/pages/live-console/context-view.tsx` — typed stub (F5b implementation)
- `src/pages/live-console/inspector.tsx` — typed stub (F5b implementation)

**Modify — Tests (1):**
- `tests/pages/live-console.test.tsx` (2 todos → ~14 real tests)

**Modify — Docs (1):**
- `IMPLEMENTATION_STATUS.md`

**Total: 9 files.**
