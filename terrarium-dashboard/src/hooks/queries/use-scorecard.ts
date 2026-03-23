import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/constants/query-keys';
import { STALE_TIME_SCORECARD } from '@/constants/defaults';
import { useApiClient } from '@/providers/services-provider';

export function useScorecard(runId: string) {
  const api = useApiClient();
  return useQuery({
    queryKey: queryKeys.runs.scorecard(runId),
    queryFn: () => api.getScorecard(runId),
    staleTime: STALE_TIME_SCORECARD,
  });
}
