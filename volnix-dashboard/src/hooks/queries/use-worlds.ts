import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/constants/query-keys';
import { STALE_TIME_WORLDS } from '@/constants/defaults';
import { useApiClient } from '@/providers/services-provider';
import type { WorldsListResponse } from '@/types/api';

export function useWorlds() {
  const api = useApiClient();
  return useQuery({
    queryKey: queryKeys.worlds.list(),
    queryFn: () => api.getWorlds(),
    staleTime: STALE_TIME_WORLDS,
    refetchInterval: (query) => {
      const data = query.state.data as WorldsListResponse | undefined;
      const hasCreating = data?.worlds.some((w) => w.status === 'created') ?? false;
      return hasCreating ? 3_000 : false;
    },
  });
}
