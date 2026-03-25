import { Link } from 'react-router';
import { ChevronRight } from 'lucide-react';
import type { Run } from '@/types/domain';
import { RunStatusBadge } from '@/components/domain/run-status-badge';
import { ScoreGrade } from '@/components/domain/score-grade';
import { ScoreBar } from '@/components/domain/score-bar';
import { capitalize } from '@/lib/formatters';

interface ReportHeaderProps {
  run: Run;
}

const BADGE_ITEMS: Array<{ label: string; value: (r: Run) => string | number | null | undefined }> = [
  { label: 'Preset', value: (r) => r.reality_preset },
  { label: 'Behavior', value: (r) => r.config_snapshot?.behavior },
  { label: 'Fidelity', value: (r) => r.fidelity_mode },
  { label: 'Mode', value: (r) => r.mode },
];

export function ReportHeader({ run }: ReportHeaderProps) {
  const tagName = run.tag || run.run_id;
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
            <h1 className="truncate text-2xl font-bold tracking-tight">{capitalize(run.world_def.name)}</h1>
            <RunStatusBadge status={run.status} />
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {BADGE_ITEMS.map(({ label, value }) => {
              const v = value(run);
              if (v === null || v === undefined) return null;
              return (
                <span
                  key={label}
                  className="rounded-md border border-border/30 bg-bg-elevated/60 px-2 py-0.5 text-xs text-text-secondary"
                >
                  {capitalize(String(v))}
                </span>
              );
            })}
            {run.config_snapshot?.seed != null && (
              <span className="rounded-md border border-border/30 bg-bg-elevated/60 px-2 py-0.5 font-mono text-xs text-text-muted">
                seed: {run.config_snapshot?.seed}
              </span>
            )}
          </div>
        </div>
        {hasScore && (
          <div className="flex shrink-0 flex-col items-end gap-2 rounded-xl border border-border/30 bg-bg-surface p-3 shadow-sm">
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
