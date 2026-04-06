import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/constants/query-keys';
import { STALE_TIME_EVENTS } from '@/constants/defaults';
import { useApiClient } from '@/providers/services-provider';
import type { EventFilterParams } from '@/types/api';

export function useRunEvents(runId: string, params?: EventFilterParams) {
  const api = useApiClient();
  return useQuery({
    queryKey: queryKeys.runs.events(runId, params),
    queryFn: () => api.getRunEvents(runId, params),
    staleTime: STALE_TIME_EVENTS,
  });
}

export function useRunEvent(runId: string, eventId: string) {
  const api = useApiClient();
  return useQuery({
    queryKey: queryKeys.runs.event(runId, eventId),
    queryFn: () => api.getRunEvent(runId, eventId),
    staleTime: STALE_TIME_EVENTS,
    enabled: !!eventId,
  });
}
