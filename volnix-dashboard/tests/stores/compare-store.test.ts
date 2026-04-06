import { describe, it, expect, beforeEach } from 'vitest';
import { useCompareStore } from '@/stores/compare-store';

beforeEach(() => {
  useCompareStore.setState({ selectedRunIds: [] });
});

describe('useCompareStore', () => {
  it('starts with empty selection', () => {
    expect(useCompareStore.getState().selectedRunIds).toEqual([]);
  });

  it('toggleRun adds run ID', () => {
    useCompareStore.getState().toggleRun('run-1');
    expect(useCompareStore.getState().selectedRunIds).toEqual(['run-1']);
  });

  it('toggleRun removes if already selected', () => {
    useCompareStore.getState().toggleRun('run-1');
    useCompareStore.getState().toggleRun('run-1');
    expect(useCompareStore.getState().selectedRunIds).toEqual([]);
  });

  it('clearSelection empties list', () => {
    useCompareStore.getState().toggleRun('run-1');
    useCompareStore.getState().toggleRun('run-2');
    useCompareStore.getState().clearSelection();
    expect(useCompareStore.getState().selectedRunIds).toEqual([]);
  });

  it('isSelected returns correct boolean', () => {
    useCompareStore.getState().toggleRun('run-1');
    expect(useCompareStore.getState().isSelected('run-1')).toBe(true);
    expect(useCompareStore.getState().isSelected('run-2')).toBe(false);
  });
});
