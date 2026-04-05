import { formatRelativeTime } from '@/lib/formatters';
import { format, parseISO, isValid } from 'date-fns';

interface TimestampCellProps {
  iso: string;
}

export function TimestampCell({ iso }: TimestampCellProps) {
  if (!iso || typeof iso !== 'string') return null;
  const parsed = parseISO(iso);
  const fullTime = isValid(parsed) ? format(parsed, 'yyyy-MM-dd HH:mm:ss') : iso;
  return (
    <span className="font-mono text-xs text-text-muted" title={fullTime}>
      {formatRelativeTime(iso)}
    </span>
  );
}
