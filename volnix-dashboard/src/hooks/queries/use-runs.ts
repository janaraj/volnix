import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/constants/query-keys';
import { STALE_TIME_RUNS_LIST, STALE_TIME_RUN_DETAIL } from '@/constants/defaults';
import { useApiClient } from '@/providers/services-provider';
import type { RunListParams } from '@/types/api';

interface UseRunsOptions {
  refetchInterval?: number | false | ((query: { state: { data: unknown } }) => number | false | undefined);
}

export function useRuns(params?: RunListParams, options?: UseRunsOptions) {
  const api = useApiClient();
  return useQuery({
    queryKey: queryKeys.runs.list(params),
    queryFn: () => api.getRuns(params),
    staleTime: STALE_TIME_RUNS_LIST,
    ...(options?.refetchInterval !== undefined && { refetchInterval: options.refetchInterval }),
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
