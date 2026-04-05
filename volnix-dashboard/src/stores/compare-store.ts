import { create } from 'zustand';

interface CompareStore {
  selectedRunIds: string[];
  toggleRun: (id: string) => void;
  clearSelection: () => void;
  isSelected: (id: string) => boolean;
}

export const useCompareStore = create<CompareStore>((set, get) => ({
  selectedRunIds: [],

  toggleRun: (id: string) => {
    set((state) => {
      const exists = state.selectedRunIds.includes(id);
      return {
        selectedRunIds: exists
          ? state.selectedRunIds.filter((r) => r !== id)
          : [...state.selectedRunIds, id],
      };
    });
  },

  clearSelection: () => set({ selectedRunIds: [] }),

  isSelected: (id: string) => get().selectedRunIds.includes(id),
}));
