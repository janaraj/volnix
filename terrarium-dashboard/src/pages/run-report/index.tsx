import { useParams } from 'react-router';
import { PageHeader } from '@/components/layout/page-header';

export function RunReportPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <div>
      <PageHeader title="Run Report" subtitle={`Run: ${id}`} />
      <div className="flex gap-2 border-b border-bg-elevated pb-2 text-sm">
        {['Overview', 'Scorecard', 'Events', 'Entities', 'Gaps', 'Conditions'].map((tab) => (
          <button key={tab} className="rounded px-3 py-1 text-text-secondary hover:bg-bg-hover hover:text-text-primary">
            {tab}
          </button>
        ))}
      </div>
      <div className="mt-4 rounded border border-bg-elevated bg-bg-surface p-8 text-center text-text-muted">
        Run Report tabs — placeholder
      </div>
    </div>
  );
}
