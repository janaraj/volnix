import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

interface LayoutStore {
  sidebarCollapsed: boolean;
  livePanelSizes: [number, number, number];
  toggleSidebar: () => void;
  setPanelSizes: (sizes: [number, number, number]) => void;
}

export const useLayoutStore = create<LayoutStore>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      livePanelSizes: [25, 50, 25] as [number, number, number],

      toggleSidebar: () =>
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

      setPanelSizes: (sizes: [number, number, number]) =>
        set({ livePanelSizes: sizes }),
    }),
    {
      name: 'terrarium-layout',
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
