import { eventTypeToColorClass } from '@/lib/classifiers';

interface EventTypeBadgeProps {
  eventType: string;
}

export function EventTypeBadge({ eventType }: EventTypeBadgeProps) {
  const display = eventType.replace(/_/g, ' ');
  return (
    <span className={`rounded bg-bg-elevated px-1.5 py-0.5 font-mono text-xs ${eventTypeToColorClass(eventType)}`}>
      {display}
    </span>
  );
}
