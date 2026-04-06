import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import { Lightbulb, Plus } from 'lucide-react';
import { PageHeader } from '@/components/layout/page-header';
import { QueryGuard } from '@/components/feedback/query-guard';
import { EmptyState } from '@/components/feedback/empty-state';
import { useUrlState } from '@/hooks/use-url-state';
import { useRuns } from '@/hooks/queries/use-runs';
import { useWorlds } from '@/hooks/queries/use-worlds';
import { useApiClient } from '@/providers/services-provider';
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
  if (filters.world_id) (params as Record<string, unknown>).world_id = filters.world_id;
  return params;
}

function hasRunningRun(data: RunsListResponse | undefined): boolean {
  return data?.runs.some((r) => r.status === 'running') ?? false;
}

// ---------------------------------------------------------------------------
// New Run button with world selector
// ---------------------------------------------------------------------------

function NewRunButton({ hasActiveRun }: { hasActiveRun: boolean }) {
  const api = useApiClient();
  const navigate = useNavigate();
  const worldsQuery = useWorlds();
  const [creating, setCreating] = useState(false);
  const [showPicker, setShowPicker] = useState(false);

  const worlds = worldsQuery.data?.worlds ?? [];

  async function handleNewRun(worldId?: string) {
    if (hasActiveRun) {
      const confirmed = window.confirm(
        'The current active run will be completed and a scorecard generated. Start a new run?'
      );
      if (!confirmed) return;
    }
    setCreating(true);
    setShowPicker(false);
    try {
      const result = await api.newRun(worldId);
      navigate(`/runs/${result.run_id}/live`);
    } catch {
      // May fail if no world available
    }
    setCreating(false);
  }

  if (worlds.length === 0) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-text-muted">
        <Lightbulb size={14} />
        Start a new run from the CLI
      </span>
    );
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => worlds.length === 1 ? handleNewRun(worlds[0].world_id) : setShowPicker(!showPicker)}
        disabled={creating}
        className="inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-accent/80 disabled:opacity-50"
      >
        <Plus size={14} />
        {creating ? 'Creating...' : 'New Run'}
      </button>
      {showPicker && worlds.length > 1 && (
        <div className="absolute right-0 top-full z-10 mt-1 w-64 rounded-md border border-border bg-bg-surface shadow-lg">
          <div className="p-2 text-xs font-medium text-text-muted">Select world</div>
          {worlds.filter(w => w.status === 'generated').map((w) => (
            <button
              key={w.world_id}
              type="button"
              onClick={() => handleNewRun(w.world_id)}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-bg-hover"
            >
              <span className="truncate font-medium">{w.name}</span>
              <span className="ml-auto text-xs text-text-muted">{w.world_id.slice(0, 12)}</span>
            </button>
          ))}
        </div>
      )}
    </div>
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

  const isFiltered = filters.status !== '' || filters.preset !== '' || filters.tag !== '' || filters.world_id !== '';

  return (
    <div>
      <PageHeader
        title="Runs"
        subtitle={filters.world_id ? `Runs for world ${filters.world_id}` : 'All simulation runs'}
        actions={<NewRunButton hasActiveRun={hasRunningRun(runsQuery.data)} />}
      />

      {filters.world_id && (
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-accent/20 bg-accent/5 px-4 py-2 text-sm text-text-secondary">
          <span>Filtered by world:</span>
          <span className="font-mono text-accent">{filters.world_id}</span>
          <button
            type="button"
            onClick={() => setFilters({ world_id: '' })}
            className="ml-auto text-xs text-text-muted hover:text-text-primary"
          >
            Clear
          </button>
        </div>
      )}

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
