import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useWsManager } from '@/providers/services-provider';
import { queryKeys } from '@/constants/query-keys';
import type { WsMessage } from '@/types/ws';
import type { ConnectionStatus } from '@/types/ui';
import type { EventsListResponse, EntitiesListResponse } from '@/types/api';
import type { Run, Entity, AgentSummary } from '@/types/domain';

/**
 * Bridge between WebSocket live stream and TanStack Query cache.
 *
 * Dual-source pattern:
 * 1. On mount: REST backfill (GET /api/runs/:id/events) fetches events before WS connected
 * 2. WS stream appends new events, deduped by event_id
 * 3. On run_complete: invalidate queries → REST re-fetch confirms final state
 */
export function useLiveEvents(runId: string): ConnectionStatus {
  const ws = useWsManager();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');

  useEffect(() => {
    if (!runId) return;

    const unsubStatus = ws.subscribeStatus(setStatus);
    ws.connect(runId);

    const unsubMessages = ws.subscribe((message: WsMessage) => {
      switch (message.type) {
        case 'event': {
          // Append to ALL event caches for this run (prefix match covers filtered + unfiltered).
          // Dedup by event_id prevents duplicates from REST backfill + WS overlap.
          const newEvent = message.data;
          queryClient.setQueriesData<EventsListResponse>(
            { queryKey: ['runs', runId, 'events'] },
            (old) => {
              if (!old) return old;
              if (old.events.some((e) => e.event_id === newEvent.event_id)) return old;
              return { ...old, events: [...old.events, newEvent], total: old.total + 1 };
            },
          );
          break;
        }

        case 'status': {
          // Patch run detail cache with new tick — no refetch needed.
          // WS status ("running"/"paused") maps to RunStatus; "paused" is not a RunStatus
          // so we only update the tick and keep the run status unchanged unless it's "running".
          const wsStatus = message.data.status;
          queryClient.setQueryData<Run>(
            queryKeys.runs.detail(runId),
            (old) => {
              if (!old) return old;
              return {
                ...old,
                current_tick: message.data.tick,
                ...(wsStatus === 'running' ? { status: 'running' as const } : {}),
              };
            },
          );
          break;
        }

        case 'budget_update': {
          // Patch specific actor's budget in actor cache.
          const { actor_id, remaining, total, budget_type } = message.data;
          queryClient.setQueryData<AgentSummary>(
            queryKeys.runs.actor(runId, actor_id),
            (old) => {
              if (!old) return old;
              return {
                ...old,
                budget_remaining: { ...old.budget_remaining, [budget_type]: remaining },
                budget_total: { ...old.budget_total, [budget_type]: total },
              };
            },
          );
          break;
        }

        case 'entity_update': {
          // Patch specific entity detail cache.
          const update = message.data;
          queryClient.setQueryData<Entity>(
            queryKeys.runs.entity(runId, update.entity_id),
            (old) => {
              if (!old) return old;
              return {
                ...old,
                fields: { ...old.fields, ...update.fields },
                updated_at: new Date().toISOString(),
              };
            },
          );
          // Also patch entity list caches (prefix match).
          queryClient.setQueriesData<EntitiesListResponse>(
            { queryKey: ['runs', runId, 'entities'] },
            (old) => {
              if (!old) return old;
              return {
                ...old,
                entities: old.entities.map((e) =>
                  e.id === update.entity_id
                    ? { ...e, fields: { ...(e.fields ?? {}), ...update.fields }, updated_at: new Date().toISOString() }
                    : e,
                ),
              };
            },
          );
          break;
        }

        case 'run_complete':
          // Verify message belongs to current run before invalidating.
          if (message.data.run_id === runId) {
            queryClient.invalidateQueries({ queryKey: queryKeys.runs.detail(runId) });
            queryClient.invalidateQueries({ queryKey: queryKeys.runs.events(runId) });
          }
          break;
      }
    });

    return () => {
      unsubStatus();
      unsubMessages();
      ws.disconnect();
    };
  }, [runId, ws, queryClient]);

  return status;
}
