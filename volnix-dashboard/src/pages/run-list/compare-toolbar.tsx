import { useNavigate } from 'react-router';
import { X, GitCompareArrows } from 'lucide-react';
import { useCompareStore } from '@/stores/compare-store';
import { comparePath } from '@/constants/routes';

export function CompareToolbar() {
  const navigate = useNavigate();
  const { selectedRunIds, clearSelection } = useCompareStore();

  if (selectedRunIds.length === 0) return null;

  return (
    <div className="fixed bottom-4 left-1/2 z-50 flex -translate-x-1/2 items-center gap-4 rounded-lg border border-border-default bg-bg-surface px-5 py-3 shadow-lg">
      <span className="text-sm text-text-secondary">
        {selectedRunIds.length} run{selectedRunIds.length !== 1 && 's'} selected
      </span>

      <button
        type="button"
        onClick={clearSelection}
        className="inline-flex items-center gap-1 text-xs text-text-muted hover:text-text-primary"
      >
        <X size={14} />
        Clear
      </button>

      <button
        type="button"
        disabled={selectedRunIds.length < 2}
        onClick={() => navigate(comparePath(selectedRunIds))}
        className="inline-flex items-center gap-1.5 rounded bg-info px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40"
      >
        <GitCompareArrows size={14} />
        Compare Selected
      </button>
    </div>
  );
}
