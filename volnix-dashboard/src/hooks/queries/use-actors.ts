import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/constants/query-keys';
import { useApiClient } from '@/providers/services-provider';

export function useActor(runId: string, actorId: string) {
  const api = useApiClient();
  return useQuery({
    queryKey: queryKeys.runs.actor(runId, actorId),
    queryFn: () => api.getActor(runId, actorId),
    enabled: !!actorId,
  });
}
