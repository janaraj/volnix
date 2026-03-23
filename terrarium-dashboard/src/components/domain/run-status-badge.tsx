import type { RunStatus } from '@/types/domain';
import { runStatusToColorClass } from '@/lib/classifiers';
import { cn } from '@/lib/cn';

interface RunStatusBadgeProps {
  status: RunStatus;
}

const STATUS_BG: Record<RunStatus, string> = {
  created: 'bg-neutral/15',
  running: 'bg-info/15',
  completed: 'bg-success/15',
  failed: 'bg-error/15',
  stopped: 'bg-warning/15',
};

export function RunStatusBadge({ status }: RunStatusBadgeProps) {
  return (
    <span className={cn(
      'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium',
      runStatusToColorClass(status),
      STATUS_BG[status] ?? 'bg-neutral/15',
    )}>
      <span className={cn('h-1.5 w-1.5 rounded-full bg-current', status === 'running' && 'animate-pulse')} />
      {status}
    </span>
  );
}
