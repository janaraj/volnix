import { Loader2 } from 'lucide-react';

export function PageLoading() {
  return (
    <div className="flex h-64 flex-col items-center justify-center gap-3 text-text-muted">
      <Loader2 className="h-8 w-8 animate-spin" />
      <span className="text-sm">Loading...</span>
    </div>
  );
}
