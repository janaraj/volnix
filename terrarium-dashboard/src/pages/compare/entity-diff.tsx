import type { ComparisonMetric, Run } from '@/types/domain';
import { ScoreBar } from '@/components/domain/score-bar';

interface ScoreComparisonBarsProps {
  metrics: ComparisonMetric[];
  runs: Run[];
}

export function ScoreComparisonBars({ metrics, runs }: ScoreComparisonBarsProps) {
  const scoreMetrics = metrics.filter((metric) => {
    const values = Object.values(metric.values);
    return values.every(
      (v) => typeof v === 'number' && v >= 0 && v <= 100,
    );
  });

  if (scoreMetrics.length === 0) return null;

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium text-text-secondary">Score Comparison</h3>
      <div className="space-y-6">
        {scoreMetrics.map((metric) => (
          <div key={metric.name} className="space-y-2">
            <h4 className="text-xs font-medium text-text-muted">{metric.name}</h4>
            {runs.map((run) => {
              const value = metric.values[run.id];
              if (typeof value !== 'number') return null;
              return (
                <ScoreBar
                  key={run.id}
                  value={value / 100}
                  label={run.tags[0] ?? run.id}
                />
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
