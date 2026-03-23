import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/constants/query-keys';
import { STALE_TIME_RUNS_LIST, STALE_TIME_RUN_DETAIL } from '@/constants/defaults';
import { useApiClient } from '@/providers/services-provider';
import type { RunListParams } from '@/types/api';

export function useRuns(params?: RunListParams) {
  const api = useApiClient();
  return useQuery({
    queryKey: queryKeys.runs.list(params),
    queryFn: () => api.getRuns(params),
    staleTime: STALE_TIME_RUNS_LIST,
  });
}

export function useRun(id: string) {
  const api = useApiClient();
  return useQuery({
    queryKey: queryKeys.runs.detail(id),
    queryFn: () => api.getRun(id),
    staleTime: STALE_TIME_RUN_DETAIL,
  });
}
