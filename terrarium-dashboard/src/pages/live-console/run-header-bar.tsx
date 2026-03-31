import { useState } from 'react';
import { Link } from 'react-router';
import { ChevronRight, CheckCircle2 } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import type { Run } from '@/types/domain';
import type { ConnectionStatus } from '@/types/ui';
import { RunStatusBadge } from '@/components/domain/run-status-badge';
import { useApiClient } from '@/providers/services-provider';
import { queryKeys } from '@/constants/query-keys';
import { cn } from '@/lib/cn';
import { capitalize, formatTick } from '@/lib/formatters';

interface RunHeaderBarProps {
  run: Run;
  connectionStatus: ConnectionStatus;
  eventCount: number;
}

const STATUS_CONFIG: Record<ConnectionStatus, { dot: string; label: string }> = {
  connecting: { dot: 'bg-warning', label: 'Connecting' },
  connected: { dot: 'bg-success', label: 'Connected' },
  disconnected: { dot: 'bg-error', label: 'Disconnected' },
  reconnecting: { dot: 'bg-warning', label: 'Reconnecting' },
};

function CompleteRunButton({ runId }: { runId: string }) {
  const api = useApiClient();
  const queryClient = useQueryClient();
  const [completing, setCompleting] = useState(false);

  async function handleComplete() {
    setCompleting(true);
    try {
      await api.completeRun(runId);
    } catch {
      // Run may already be completed — that's fine
    }
    // Always refresh run detail so the UI updates
    await queryClient.invalidateQueries({ queryKey: queryKeys.runs.detail(runId) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.runs.events(runId) });
    setCompleting(false);
  }

  return (
    <button
      type="button"
      onClick={handleComplete}
      disabled={completing}
      className="inline-flex items-center gap-1.5 rounded-md border border-success/40 px-2.5 py-1 text-xs font-medium text-success transition-colors hover:bg-success/10 disabled:opacity-50"
    >
      <CheckCircle2 size={12} />
      {completing ? 'Completing...' : 'Complete Run'}
    </button>
  );
}

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
        <h1 className="truncate text-xl font-semibold">{capitalize(run.world_def.name)}</h1>
        <RunStatusBadge status={run.status} />
        <div className={cn(
          'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium',
          connectionStatus === 'connected' && 'bg-success/10 text-success border-success/20',
          connectionStatus === 'connecting' && 'bg-warning/10 text-warning border-warning/20',
          connectionStatus === 'disconnected' && 'bg-error/10 text-error border-error/20',
          connectionStatus === 'reconnecting' && 'bg-warning/10 text-warning border-warning/20',
        )}>
          <span className={cn('h-2 w-2 rounded-full', statusCfg.dot, connectionStatus === 'connected' && 'animate-pulse')} />
          {capitalize(statusCfg.label)}
        </div>
      </div>

      {/* Stats row + controls */}
      <div className="mt-2 flex items-center justify-between">
        <div className="flex items-center gap-4 text-xs text-text-secondary">
          <span>
            {(run.current_tick ?? 0) > 0
              ? <>Tick: <span className="font-mono">{formatTick(run.current_tick!)}</span></>
              : <span className="text-text-muted">Live</span>
            }
          </span>
          <span>
            Agents: <span className="font-mono">{run.actor_count ?? 0}</span>
          </span>
          <span>
            Events: <span className="font-mono">{eventCount}</span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          {run.status === 'running' && (
            <CompleteRunButton runId={run.run_id} />
          )}
        </div>
      </div>
    </div>
  );
}
