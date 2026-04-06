import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/constants/query-keys';
import { useApiClient } from '@/providers/services-provider';

export function useCapabilityGaps(runId: string) {
  const api = useApiClient();
  return useQuery({
    queryKey: queryKeys.runs.gaps(runId),
    queryFn: () => api.getCapabilityGaps(runId),
    staleTime: Infinity,
  });
}
