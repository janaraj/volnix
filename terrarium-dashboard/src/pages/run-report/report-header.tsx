import { Link } from 'react-router';
import { ChevronRight } from 'lucide-react';
import type { Run } from '@/types/domain';
import { RunStatusBadge } from '@/components/domain/run-status-badge';
import { ScoreGrade } from '@/components/domain/score-grade';
import { ScoreBar } from '@/components/domain/score-bar';

interface ReportHeaderProps {
  run: Run;
}

const BADGE_KEYS = ['reality_preset', 'behavior', 'fidelity', 'mode'] as const;

function getBadgeValue(run: Run, key: string): string {
  const value = run[key as keyof Run];
  if (value == null) return 'none';
  return String(value);
}

export function ReportHeader({ run }: ReportHeaderProps) {
  const tagName = run.tags.length > 0 ? run.tags[0] : run.id;
  const hasScore = run.governance_score != null;

  return (
    <div className="mb-6">
      {/* Breadcrumb */}
      <div className="mb-3 flex items-center gap-1 text-sm text-text-muted">
        <Link to="/" className="hover:text-text-primary transition-colors">Terrarium</Link>
        <ChevronRight size={14} />
        <span className="text-text-secondary">{tagName}</span>
        <ChevronRight size={14} />
        <span className="text-text-secondary">Report</span>
      </div>

      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3">
            <h1 className="truncate text-2xl font-semibold">{run.world_name}</h1>
            <RunStatusBadge status={run.status} />
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {BADGE_KEYS.map((key) => (
              <span
                key={key}
                className="rounded-full bg-bg-elevated px-2 py-0.5 text-xs text-text-secondary"
              >
                {getBadgeValue(run, key)}
              </span>
            ))}
            {run.seed != null && (
              <span className="rounded-full bg-bg-elevated px-2 py-0.5 font-mono text-xs text-text-muted">
                seed: {run.seed}
              </span>
            )}
          </div>
        </div>
        {hasScore && (
          <div className="flex shrink-0 flex-col items-end gap-2">
            <ScoreGrade score={run.governance_score!} />
            <div className="w-40">
              <ScoreBar value={run.governance_score!} label="Governance" />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
