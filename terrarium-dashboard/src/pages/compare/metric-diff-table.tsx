import { findBestValue } from '@/lib/comparison';
import { cn } from '@/lib/cn';

interface MetricDiffTableProps {
  metrics: Record<string, { values: Record<string, number>; deltas: Record<string, number> }>;
  labels: Record<string, string>;
  runIds: string[];
}

function formatMetricName(name: string): string {
  return name.split('_').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

export function MetricDiffTable({ metrics, labels, runIds }: MetricDiffTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-bg-elevated text-left text-text-secondary">
            <th className="py-2 pr-4 font-medium">Metric</th>
            {runIds.map((id) => (
              <th key={id} className="py-2 pr-4 font-medium">{labels[id] ?? id}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Object.entries(metrics).map(([name, metric]) => {
            const bestId = findBestValue(metric.values);
            return (
              <tr key={name} className="border-b border-bg-elevated">
                <td className="py-2 pr-4 text-text-secondary">{formatMetricName(name)}</td>
                {runIds.map((id) => {
                  const value = metric.values[id];
                  const isBest = bestId === id;
                  return (
                    <td key={id} className={cn('py-2 pr-4 font-mono', isBest && 'text-success font-medium')}>
                      {value != null ? String(value) : '\u2014'}
                      {isBest && <span className="ml-1 text-xs">\u2713best</span>}
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
