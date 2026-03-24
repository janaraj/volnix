import { useCompareStore } from '@/stores/compare-store';
import { RunCard } from '@/pages/run-list/run-row';
import type { Run } from '@/types/domain';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface RunTableProps {
  runs: Run[];
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RunTable({ runs }: RunTableProps) {
  const { selectedRunIds, toggleRun } = useCompareStore();

  return (
    <div className="grid gap-3">
      {runs.map((run) => (
        <RunCard
          key={run.id}
          run={run}
          selected={selectedRunIds.includes(run.id)}
          onToggleSelect={toggleRun}
        />
      ))}
    </div>
  );
}
