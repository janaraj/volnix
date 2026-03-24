import { useEffect, useMemo, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { ArrowDownToLine } from 'lucide-react';
import type { WorldEvent, EventType, Outcome } from '@/types/domain';
import { EventFeedItem } from '@/pages/live-console/event-feed-item';
import { EmptyState } from '@/components/feedback/empty-state';
import { cn } from '@/lib/cn';

interface EventFeedProps {
  events: WorldEvent[];
  selectedEventId: string | null;
  onSelectEvent: (eventId: string) => void;
  onSelectActor: (actorId: string) => void;
}

const OUTCOME_FILTER_OPTIONS: Record<string, string> = {
  '': 'All outcomes',
  success: 'Success',
  denied: 'Denied',
  held: 'Held',
  escalated: 'Escalated',
  error: 'Error',
  gap: 'Gap',
  flagged: 'Flagged',
};

const EVENT_TYPE_FILTER_OPTIONS: Record<string, string> = {
  '': 'All types',
  agent_action: 'Agent action',
  policy_hold: 'Policy hold',
  policy_block: 'Policy block',
  policy_escalate: 'Policy escalate',
  policy_flag: 'Policy flag',
  permission_denied: 'Permission denied',
  budget_deduction: 'Budget deduction',
  budget_warning: 'Budget warning',
  budget_exhausted: 'Budget exhausted',
  capability_gap: 'Capability gap',
  animator_event: 'Animator event',
  state_change: 'State change',
  side_effect: 'Side effect',
  system_event: 'System event',
};

export function EventFeed({ events, selectedEventId, onSelectEvent, onSelectActor }: EventFeedProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [outcomeFilter, setOutcomeFilter] = useState('');
  const [eventTypeFilter, setEventTypeFilter] = useState('');
  const [actorFilter, setActorFilter] = useState('');
  const [serviceFilter, setServiceFilter] = useState('');

  // Derive dynamic actor/service options from event data
  const actorOptions = useMemo(() => {
    const ids = new Set(events.map((e) => e.actor_id));
    return Array.from(ids).sort();
  }, [events]);

  const serviceOptions = useMemo(() => {
    const ids = new Set(events.filter((e) => e.service_id).map((e) => e.service_id!));
    return Array.from(ids).sort();
  }, [events]);

  const filteredEvents = useMemo(() => {
    return events.filter((e) => {
      if (outcomeFilter && e.outcome !== outcomeFilter) return false;
      if (eventTypeFilter && e.event_type !== eventTypeFilter) return false;
      if (actorFilter && e.actor_id !== actorFilter) return false;
      if (serviceFilter && e.service_id !== serviceFilter) return false;
      return true;
    });
  }, [events, outcomeFilter, eventTypeFilter, actorFilter, serviceFilter]);

  const virtualizer = useVirtualizer({
    count: filteredEvents.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 80,
    overscan: 10,
  });

  useEffect(() => {
    if (autoScroll && filteredEvents.length > 0) {
      virtualizer.scrollToIndex(filteredEvents.length - 1, { align: 'end' });
    }
  }, [filteredEvents.length, autoScroll, virtualizer]);

  function handleScroll() {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 32;
    setAutoScroll(isAtBottom);
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between pb-2">
        <h2 className="text-sm font-semibold text-text-primary">
          Event Feed ({filteredEvents.length})
        </h2>
        <button
          type="button"
          onClick={() => {
            setAutoScroll(true);
            if (filteredEvents.length > 0) {
              virtualizer.scrollToIndex(filteredEvents.length - 1, { align: 'end' });
            }
          }}
          className={cn(
            'rounded p-1 transition-colors hover:bg-bg-elevated',
            autoScroll ? 'text-info' : 'text-text-muted',
          )}
          title={autoScroll ? 'Auto-scroll on' : 'Auto-scroll off'}
        >
          <ArrowDownToLine size={16} />
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-2 pb-2">
        <select
          aria-label="Filter by outcome"
          value={outcomeFilter}
          onChange={(e) => setOutcomeFilter(e.target.value as Outcome | '')}
          className="rounded border border-border bg-bg-surface px-2 py-1 text-xs text-text-primary"
        >
          {Object.entries(OUTCOME_FILTER_OPTIONS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by event type"
          value={eventTypeFilter}
          onChange={(e) => setEventTypeFilter(e.target.value as EventType | '')}
          className="rounded border border-border bg-bg-surface px-2 py-1 text-xs text-text-primary"
        >
          {Object.entries(EVENT_TYPE_FILTER_OPTIONS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by actor"
          value={actorFilter}
          onChange={(e) => setActorFilter(e.target.value)}
          className="rounded border border-border bg-bg-surface px-2 py-1 text-xs text-text-primary"
        >
          <option value="">All actors</option>
          {actorOptions.map((id) => (
            <option key={id} value={id}>{id}</option>
          ))}
        </select>
        <select
          aria-label="Filter by service"
          value={serviceFilter}
          onChange={(e) => setServiceFilter(e.target.value)}
          className="rounded border border-border bg-bg-surface px-2 py-1 text-xs text-text-primary"
        >
          <option value="">All services</option>
          {serviceOptions.map((id) => (
            <option key={id} value={id}>{id}</option>
          ))}
        </select>
      </div>

      {/* Virtualized scrollable event list */}
      <div ref={scrollRef} onScroll={handleScroll} className="min-h-0 flex-1 overflow-auto">
        {filteredEvents.length === 0 ? (
          <EmptyState title="No events" description="Waiting for events..." />
        ) : (
          <div style={{ height: `${virtualizer.getTotalSize()}px`, position: 'relative' }}>
            {virtualizer.getVirtualItems().map((virtualItem) => {
              const event = filteredEvents[virtualItem.index];
              return (
                <div
                  key={virtualItem.key}
                  ref={virtualizer.measureElement}
                  data-index={virtualItem.index}
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    transform: `translateY(${virtualItem.start}px)`,
                  }}
                >
                  <EventFeedItem
                    event={event}
                    isSelected={selectedEventId === event.event_id}
                    onSelect={onSelectEvent}
                    onSelectActor={onSelectActor}
                  />
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
