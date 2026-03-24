import { describe, it, expect, beforeEach } from 'vitest';
import { useLayoutStore } from '@/stores/layout-store';

beforeEach(() => {
  useLayoutStore.setState({
    sidebarCollapsed: false,
    livePanelSizes: [25, 50, 25],
  });
});

describe('useLayoutStore', () => {
  it('starts with sidebar expanded', () => {
    expect(useLayoutStore.getState().sidebarCollapsed).toBe(false);
  });

  it('toggleSidebar flips collapsed state', () => {
    useLayoutStore.getState().toggleSidebar();
    expect(useLayoutStore.getState().sidebarCollapsed).toBe(true);
    useLayoutStore.getState().toggleSidebar();
    expect(useLayoutStore.getState().sidebarCollapsed).toBe(false);
  });

  it('setPanelSizes updates sizes', () => {
    useLayoutStore.getState().setPanelSizes([30, 40, 30]);
    expect(useLayoutStore.getState().livePanelSizes).toEqual([30, 40, 30]);
  });

  it('has correct default panel sizes', () => {
    expect(useLayoutStore.getState().livePanelSizes).toEqual([25, 50, 25]);
  });

  it('has persist config with storage name', () => {
    // Zustand persist stores config on the store itself
    const store = useLayoutStore as unknown as { persist: { getOptions: () => { name: string } } };
    expect(store.persist.getOptions().name).toBe('terrarium-layout');
  });
});
