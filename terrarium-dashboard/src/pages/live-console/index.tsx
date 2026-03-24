import { useState } from 'react';
import { useParams } from 'react-router';
import { useRun } from '@/hooks/queries/use-runs';
import { useRunEvents } from '@/hooks/queries/use-events';
import { useLiveEvents } from '@/hooks/use-live-events';
import { QueryGuard } from '@/components/feedback/query-guard';
import { PanelLayout } from '@/components/layout/panel-layout';
import { RunHeaderBar } from '@/pages/live-console/run-header-bar';
import { TransitionBanner } from '@/pages/live-console/transition-banner';
import { EventFeed } from '@/pages/live-console/event-feed';
import { ContextView } from '@/pages/live-console/context-view';
import { Inspector } from '@/pages/live-console/inspector';

export function LiveConsolePage() {
  const { id } = useParams<{ id: string }>();
  const runId = id!;

  const connectionStatus = useLiveEvents(runId);
  const runQuery = useRun(runId);
  const eventsQuery = useRunEvents(runId);

  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [selectedActorId, setSelectedActorId] = useState<string | null>(null);

  function handleSelectEvent(eventId: string) {
    setSelectedEventId(eventId);
    const events = eventsQuery.data?.items ?? [];
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

  return (
    <QueryGuard query={runQuery}>
      {(run) => {
        const events = eventsQuery.data?.items ?? [];
        const eventCount = events.length;

        return (
          <div className="flex h-full flex-col">
            <RunHeaderBar
              run={run}
              connectionStatus={connectionStatus}
              eventCount={eventCount}
            />
            <TransitionBanner
              runId={runId}
              visible={run.status === 'completed'}
            />
            <div className="min-h-0 flex-1">
              <PanelLayout
                left={
                  <EventFeed
                    events={events}
                    selectedEventId={selectedEventId}
                    onSelectEvent={handleSelectEvent}
                    onSelectActor={handleSelectActor}
                  />
                }
                center={
                  <ContextView
                    runId={runId}
                    run={run}
                    selectedEventId={selectedEventId}
                    selectedActorId={selectedActorId}
                    eventCount={eventCount}
                    onSelectEvent={handleSelectEvent}
                    onClearSelection={handleClearSelection}
                  />
                }
                right={
                  <Inspector
                    runId={runId}
                    selectedActorId={selectedActorId}
                    run={run}
                  />
                }
              />
            </div>
          </div>
        );
      }}
    </QueryGuard>
  );
}
