export function MetricCardsSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="animate-pulse rounded-lg border border-bg-elevated bg-bg-surface p-4">
          <div className="h-3 w-16 rounded bg-bg-elevated" />
          <div className="mt-2 h-6 w-12 rounded bg-bg-elevated" />
        </div>
      ))}
    </div>
  );
}

export function EventFeedSkeleton() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="animate-pulse rounded px-3 py-2">
          <div className="h-3 w-24 rounded bg-bg-elevated" />
          <div className="mt-1 h-3 w-32 rounded bg-bg-elevated" />
          <div className="mt-1 h-3 w-20 rounded bg-bg-elevated" />
        </div>
      ))}
    </div>
  );
}

export function ScorecardGridSkeleton() {
  return (
    <div className="animate-pulse space-y-2">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="flex gap-4">
          <div className="h-4 w-40 rounded bg-bg-elevated" />
          <div className="h-4 w-16 rounded bg-bg-elevated" />
          <div className="h-4 w-16 rounded bg-bg-elevated" />
        </div>
      ))}
    </div>
  );
}

export function EntityCardSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="animate-pulse rounded-lg border border-bg-elevated bg-bg-surface p-4">
          <div className="h-4 w-24 rounded bg-bg-elevated" />
          <div className="mt-2 space-y-1">
            <div className="h-3 w-full rounded bg-bg-elevated" />
            <div className="h-3 w-3/4 rounded bg-bg-elevated" />
          </div>
        </div>
      ))}
    </div>
  );
}
