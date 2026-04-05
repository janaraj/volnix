import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { Run } from '@/types/domain';
import { formatTick } from '@/lib/formatters';

interface DivergencePoint {
  tick: number;
  description: string;
  decisions: Record<string, string>;
  consequences: Record<string, string>;
}

interface DivergenceTimelineProps {
  points: DivergencePoint[];
  runs: Run[];
}

export function DivergenceTimeline({ points, runs }: DivergenceTimelineProps) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  if (points.length === 0) return null;

  const toggle = (idx: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  return (
    <div>
      <h2 className="mb-3 text-lg font-semibold">Divergence Points</h2>
      <div className="space-y-3">
        {points.map((point, idx) => {
          const isExpanded = expanded.has(idx);
          return (
            <div key={idx} className="rounded-lg border border-border bg-bg-surface">
              <button
                type="button"
                onClick={() => toggle(idx)}
                className="flex w-full items-center gap-2 px-4 py-3 text-left transition-colors hover:bg-bg-hover"
              >
                {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                <span className="font-mono text-xs text-text-muted">{formatTick(point.tick)}</span>
                <span className="text-sm font-medium text-text-primary">{point.description}</span>
              </button>
              {isExpanded && (
                <div className="border-t border-bg-elevated px-4 py-3 space-y-2">
                  {runs.map((run) => {
                    const decision = point.decisions[run.run_id];
                    const consequence = point.consequences[run.run_id];
                    if (!decision) return null;
                    return (
                      <div key={run.run_id} className="text-sm">
                        <span className="font-medium text-text-secondary">{run.tag || run.run_id}:</span>
                        <span className="ml-1 text-text-primary">{decision}</span>
                        {consequence && <span className="ml-1 text-text-muted">— {consequence}</span>}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
