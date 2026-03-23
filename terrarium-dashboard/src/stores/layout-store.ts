import { create } from 'zustand';

interface LayoutStore {
  sidebarCollapsed: boolean;
  livePanelSizes: [number, number, number];
  toggleSidebar: () => void;
  setPanelSizes: (sizes: [number, number, number]) => void;
}

export const useLayoutStore = create<LayoutStore>((set) => ({
  sidebarCollapsed: false,
  livePanelSizes: [25, 50, 25] as [number, number, number],

  toggleSidebar: () =>
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

  setPanelSizes: (sizes: [number, number, number]) =>
    set({ livePanelSizes: sizes }),
}));
