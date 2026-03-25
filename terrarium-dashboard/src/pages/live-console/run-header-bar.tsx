import { Link } from 'react-router';
import { ChevronRight, Pause, Square } from 'lucide-react';
import type { Run } from '@/types/domain';
import type { ConnectionStatus } from '@/types/ui';
import { RunStatusBadge } from '@/components/domain/run-status-badge';
import { cn } from '@/lib/cn';
import { formatTick } from '@/lib/formatters';

interface RunHeaderBarProps {
  run: Run;
  connectionStatus: ConnectionStatus;
  eventCount: number;
}

const STATUS_CONFIG: Record<ConnectionStatus, { color: string; label: string }> = {
  connecting: { color: 'bg-warning', label: 'Connecting' },
  connected: { color: 'bg-success', label: 'Connected' },
  disconnected: { color: 'bg-error', label: 'Disconnected' },
  reconnecting: { color: 'bg-warning', label: 'Reconnecting' },
};

export function RunHeaderBar({ run, connectionStatus, eventCount }: RunHeaderBarProps) {
  const tagName = run.tag || run.run_id;
  const statusCfg = STATUS_CONFIG[connectionStatus];

  return (
    <div className="border-b border-border bg-bg-surface px-4 py-3">
      {/* Breadcrumb */}
      <div className="mb-2 flex items-center gap-1 text-sm text-text-muted">
        <Link to="/" className="transition-colors hover:text-text-primary">Terrarium</Link>
        <ChevronRight size={14} />
        <span className="text-text-secondary">{tagName}</span>
        <ChevronRight size={14} />
        <span className="text-text-secondary">Live</span>
      </div>

      {/* Title row */}
      <div className="flex items-center gap-3">
        <h1 className="truncate text-xl font-semibold">{run.world_def.name}</h1>
        <RunStatusBadge status={run.status} />
        <div className="flex items-center gap-1.5 text-xs text-text-muted">
          <span className={cn('inline-block h-2 w-2 rounded-full', statusCfg.color)} />
          {statusCfg.label}
        </div>
      </div>

      {/* Stats row + controls */}
      <div className="mt-2 flex items-center justify-between">
        <div className="flex items-center gap-4 text-xs text-text-secondary">
          <span>
            Tick: <span className="font-mono">{formatTick(run.current_tick ?? 0)}</span>
          </span>
          <span>
            Agents: <span className="font-mono">{run.actor_count ?? 0}</span>
          </span>
          <span>
            Events: <span className="font-mono">{eventCount}</span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled
            title="Not available in v1"
            className="rounded p-1 text-text-muted opacity-50"
          >
            <Pause size={16} />
          </button>
          <button
            type="button"
            disabled
            title="Not available in v1"
            className="rounded p-1 text-text-muted opacity-50"
          >
            <Square size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
