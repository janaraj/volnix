import type { WorldEvent } from '@/types/domain';
import { OutcomeIcon } from '@/components/domain/outcome-icon';
import { TimestampCell } from '@/components/domain/timestamp-cell';
import { eventTypeToColorClass } from '@/lib/classifiers';
import { formatTick } from '@/lib/formatters';
import { cn } from '@/lib/cn';

interface EventFeedItemProps {
  event: WorldEvent;
  isSelected: boolean;
  onSelect: (eventId: string) => void;
  onSelectActor: (actorId: string) => void;
}

export function EventFeedItem({ event, isSelected, onSelect, onSelectActor }: EventFeedItemProps) {
  const isBlocked = event.outcome !== 'success' && event.outcome != null;

  return (
    <button
      type="button"
      onClick={() => onSelect(event.event_id ?? '')}
      className={cn(
        'w-full rounded px-2 py-1.5 text-left transition-colors hover:bg-bg-elevated animate-slide-in',
        isSelected && 'bg-bg-elevated border border-border',
      )}
    >
      {/* Line 1: timestamp + outcome icon */}
      <div className="flex items-center gap-1.5">
        <TimestampCell iso={event.timestamp?.wall_time ?? ''} />
        <OutcomeIcon outcome={event.outcome ?? 'success'} size={12} />
        {(event.timestamp?.tick ?? 0) > 0 && (
          <span className="font-mono text-[10px] text-text-muted">{formatTick(event.timestamp!.tick)}</span>
        )}
      </div>

      {/* Line 2: actor → action → outcome (narrative) */}
      <div className="mt-0.5 flex items-center gap-1 text-xs">
        {event.event_type?.startsWith('world.') ? (
          <>
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => { e.stopPropagation(); onSelectActor(event.actor_id); }}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.stopPropagation(); onSelectActor(event.actor_id); } }}
              className="text-info hover:underline truncate max-w-[140px]"
            >
              {event.actor_id}
            </span>
            <span className="text-text-muted">&rarr;</span>
            <span className="font-mono text-text-primary truncate">{event.action ?? event.event_type}</span>
          </>
        ) : event.event_type?.startsWith('budget.') ? (
          <>
            <span className={cn('font-mono truncate', eventTypeToColorClass(event.event_type ?? ''))}>{event.event_type}</span>
            <span className="text-text-muted">&middot;</span>
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => { e.stopPropagation(); onSelectActor(event.actor_id); }}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.stopPropagation(); onSelectActor(event.actor_id); } }}
              className="text-info hover:underline truncate max-w-[140px]"
            >
              {event.actor_id}
            </span>
            <span className="text-text-muted">&middot;</span>
            <span className="font-mono text-text-muted truncate">-{event.amount ?? event.budget_delta ?? 0} {event.budget_type ?? 'api_calls'}</span>
          </>
        ) : event.event_type?.startsWith('policy.') ? (
          <>
            <span className={cn('font-mono truncate', eventTypeToColorClass(event.event_type ?? ''))}>{event.event_type}</span>
            <span className="text-text-muted">&middot;</span>
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => { e.stopPropagation(); onSelectActor(event.actor_id); }}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.stopPropagation(); onSelectActor(event.actor_id); } }}
              className="text-info hover:underline truncate max-w-[140px]"
            >
              {event.actor_id}
            </span>
            <span className="text-text-muted">&middot;</span>
            <span className="font-mono text-text-muted truncate">{event.action} on {event.service_id}</span>
          </>
        ) : (
          <>
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => { e.stopPropagation(); onSelectActor(event.actor_id); }}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.stopPropagation(); onSelectActor(event.actor_id); } }}
              className="text-info hover:underline truncate max-w-[140px]"
            >
              {event.actor_id}
            </span>
            <span className="text-text-muted">&rarr;</span>
            <span className="font-mono text-text-primary truncate">{event.event_type}</span>
          </>
        )}
        {isBlocked && (
          <>
            <span className="text-text-muted">&rarr;</span>
            <span className="text-error text-[10px] uppercase font-medium">{event.outcome}</span>
          </>
        )}
      </div>

      {/* Line 3: policy detail if blocked */}
      {event.policy_hit && (
        <div className="mt-0.5 text-[10px] text-warning pl-2 border-l border-warning/30">
          {event.policy_hit.enforcement}: {event.policy_hit.policy_name}
        </div>
      )}
    </button>
  );
}
