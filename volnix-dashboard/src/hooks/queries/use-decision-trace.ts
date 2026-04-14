import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/constants/query-keys';
import { STALE_TIME_TRACE } from '@/constants/defaults';
import { useApiClient } from '@/providers/services-provider';

export function useDecisionTrace(runId: string) {
  const api = useApiClient();
  return useQuery({
    queryKey: queryKeys.runs.trace(runId),
    queryFn: () => api.getDecisionTrace(runId),
    staleTime: STALE_TIME_TRACE,
  });
}
