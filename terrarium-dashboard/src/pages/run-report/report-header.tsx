import { Link } from 'react-router';
import { ChevronRight } from 'lucide-react';
import { cn } from '@/lib/cn';
import type { Run } from '@/types/domain';
import { RunStatusBadge } from '@/components/domain/run-status-badge';
import { ScoreGrade } from '@/components/domain/score-grade';
import { ScoreBar } from '@/components/domain/score-bar';
import { capitalize } from '@/lib/formatters';

interface ReportHeaderProps {
  run: Run;
}

// ---------------------------------------------------------------------------
// Dimension badge helper (color-coded)
// ---------------------------------------------------------------------------

const DIMENSION_COLORS: Record<string, string> = {
  blue: 'bg-info/10 text-info border-info/20',
  amber: 'bg-warning/10 text-warning border-warning/20',
  purple: 'bg-accent/10 text-accent border-accent/20',
  green: 'bg-success/10 text-success border-success/20',
};

function DimensionBadge({ value, color }: { value: string; color: string }) {
  return (
    <span className={cn('inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-medium', DIMENSION_COLORS[color] ?? DIMENSION_COLORS.blue)}>
      {capitalize(value)}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

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
            {run.reality_preset && <DimensionBadge value={run.reality_preset} color="blue" />}
            {run.config_snapshot?.behavior && <DimensionBadge value={run.config_snapshot.behavior} color="amber" />}
            {run.fidelity_mode && <DimensionBadge value={run.fidelity_mode} color="green" />}
            {run.mode && <DimensionBadge value={run.mode} color="purple" />}
            {run.config_snapshot?.seed != null && (
              <span className="rounded-md border border-border/30 bg-bg-elevated/60 px-2 py-0.5 font-mono text-xs text-text-muted">
                seed: {run.config_snapshot?.seed}
              </span>
            )}
          </div>
        </div>
        {hasScore ? (
          <div className="flex shrink-0 flex-col items-end gap-2 rounded-xl border border-border/30 bg-bg-surface p-3 shadow-sm">
            <ScoreGrade score={run.governance_score!} />
            <div className="w-40">
              <ScoreBar value={run.governance_score!} label="Governance" />
            </div>
          </div>
        ) : (
          <span className="text-text-muted text-sm">Score: —</span>
        )}
      </div>
    </div>
  );
}
