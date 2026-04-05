import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/constants/query-keys';
import { STALE_TIME_ENTITIES } from '@/constants/defaults';
import { useApiClient } from '@/providers/services-provider';
import type { EntityFilterParams } from '@/types/api';

export function useEntities(runId: string, params?: EntityFilterParams) {
  const api = useApiClient();
  return useQuery({
    queryKey: queryKeys.runs.entities(runId, params),
    queryFn: () => api.getEntities(runId, params),
    staleTime: STALE_TIME_ENTITIES,
  });
}

export function useEntity(runId: string, entityId: string) {
  const api = useApiClient();
  return useQuery({
    queryKey: queryKeys.runs.entity(runId, entityId),
    queryFn: () => api.getEntity(runId, entityId),
    staleTime: STALE_TIME_ENTITIES,
    enabled: !!entityId,
  });
}
