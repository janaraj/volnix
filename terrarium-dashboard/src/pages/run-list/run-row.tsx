import { useNavigate } from 'react-router';
import { ExternalLink, Radio } from 'lucide-react';
import { cn } from '@/lib/cn';
import { formatRelativeTime, truncateId } from '@/lib/formatters';
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
// Badge helper
// ---------------------------------------------------------------------------

const BADGE_ITEMS: Array<{ label: string; value: (r: Run) => string | number | null | undefined }> = [
  { label: 'Preset', value: (r) => r.reality_preset },
  { label: 'Behavior', value: (r) => r.config_snapshot?.behavior },
  { label: 'Fidelity', value: (r) => r.fidelity_mode },
  { label: 'Mode', value: (r) => r.mode },
  { label: 'Seed', value: (r) => r.config_snapshot?.seed },
];

function BadgeRow({ run }: { run: Run }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {BADGE_ITEMS.map(({ label, value }) => {
        const v = value(run);
        if (v === null || v === undefined) return null;
        return (
          <span key={label} className="rounded bg-bg-elevated px-1.5 py-0.5 text-[11px] text-text-secondary">
            {label}: {String(v)}
          </span>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stats helper
// ---------------------------------------------------------------------------

function StatsRow({ run }: { run: Run }) {
  const duration =
    run.started_at && run.completed_at
      ? `${Math.round((new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()) / 1000)}s`
      : run.started_at
        ? 'running...'
        : '--';

  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
      <span>{run.actor_count ?? 0} actors</span>
      <span>{run.event_count ?? 0} events</span>
      <span>{(run.services ?? []).length} entities</span>
      <span>{duration}</span>
      <span>{formatRelativeTime(run.created_at)}</span>
    </div>
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

  return (
    <div
      className={cn(
        'rounded-lg border bg-bg-surface p-4 transition-colors',
        selected ? 'border-info' : 'border-border-default',
      )}
    >
      {/* Top row: checkbox, status, tag, actions */}
      <div className="mb-3 flex items-center justify-between">
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
              className="inline-flex items-center gap-1.5 rounded bg-info/15 px-2.5 py-1 text-xs font-medium text-info hover:bg-info/25"
            >
              <Radio size={12} />
              Watch Live
            </button>
          ) : (
            <button
              type="button"
              onClick={handlePrimaryAction}
              className="inline-flex items-center gap-1.5 rounded bg-bg-elevated px-2.5 py-1 text-xs font-medium text-text-secondary hover:text-text-primary"
            >
              <ExternalLink size={12} />
              View
            </button>
          )}
        </div>
      </div>

      {/* World name */}
      <p className="mb-2 text-sm text-text-secondary">{run.world_def.name}</p>

      {/* Badge row */}
      <div className="mb-2">
        <BadgeRow run={run} />
      </div>

      {/* Conditional score bar */}
      {run.governance_score != null && (
        <div className="mb-2">
          <ScoreBar value={run.governance_score} label="Governance" />
        </div>
      )}

      {/* Stats row */}
      <StatsRow run={run} />
    </div>
  );
}
