import type { ComparisonMetric, Run } from '@/types/domain';
import { findBestValue } from '@/lib/comparison';
import { cn } from '@/lib/cn';

interface MetricDiffTableProps {
  metrics: ComparisonMetric[];
  runs: Run[];
}

export function MetricDiffTable({ metrics, runs }: MetricDiffTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-bg-elevated text-left text-text-secondary">
            <th className="py-2 pr-4 font-medium">Metric</th>
            {runs.map((run) => (
              <th key={run.id} className="py-2 pr-4 font-medium">
                {run.tags[0] ?? run.id}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metrics.map((metric) => {
            const numericValues: Record<string, number> = {};
            for (const [runId, val] of Object.entries(metric.values)) {
              if (typeof val === 'number') {
                numericValues[runId] = val;
              }
            }
            const bestId = findBestValue(numericValues);

            return (
              <tr key={metric.name} className="border-b border-bg-elevated">
                <td className="py-2 pr-4 text-text-secondary">{metric.name}</td>
                {runs.map((run) => {
                  const value = metric.values[run.id];
                  const isBest = bestId === run.id;
                  return (
                    <td
                      key={run.id}
                      className={cn(
                        'py-2 pr-4 font-mono',
                        isBest && 'text-success font-medium',
                      )}
                    >
                      {String(value ?? '—')}
                      {isBest && (
                        <span className="ml-1 text-xs">✓best</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
