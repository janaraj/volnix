import { useUrlState } from './use-url-state';

export function useUrlTabs(defaultTab: string) {
  const [state, setState] = useUrlState({ tab: defaultTab });
  return [state.tab, (tab: string) => setState({ tab })] as const;
}
