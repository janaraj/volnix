import type { RunStatus } from '@/types/domain';
import type { LucideIcon } from 'lucide-react';
import { CheckCircle2, Loader2, XCircle, StopCircle, Circle } from 'lucide-react';
import { runStatusToColorClass } from '@/lib/classifiers';
import { capitalize } from '@/lib/formatters';
import { cn } from '@/lib/cn';

interface RunStatusBadgeProps {
  status: RunStatus;
}

const STATUS_ICONS: Record<RunStatus, LucideIcon> = {
  created: Circle,
  running: Loader2,
  completed: CheckCircle2,
  failed: XCircle,
  stopped: StopCircle,
};

const STATUS_STYLES: Record<RunStatus, string> = {
  created: 'bg-neutral/10 border-neutral/20',
  running: 'bg-info/10 border-info/20',
  completed: 'bg-success/10 border-success/20',
  failed: 'bg-error/10 border-error/20',
  stopped: 'bg-warning/10 border-warning/20',
};

export function RunStatusBadge({ status }: RunStatusBadgeProps) {
  const Icon = STATUS_ICONS[status];
  return (
    <span className={cn(
      'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold',
      runStatusToColorClass(status),
      STATUS_STYLES[status] ?? 'bg-neutral/10 border-neutral/20',
    )}>
      <Icon size={12} className={cn(status === 'running' && 'animate-spin')} />
      {capitalize(status)}
    </span>
  );
}
