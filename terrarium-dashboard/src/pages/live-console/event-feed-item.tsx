import type { WorldEvent } from '@/types/domain';
import { OutcomeIcon } from '@/components/domain/outcome-icon';
import { TimestampCell } from '@/components/domain/timestamp-cell';
import { formatTick } from '@/lib/formatters';
import { cn } from '@/lib/cn';

interface EventFeedItemProps {
  event: WorldEvent;
  isSelected: boolean;
  onSelect: (eventId: string) => void;
  onSelectActor: (actorId: string) => void;
}

export function EventFeedItem({ event, isSelected, onSelect, onSelectActor }: EventFeedItemProps) {
  const showDescription =
    event.policy_hit != null || (event.outcome !== 'success');

  return (
    <button
      type="button"
      onClick={() => onSelect(event.event_id ?? '')}
      className={cn(
        'w-full rounded px-3 py-2 text-left transition-colors hover:bg-bg-elevated',
        isSelected && 'bg-bg-elevated border border-border',
      )}
    >
      {/* Line 1: timestamp + outcome + tick */}
      <div className="flex items-center gap-2">
        <TimestampCell iso={event.timestamp?.wall_time ?? ''} />
        <OutcomeIcon outcome={event.outcome ?? 'success'} size={14} />
        {(event.timestamp?.tick ?? 0) > 0 && (
          <span className="font-mono text-xs text-text-muted">{formatTick(event.timestamp.tick)}</span>
        )}
      </div>

      {/* Line 2: actor name */}
      <div className="mt-1">
        <span
          role="button"
          tabIndex={0}
          onClick={(e) => {
            e.stopPropagation();
            onSelectActor(event.actor_id);
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.stopPropagation();
              onSelectActor(event.actor_id);
            }
          }}
          className="text-xs text-info hover:underline"
        >
          {event.actor_id}
        </span>
      </div>

      {/* Line 3: action name */}
      <div className="mt-0.5 font-mono text-xs text-text-primary">{event.action ?? event.event_type}</div>

      {/* Line 4: brief description (conditional) */}
      {showDescription && (
        <div className="mt-0.5 text-xs text-text-muted">
          {event.policy_hit
            ? `${event.policy_hit.enforcement ?? 'unknown'}: ${event.policy_hit.policy_name ?? ''}`
            : (event.outcome ?? '').toUpperCase()}
        </div>
      )}
    </button>
  );
}
