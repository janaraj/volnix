import { AlertTriangle } from 'lucide-react';

interface ErrorDisplayProps {
  error: Error;
  onRetry?: () => void;
}

export function ErrorDisplay({ error, onRetry }: ErrorDisplayProps) {
  return (
    <div className="rounded border border-error/20 bg-error/5 p-4">
      <div className="flex items-center gap-2">
        <AlertTriangle size={16} className="text-error" />
        <p className="text-sm text-error">{error.message}</p>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-3 rounded border border-border px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors"
        >
          Retry
        </button>
      )}
    </div>
  );
}
