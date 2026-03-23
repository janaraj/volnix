import { useParams } from 'react-router';
import { PageHeader } from '@/components/layout/page-header';

export function LiveConsolePage() {
  const { id } = useParams<{ id: string }>();
  return (
    <div>
      <PageHeader title="Live Console" subtitle={`Run: ${id}`} />
      <div className="rounded border border-bg-elevated bg-bg-surface p-8 text-center text-text-muted">
        Live Console — 3-panel layout placeholder
      </div>
    </div>
  );
}
