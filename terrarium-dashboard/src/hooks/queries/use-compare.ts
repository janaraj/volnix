import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/constants/query-keys';
import { STALE_TIME_COMPARISON } from '@/constants/defaults';
import { useApiClient } from '@/providers/services-provider';

export function useComparison(runIds: string[]) {
  const api = useApiClient();
  return useQuery({
    queryKey: queryKeys.compare.detail(runIds),
    queryFn: () => api.getComparison(runIds),
    staleTime: STALE_TIME_COMPARISON,
    enabled: runIds.length >= 2,
  });
}
