import { useState, useMemo, useCallback } from 'react';
import { X, Search, ChevronLeft, ChevronRight, GitBranch } from 'lucide-react';
import { useKeyboard } from '@/hooks/use-keyboard';
import {
  useReactTable, getCoreRowModel, getSortedRowModel,
  getPaginationRowModel, flexRender,
  type ColumnDef, type SortingState, type OnChangeFn,
} from '@tanstack/react-table';
import { useRunEvents, useRunEvent } from '@/hooks/queries/use-events';
import { useUrlFilters } from '@/hooks/use-url-filters';
import { useUrlState } from '@/hooks/use-url-state';
import { QueryGuard } from '@/components/feedback/query-guard';
import { SectionLoading } from '@/components/feedback/section-loading';
import { EmptyState } from '@/components/feedback/empty-state';
import { OutcomeIcon } from '@/components/domain/outcome-icon';
import { ActorBadge } from '@/components/domain/actor-badge';
import { TimestampCell } from '@/components/domain/timestamp-cell';
import { EnforcementBadge } from '@/components/domain/enforcement-badge';
import { JsonViewer } from '@/components/domain/json-viewer';
import { EntityLink } from '@/components/domain/entity-link';
import { FidelityIndicator } from '@/components/domain/fidelity-indicator';
import { formatTick, truncateId, formatCurrency } from '@/lib/formatters';
import { cn } from '@/lib/cn';
import { PAGE_SIZE_EVENTS } from '@/constants/defaults';
import type { WorldEvent, Outcome } from '@/types/domain';
import type { EventFilterParams } from '@/types/api';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface EventsTabProps {
  runId: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const EVENT_DETAIL_DEFAULTS = { event: '' };
const TABLE_PAGE_SIZE = 10;

const OUTCOME_OPTIONS: Record<string, string> = {
  '': 'All outcomes',
  success: 'Success',
  denied: 'Denied',
  held: 'Held',
  escalated: 'Escalated',
  error: 'Error',
  gap: 'Gap',
  flagged: 'Flagged',
};

const EVENT_TYPE_OPTIONS: Record<string, string> = {
  '': 'All types',
  agent_action: 'Agent Action',
  policy_hold: 'Policy Hold',
  policy_block: 'Policy Block',
  policy_escalate: 'Policy Escalate',
  policy_flag: 'Policy Flag',
  permission_denied: 'Permission Denied',
  budget_deduction: 'Budget Deduction',
  budget_warning: 'Budget Warning',
  budget_exhausted: 'Budget Exhausted',
  capability_gap: 'Capability Gap',
  animator_event: 'Animator Event',
  state_change: 'State Change',
  side_effect: 'Side Effect',
  system_event: 'System Event',
};

// ---------------------------------------------------------------------------
// Sub-component A: EventFilters
// ---------------------------------------------------------------------------

function EventFilters({
  filters,
  onFilterChange,
}: {
  filters: Record<string, string>;
  onFilterChange: (updates: Record<string, string>) => void;
}) {
  const selectClass =
    'rounded border border-border bg-bg-surface px-3 py-1.5 text-sm text-text-primary';
  return (
    <div className="mb-4 flex flex-wrap items-center gap-3">
      <select
        value={filters.actor_id ?? ''}
        onChange={(e) => onFilterChange({ actor_id: e.target.value })}
        className={selectClass}
        aria-label="Filter by actor"
      >
        <option value="">All actors</option>
      </select>
      <select
        value={filters.service_id ?? ''}
        onChange={(e) => onFilterChange({ service_id: e.target.value })}
        className={selectClass}
        aria-label="Filter by service"
      >
        <option value="">All services</option>
      </select>
      <select
        value={filters.outcome ?? ''}
        onChange={(e) => onFilterChange({ outcome: e.target.value })}
        className={selectClass}
        aria-label="Filter by outcome"
      >
        {Object.entries(OUTCOME_OPTIONS).map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
      <select
        value={filters.event_type ?? ''}
        onChange={(e) => onFilterChange({ event_type: e.target.value })}
        className={selectClass}
        aria-label="Filter by type"
      >
        {Object.entries(EVENT_TYPE_OPTIONS).map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
      <div className="relative">
        <Search
          size={14}
          className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted"
        />
        <input
          type="text"
          placeholder="Search..."
          aria-label="Search events"
          className="rounded border border-border bg-bg-surface py-1.5 pl-8 pr-3 text-sm text-text-primary placeholder:text-text-muted"
          readOnly
          title="Server-side search available in a future release"
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component B: Column definitions
// ---------------------------------------------------------------------------

const columns: ColumnDef<WorldEvent>[] = [
  {
    accessorFn: (row) => row.timestamp?.tick ?? 0,
    id: 'tick',
    header: 'Tick',
    cell: ({ getValue }) => (
      <span className="font-mono text-xs text-text-muted">
        {formatTick(getValue<number>())}
      </span>
    ),
    size: 80,
  },
  {
    accessorFn: (row) => row.timestamp?.wall_time ?? '',
    id: 'time',
    header: 'Time',
    cell: ({ getValue }) => <TimestampCell iso={getValue<string>()} />,
    size: 120,
  },
  {
    accessorKey: 'actor_id',
    header: 'Actor',
    cell: ({ row }) => (
      <ActorBadge actorId={row.original.actor_id} role={row.original.actor_role} />
    ),
    size: 160,
  },
  {
    accessorKey: 'action',
    header: 'Action',
    cell: ({ getValue }) => (
      <span className="truncate text-sm text-text-secondary">
        {getValue<string>()}
      </span>
    ),
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

// ---------------------------------------------------------------------------
// Sub-component C: EventTableView (TanStack Table v8)
// ---------------------------------------------------------------------------

function EventTableView({
  events,
  sorting,
  onSortingChange,
  selectedEventId,
  onSelectEvent,
}: {
  events: WorldEvent[];
  sorting: SortingState;
  onSortingChange: OnChangeFn<SortingState>;
  selectedEventId: string;
  onSelectEvent: (id: string) => void;
}) {
  const table = useReactTable({
    data: events,
    columns,
    state: { sorting },
    onSortingChange,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: TABLE_PAGE_SIZE } },
  });

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b border-bg-elevated">
                {hg.headers.map((h) => (
                  <th
                    key={h.id}
                    className={cn(
                      'px-3 py-2 text-left text-xs font-medium uppercase text-text-muted',
                      h.column.getCanSort() &&
                        'cursor-pointer select-none hover:text-text-secondary',
                    )}
                    onClick={h.column.getToggleSortingHandler()}
                  >
                    {flexRender(h.column.columnDef.header, h.getContext())}
                    {h.column.getIsSorted() === 'asc' && ' \u2191'}
                    {h.column.getIsSorted() === 'desc' && ' \u2193'}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                onClick={() => onSelectEvent(row.original.event_id ?? '')}
                className={cn(
                  'cursor-pointer border-b border-bg-elevated transition-colors hover:bg-bg-hover',
                  selectedEventId === (row.original.event_id ?? '') && 'bg-bg-elevated',
                )}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-3 py-2">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {/* Pagination */}
      {table.getPageCount() > 1 && (
        <div className="mt-3 flex items-center justify-between text-xs text-text-muted">
          <span>
            Page {table.getState().pagination.pageIndex + 1} of{' '}
            {table.getPageCount()}
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
              className="rounded p-1 hover:bg-bg-hover disabled:opacity-30"
              aria-label="Previous page"
            >
              <ChevronLeft size={16} />
            </button>
            <button
              type="button"
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
              className="rounded p-1 hover:bg-bg-hover disabled:opacity-30"
              aria-label="Next page"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component D: CausalLink + EventDetail
// ---------------------------------------------------------------------------

function CausalLink({
  eventId,
  onSelect,
}: {
  eventId: string;
  onSelect: (id: string) => void;
}) {
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

function EventDetail({
  runId,
  eventId,
  onClose,
  onSelectEvent,
}: {
  runId: string;
  eventId: string;
  onClose: () => void;
  onSelectEvent: (id: string) => void;
}) {
  const eventQuery = useRunEvent(runId, eventId);
  return (
    <div className="mt-4 rounded-lg border border-border bg-bg-surface p-4">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-lg font-semibold">
          Event: <span className="font-mono">{truncateId(eventId, 16)}</span>
        </h3>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close event detail"
          className="rounded p-1 text-text-muted hover:bg-bg-hover hover:text-text-primary transition-colors"
        >
          <X size={18} />
        </button>
      </div>
      <QueryGuard query={eventQuery} loadingFallback={<SectionLoading />}>
        {(event) => (
          <div className="space-y-4">
            {/* Summary */}
            <p className="text-sm text-text-secondary">
              <span className="text-text-primary">{event.actor_id}</span> &rarr;{' '}
              {event.action ?? event.event_type} &rarr;{' '}
              <span className="uppercase font-medium">{event.outcome ?? ''}</span>
            </p>

            {/* Input / Output */}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <p className="mb-1 text-xs font-medium uppercase text-text-muted">
                  Input
                </p>
                <JsonViewer data={event.input_data} />
              </div>
              <div>
                <p className="mb-1 text-xs font-medium uppercase text-text-muted">
                  Output
                </p>
                <JsonViewer data={event.output_data} />
              </div>
            </div>

            {/* Budget impact */}
            {((event.budget_delta ?? 0) !== 0 || (event.budget_remaining ?? 0) > 0) && (
              <div className="text-sm text-text-secondary">
                <span className="text-xs font-medium uppercase text-text-muted">
                  Budget impact:{' '}
                </span>
                <span className="font-mono">
                  {(event.budget_delta ?? 0) < 0 ? '-' : '+'}
                  {formatCurrency(Math.abs(event.budget_delta ?? 0))}
                </span>
                <span className="text-text-muted"> &rarr; </span>
                <span className="font-mono">
                  {formatCurrency(event.budget_remaining ?? 0)} remaining
                </span>
              </div>
            )}

            {/* Policy section */}
            {event.policy_hit && (
              <div className="rounded border border-bg-elevated p-3">
                <p className="mb-1 text-xs font-medium uppercase text-text-muted">
                  Policy
                </p>
                <div className="space-y-1 text-sm">
                  <p className="text-text-secondary">
                    Policy:{' '}
                    <span className="font-medium text-text-primary">
                      {event.policy_hit.policy_name}
                    </span>
                  </p>
                  <p className="text-text-secondary">
                    Rule:{' '}
                    <span className="text-text-primary">
                      {event.policy_hit.condition}
                    </span>
                  </p>
                  <div className="flex items-center gap-2">
                    <span className="text-text-secondary">Enforcement:</span>
                    <EnforcementBadge enforcement={event.policy_hit.enforcement} />
                    {event.policy_hit.resolution && (
                      <span className="text-text-muted">
                        &rarr; {event.policy_hit.resolution}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Entity IDs -- clickable links to entities tab */}
            {(event.entity_ids ?? []).length > 0 && (
              <div>
                <p className="mb-1 text-xs font-medium uppercase text-text-muted">
                  Entities
                </p>
                <div className="flex flex-wrap gap-2">
                  {(event.entity_ids ?? []).map((eid) => (
                    <EntityLink key={eid} runId={runId} entityId={eid} />
                  ))}
                </div>
              </div>
            )}

            {/* Causal chain -- CLICKABLE links that update ?event= param */}
            {((event.causal_parent_ids ?? []).length > 0 || event.caused_by) && (
              <div>
                <div className="flex items-center gap-1 text-xs text-text-muted mb-1">
                  <GitBranch size={12} />
                  <span>Caused by:</span>
                </div>
                <div className="ml-3 flex flex-wrap gap-2">
                  {event.caused_by && (
                    <CausalLink eventId={event.caused_by} onSelect={onSelectEvent} />
                  )}
                  {(event.causal_parent_ids ?? [])
                    .filter((id) => id !== event.caused_by)
                    .map((id) => (
                      <CausalLink key={id} eventId={id} onSelect={onSelectEvent} />
                    ))}
                </div>
              </div>
            )}
            {(event.causal_child_ids ?? []).length > 0 && (
              <div>
                <div className="flex items-center gap-1 text-xs text-text-muted mb-1">
                  <GitBranch size={12} />
                  <span>Caused:</span>
                </div>
                <div className="ml-3 flex flex-wrap gap-2">
                  {(event.causal_child_ids ?? []).map((id) => (
                    <CausalLink key={id} eventId={id} onSelect={onSelectEvent} />
                  ))}
                </div>
              </div>
            )}
            {((event.causal_parent_ids ?? []).length > 0 ||
              (event.causal_child_ids ?? []).length > 0) && (
              <p className="text-xs text-text-muted">[View causal chain &rarr;]</p>
            )}

            {/* Fidelity */}
            <div>
              <FidelityIndicator
                tier={event.fidelity_tier ?? 2}
                source={event.fidelity?.fidelity_source ?? undefined}
              />
            </div>
          </div>
        )}
      </QueryGuard>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main EventsTab component
// ---------------------------------------------------------------------------

export function EventsTab({ runId }: EventsTabProps) {
  const [filters, setFilters] = useUrlFilters();
  const [detailState, setDetailState] = useUrlState(EVENT_DETAIL_DEFAULTS);
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

  useKeyboard({ Escape: () => setDetailState({ event: '' }) });

  const selectEvent = useCallback(
    (id: string) => setDetailState({ event: id }),
    [setDetailState],
  );
  const clearSelection = useCallback(
    () => setDetailState({ event: '' }),
    [setDetailState],
  );

  return (
    <div>
      <QueryGuard query={eventsQuery} loadingFallback={<SectionLoading />}>
        {(data) => (
          <>
            <h2 className="mb-3 text-lg font-semibold">
              EVENTS{' '}
              <span className="font-normal text-text-muted">
                ({data.total} total)
              </span>
            </h2>
            <EventFilters filters={filters} onFilterChange={setFilters} />
            {data.events.length === 0 ? (
              <EmptyState title="No events match your filters" />
            ) : (
              <EventTableView
                events={data.events}
                sorting={sorting}
                onSortingChange={setSorting}
                selectedEventId={detailState.event}
                onSelectEvent={selectEvent}
              />
            )}
          </>
        )}
      </QueryGuard>
      {detailState.event && (
        <EventDetail
          runId={runId}
          eventId={detailState.event}
          onClose={clearSelection}
          onSelectEvent={selectEvent}
        />
      )}
    </div>
  );
}
