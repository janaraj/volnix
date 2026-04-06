import { useQuery } from '@tanstack/react-query';
import { useApiClient } from '@/providers/services-provider';

export function useDeliverable(runId: string) {
  const api = useApiClient();
  return useQuery({
    queryKey: ['deliverable', runId],
    queryFn: () => api.getDeliverable(runId),
    retry: false,
  });
}
