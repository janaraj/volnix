import type { DivergencePoint, Run } from '@/types/domain';
import { formatTick } from '@/lib/formatters';

interface DivergenceTimelineProps {
  points: DivergencePoint[];
  runs: Run[];
}

export function DivergenceTimeline({ points, runs }: DivergenceTimelineProps) {
  if (points.length === 0) return null;

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium text-text-secondary">Divergence Points</h3>
      <div className="space-y-3">
        {points.map((point, idx) => (
          <div key={idx} className="rounded border border-bg-elevated bg-bg-surface p-4">
            <div className="mb-2 flex items-baseline gap-2">
              <span className="font-mono text-xs text-text-muted">{formatTick(point.tick)}</span>
              <span className="text-sm text-text-primary">{point.description}</span>
            </div>
            <div className="space-y-1">
              {runs.map((run) => {
                const decision = point.decisions[run.id];
                const consequence = point.consequences[run.id];
                if (!decision && !consequence) return null;
                return (
                  <div key={run.id} className="ml-4 text-xs">
                    <span className="font-medium text-text-secondary">
                      {run.tags[0] ?? run.id}:
                    </span>{' '}
                    <span className="font-mono text-text-primary">{decision}</span>
                    {consequence && (
                      <span className="text-text-muted"> — {consequence}</span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
