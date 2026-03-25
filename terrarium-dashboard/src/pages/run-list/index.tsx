import { useMemo } from 'react';
import { Lightbulb } from 'lucide-react';
import { PageHeader } from '@/components/layout/page-header';
import { QueryGuard } from '@/components/feedback/query-guard';
import { EmptyState } from '@/components/feedback/empty-state';
import { useUrlState } from '@/hooks/use-url-state';
import { useRuns } from '@/hooks/queries/use-runs';
import { PAGE_SIZE_RUNS } from '@/constants/defaults';
import { RunFilters, FILTER_DEFAULTS } from '@/pages/run-list/run-filters';
import { RunTable } from '@/pages/run-list/run-table';
import { CompareToolbar } from '@/pages/run-list/compare-toolbar';
import type { RunListParams, RunsListResponse } from '@/types/api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildParams(filters: typeof FILTER_DEFAULTS): RunListParams {
  const params: RunListParams = { limit: PAGE_SIZE_RUNS };
  if (filters.status) params.status = filters.status;
  if (filters.preset) params.preset = filters.preset;
  if (filters.tag) params.tag = filters.tag;
  return params;
}

function hasRunningRun(data: RunsListResponse | undefined): boolean {
  return data?.runs.some((r) => r.status === 'running') ?? false;
}

// ---------------------------------------------------------------------------
// Hint shown when there are no runs at all
// ---------------------------------------------------------------------------

function NewRunHint() {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-text-muted">
      <Lightbulb size={14} />
      Start a new run from the CLI
    </span>
  );
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export function RunListPage() {
  const [filters, setFilters] = useUrlState(FILTER_DEFAULTS);

  const params = useMemo(() => buildParams(filters), [filters]);

  const runsQuery = useRuns(params, {
    refetchInterval: (query) =>
      hasRunningRun(query.state.data as RunsListResponse | undefined) ? 10_000 : false,
  });

  const isFiltered = filters.status !== '' || filters.preset !== '' || filters.tag !== '';

  return (
    <div>
      <PageHeader
        title="Runs"
        subtitle="All simulation runs"
        actions={<NewRunHint />}
      />

      <RunFilters filters={filters} onChange={setFilters} />

      <QueryGuard query={runsQuery}>
        {(data) => {
          if (data.runs.length === 0) {
            return isFiltered ? (
              <EmptyState
                title="No runs match your filters"
                description="Try adjusting the status, preset, or tag filters."
              />
            ) : (
              <EmptyState
                title="No runs yet"
                description="Start a simulation from the CLI to see results here."
              />
            );
          }

          return (
            <>
              <RunTable runs={data.runs} />
              <CompareToolbar />
            </>
          );
        }}
      </QueryGuard>
    </div>
  );
}
