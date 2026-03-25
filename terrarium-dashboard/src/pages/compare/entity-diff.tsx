import { ScoreBar } from '@/components/domain/score-bar';

interface ScoreComparisonBarsProps {
  metrics: Record<string, { values: Record<string, number> }>;
  labels: Record<string, string>;
  runIds: string[];
}

export function ScoreComparisonBars({ metrics, labels, runIds }: ScoreComparisonBarsProps) {
  const scoreMetrics = Object.entries(metrics).filter(([, m]) =>
    Object.values(m.values).every((v) => typeof v === 'number' && v >= 0 && v <= 100),
  );
  if (scoreMetrics.length === 0) return null;
  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium text-text-secondary">Score Comparison</h3>
      <div className="space-y-6">
        {scoreMetrics.map(([name, metric]) => (
          <div key={name} className="space-y-2">
            <h4 className="text-xs font-medium text-text-muted">{name.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}</h4>
            {runIds.map((id) => {
              const value = metric.values[id];
              if (typeof value !== 'number') return null;
              return <ScoreBar key={id} value={value / 100} label={labels[id] ?? id} />;
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
