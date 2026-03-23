import { useSearchParams } from 'react-router';
import { PageHeader } from '@/components/layout/page-header';

export function ComparePage() {
  const [searchParams] = useSearchParams();
  const runIds = searchParams.get('runs')?.split(',') ?? [];

  return (
    <div>
      <PageHeader title="Compare Runs" subtitle={`Comparing ${runIds.length} runs`} />
      <div className="rounded border border-bg-elevated bg-bg-surface p-8 text-center text-text-muted">
        Compare page — placeholder
        <div className="mt-2 font-mono text-xs">Runs: {runIds.join(', ') || 'none selected'}</div>
      </div>
    </div>
  );
}
