import { useNavigate } from 'react-router';
import { ExternalLink, Radio, Users, Zap, Layers, Clock, Shield } from 'lucide-react';
import { cn } from '@/lib/cn';
import { formatRelativeTime, truncateId, capitalize } from '@/lib/formatters';
import { runReportPath, liveConsolePath } from '@/constants/routes';
import { RunStatusBadge } from '@/components/domain/run-status-badge';
import { ScoreBar } from '@/components/domain/score-bar';
import type { Run } from '@/types/domain';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface RunCardProps {
  run: Run;
  selected: boolean;
  onToggleSelect: (id: string) => void;
}

// ---------------------------------------------------------------------------
// Dimension badge helper
// ---------------------------------------------------------------------------

const DIMENSION_COLORS: Record<string, string> = {
  blue: 'border-info/40 text-info',
  amber: 'border-warning/40 text-warning',
  purple: 'border-accent/40 text-accent',
  green: 'border-success/40 text-success',
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

export function RunCard({ run, selected, onToggleSelect }: RunCardProps) {
  const navigate = useNavigate();

  const tagName = run.tag || truncateId(run.run_id);

  const handlePrimaryAction = () => {
    if (run.status === 'running') {
      navigate(liveConsolePath(run.run_id));
    } else {
      navigate(runReportPath(run.run_id));
    }
  };

  const duration =
    run.started_at && run.completed_at
      ? `${Math.round((new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()) / 1000)}s`
      : run.started_at
        ? 'running...'
        : '--';

  const actorCount = run.actor_count ?? 0;
  const eventCount = run.event_count ?? 0;
  const serviceCount = (run.services ?? []).length;
  const hasAnyStats = actorCount > 0 || eventCount > 0 || serviceCount > 0;

  return (
    <div
      className={cn(
        'card elevate-on-hover p-0 overflow-hidden',
        run.status === 'running' && 'ring-1 ring-info/30',
        run.status === 'failed' && 'ring-1 ring-error/20',
        selected && '!border-accent/50 ring-1 ring-accent/30',
      )}
    >
      {/* Section 1: Header — checkbox, status, tag, action */}
      <div className="px-5 pt-4 pb-2 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            checked={selected}
            onChange={() => onToggleSelect(run.run_id)}
            className="h-4 w-4 rounded border-border-default"
          />
          <RunStatusBadge status={run.status} />
          <span className="font-mono text-sm font-medium text-text-primary">{tagName}</span>
        </div>

        <div className="flex items-center gap-2">
          {run.status === 'running' ? (
            <button
              type="button"
              onClick={() => navigate(liveConsolePath(run.run_id))}
              className="inline-flex items-center gap-1.5 rounded-lg bg-info/15 px-2.5 py-1 text-xs font-medium text-info shadow-sm transition-all duration-200 hover:bg-info/25"
            >
              <Radio size={12} />
              Watch Live
            </button>
          ) : (
            <button
              type="button"
              onClick={handlePrimaryAction}
              className="inline-flex items-center gap-1.5 rounded-lg bg-bg-elevated px-2.5 py-1 text-xs font-medium text-text-secondary shadow-xs transition-all duration-200 hover:text-text-primary"
            >
              <ExternalLink size={12} />
              View
            </button>
          )}
        </div>
      </div>

      {/* Section 2: Body — world name + dimension badges */}
      <div className="px-5 pb-3">
        <p className="mb-2 text-sm text-text-secondary">{capitalize(run.world_def.name)}</p>
        <div className="flex flex-wrap gap-1.5">
          {run.reality_preset && <DimensionBadge value={run.reality_preset} color="blue" />}
          {run.config_snapshot?.behavior && <DimensionBadge value={run.config_snapshot.behavior} color="amber" />}
          {run.fidelity_mode && <DimensionBadge value={run.fidelity_mode} color="green" />}
          {run.mode && <DimensionBadge value={run.mode} color="purple" />}
        </div>

        {/* Conditional score bar */}
        {run.governance_score != null && (
          <div className="mt-2 flex items-center gap-2">
            <Shield size={12} className="shrink-0 text-text-muted" />
            <div className="flex-1">
              <ScoreBar value={run.governance_score} label="Governance" />
            </div>
          </div>
        )}
      </div>

      {/* Section 3: Footer — stats (non-zero only) + time */}
      <div className="border-t border-border/20 bg-bg-elevated/30 px-5 py-2.5 flex items-center justify-between text-xs text-text-muted">
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {hasAnyStats && (
            <>
              {actorCount > 0 && (
                <span className="inline-flex items-center gap-1"><Users size={11} /> {actorCount} actors</span>
              )}
              {eventCount > 0 && (
                <span className="inline-flex items-center gap-1"><Zap size={11} /> {eventCount} events</span>
              )}
              {serviceCount > 0 && (
                <span className="inline-flex items-center gap-1"><Layers size={11} /> {serviceCount} services</span>
              )}
            </>
          )}
          <span className="inline-flex items-center gap-1"><Clock size={11} /> {duration}</span>
        </div>
        <span>{formatRelativeTime(run.created_at)}</span>
      </div>
    </div>
  );
}
