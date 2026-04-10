import { useState } from 'react';
import { useParams } from 'react-router';
import { useRun } from '@/hooks/queries/use-runs';
import { useRunEvents } from '@/hooks/queries/use-events';
import { useLiveEvents } from '@/hooks/use-live-events';
import { useKeyboard } from '@/hooks/use-keyboard';
import { QueryGuard } from '@/components/feedback/query-guard';
import { RunHeaderBar } from '@/pages/live-console/run-header-bar';
import { TransitionBanner } from '@/pages/live-console/transition-banner';
import { EventFeed } from '@/pages/live-console/event-feed';
import { ContextView } from '@/pages/live-console/context-view';
import { ChatView } from '@/pages/live-console/chat-view';
import { Inspector } from '@/pages/live-console/inspector';
import { ActivityTimeline } from '@/pages/live-console/activity-timeline';

export function LiveConsolePage() {
  const { id } = useParams<{ id: string }>();
  const runId = id!;

  const connectionStatus = useLiveEvents(runId);
  const runQuery = useRun(runId);
  const eventsQuery = useRunEvents(runId, { sort: 'desc', limit: 500 });

  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [selectedActorId, setSelectedActorId] = useState<string | null>(null);

  function handleSelectEvent(eventId: string) {
    setSelectedEventId(eventId);
    const events = eventsQuery.data?.events ?? [];
    const event = events.find((e) => e.event_id === eventId);
    if (event) {
      setSelectedActorId(event.actor_id);
    }
  }

  function handleSelectActor(actorId: string) {
    setSelectedActorId(actorId);
  }

  function handleClearSelection() {
    setSelectedEventId(null);
    setSelectedActorId(null);
  }

  const events = eventsQuery.data?.events ?? [];

  useKeyboard({
    Escape: () => handleClearSelection(),
    ArrowDown: () => {
      if (!selectedEventId && events.length > 0) {
        handleSelectEvent(events[0].event_id!);
      } else if (selectedEventId) {
        const idx = events.findIndex((e) => e.event_id === selectedEventId);
        if (idx < events.length - 1) handleSelectEvent(events[idx + 1].event_id!);
      }
    },
    ArrowUp: () => {
      if (selectedEventId) {
        const idx = events.findIndex((e) => e.event_id === selectedEventId);
        if (idx > 0) handleSelectEvent(events[idx - 1].event_id!);
      }
    },
  });

  return (
    <QueryGuard query={runQuery}>
      {(run) => {
        const eventCount = eventsQuery.data?.total ?? events.length;

        return (
          <div className="flex h-full flex-col">
            <RunHeaderBar
              run={run}
              connectionStatus={connectionStatus}
              eventCount={eventCount}
            />
            <TransitionBanner runId={runId} visible={run.status === 'completed'} />

            {/* Three-pane row: EventFeed (narrow) | Overview (narrow) | Chat (centerpiece, widest) */}
            <div className="min-h-0 flex-1 flex flex-col md:flex-row">
              {/* Left: Event feed */}
              <div className="min-w-0 overflow-auto bg-bg-surface p-4 border-b md:border-b-0 md:border-r border-border/30 md:w-[22%]">
                <EventFeed
                  events={events}
                  selectedEventId={selectedEventId}
                  onSelectEvent={handleSelectEvent}
                  onSelectActor={handleSelectActor}
                />
              </div>

              {/* Center: Context (Overview / EventDetail / AgentDetail) — narrower than before */}
              <div className="min-w-0 overflow-auto bg-bg-surface p-4 border-b md:border-b-0 md:border-r border-border/30 md:w-[26%]">
                <ContextView
                  runId={runId}
                  run={run}
                  selectedEventId={selectedEventId}
                  selectedActorId={selectedActorId}
                  eventCount={eventCount}
                  onSelectEvent={handleSelectEvent}
                  onClearSelection={handleClearSelection}
                />
              </div>

              {/* Right: Chat — widest, centerpiece. Contained in a boxed card. */}
              <div className="min-w-0 flex-1 bg-bg-surface p-4">
                <div className="flex h-full flex-col overflow-hidden rounded-xl border border-border/50 bg-bg-base shadow-lg">
                  <div className="flex-shrink-0 border-b border-border/40 bg-bg-surface/40 px-4 py-2.5">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-text-muted">
                      Chat
                    </span>
                  </div>
                  <div className="min-h-0 flex-1 overflow-hidden">
                    <ChatView events={events} onSelectActor={handleSelectActor} />
                  </div>
                </div>
              </div>
            </div>

            {/* Inspector strip — horizontal, at the bottom (above timeline) */}
            <div className="border-t border-border/30 bg-bg-surface max-h-[160px] overflow-auto">
              <Inspector
                runId={runId}
                selectedActorId={selectedActorId}
                run={run}
                events={events}
              />
            </div>

            <ActivityTimeline
              events={events}
              onJumpToTick={() => {
                // Jump-to-tick is visual-only; future: scroll event feed to tick
              }}
            />
          </div>
        );
      }}
    </QueryGuard>
  );
}
