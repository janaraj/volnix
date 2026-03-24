import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

interface LayoutStore {
  sidebarCollapsed: boolean;
  livePanelSizes: [number, number, number];
  toggleSidebar: () => void;
  setPanelSizes: (sizes: [number, number, number]) => void;
}

// Safe storage wrapper — handles jsdom/SSR environments
function safeStorage() {
  try {
    const testKey = '__zustand_test__';
    localStorage.setItem(testKey, '1');
    localStorage.removeItem(testKey);
    return createJSONStorage(() => localStorage);
  } catch {
    // In-memory fallback for jsdom/SSR
    const memStore = new Map<string, string>();
    return createJSONStorage(() => ({
      getItem: (name: string) => memStore.get(name) ?? null,
      setItem: (name: string, value: string) => { memStore.set(name, value); },
      removeItem: (name: string) => { memStore.delete(name); },
    }));
  }
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
      storage: safeStorage(),
    },
  ),
);
