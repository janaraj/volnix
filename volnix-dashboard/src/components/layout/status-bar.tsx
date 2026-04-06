import type { ConnectionStatus } from '@/types/ui';
import { cn } from '@/lib/cn';

interface StatusBarProps {
  connectionStatus?: ConnectionStatus;
}

const STATUS_CONFIG: Record<ConnectionStatus, { dot: string; label: string }> = {
  connected: { dot: 'bg-success', label: 'Connected' },
  connecting: { dot: 'bg-info animate-pulse', label: 'Connecting...' },
  disconnected: { dot: 'bg-neutral', label: 'Disconnected' },
  reconnecting: { dot: 'bg-warning animate-pulse', label: 'Reconnecting...' },
};

export function StatusBar({ connectionStatus = 'disconnected' }: StatusBarProps) {
  const config = STATUS_CONFIG[connectionStatus];
  return (
    <div className="flex h-9 items-center justify-between border-t border-border/30 bg-gradient-to-r from-bg-surface to-bg-base px-4 text-xs text-text-muted">
      <span className="font-medium tracking-wide">Volnix Dashboard</span>
      <span className="flex items-center gap-2">
        <span className={cn('h-2 w-2 rounded-full ring-2 ring-current/20', config.dot)} />
        {config.label}
      </span>
    </div>
  );
}
