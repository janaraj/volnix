import { useEffect, useMemo, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { ArrowDownToLine } from 'lucide-react';
import type { WorldEvent } from '@/types/domain';
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
  world: 'Agent action',
  'policy.hold': 'Policy hold',
  'policy.block': 'Policy block',
  'policy.escalate': 'Policy escalate',
  'policy.flag': 'Policy flag',
  'permission.denied': 'Permission denied',
  'budget.deduction': 'Budget deduction',
  'budget.warning': 'Budget warning',
  'budget.exhausted': 'Budget exhausted',
  'capability.gap': 'Capability gap',
  animator: 'Animator event',
};

const INTERNAL_ACTORS = new Set([
  'world_compiler',
  'animator',
  'system',
  'policy',
  'budget',
  'state',
  'permission',
  'responder',
]);

export function EventFeed({ events, selectedEventId, onSelectEvent, onSelectActor }: EventFeedProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [hideInternal, setHideInternal] = useState(true);
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
    const ids = new Set(events.filter((e) => e.service_id).map((e) => e.service_id ?? ''));
    return Array.from(ids).sort();
  }, [events]);

  const filteredEvents = useMemo(() => {
    return events.filter((e) => {
      if (hideInternal && INTERNAL_ACTORS.has(e.actor_id)) return false;
      if (outcomeFilter && (e.outcome ?? '') !== outcomeFilter) return false;
      if (eventTypeFilter && e.event_type !== eventTypeFilter) return false;
      if (actorFilter && e.actor_id !== actorFilter) return false;
      if (serviceFilter && (e.service_id ?? '') !== serviceFilter) return false;
      return true;
    });
  }, [events, hideInternal, outcomeFilter, eventTypeFilter, actorFilter, serviceFilter]);

  const virtualizer = useVirtualizer({
    count: filteredEvents.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 80,
    overscan: 10,
  });

  useEffect(() => {
    if (autoScroll && filteredEvents.length > 0) {
      virtualizer.scrollToIndex(0, { align: 'start' });
    }
  }, [filteredEvents.length, autoScroll, virtualizer]);

  function handleScroll() {
    if (!scrollRef.current) return;
    const { scrollTop } = scrollRef.current;
    const isAtTop = scrollTop < 32;
    setAutoScroll(isAtTop);
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
              virtualizer.scrollToIndex(0, { align: 'start' });
            }
          }}
          className={cn(
            'rounded p-1 transition-colors hover:bg-bg-elevated',
            autoScroll ? 'text-info' : 'text-text-muted',
          )}
          title={autoScroll ? 'Auto-scroll on' : 'Auto-scroll off'}
          aria-label={autoScroll ? 'Auto-scroll on' : 'Auto-scroll off'}
        >
          <ArrowDownToLine size={16} />
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2 pb-2">
        <label className="inline-flex items-center gap-1.5 text-xs text-text-secondary cursor-pointer select-none">
          <input
            type="checkbox"
            checked={!hideInternal}
            onChange={() => setHideInternal((v) => !v)}
            className="h-3.5 w-3.5 rounded border-border"
          />
          Show internal
        </label>
        <select
          aria-label="Filter by outcome"
          value={outcomeFilter}
          onChange={(e) => setOutcomeFilter(e.target.value in OUTCOME_FILTER_OPTIONS ? e.target.value : '')}
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
          onChange={(e) => setEventTypeFilter(e.target.value in EVENT_TYPE_FILTER_OPTIONS ? e.target.value : '')}
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
