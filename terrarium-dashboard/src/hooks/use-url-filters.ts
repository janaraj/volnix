import { useUrlState } from './use-url-state';
import type { FilterState } from '@/types/ui';

const FILTER_DEFAULTS: FilterState & Record<string, string> = {
  actor_id: '',
  service_id: '',
  event_type: '',
  outcome: '',
};

export function useUrlFilters() {
  return useUrlState(FILTER_DEFAULTS);
}
