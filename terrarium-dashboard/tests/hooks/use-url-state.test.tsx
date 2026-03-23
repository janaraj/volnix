import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { useUrlState } from '@/hooks/use-url-state';
import type { ReactNode } from 'react';

function createWrapper(initialEntries: string[] = ['/']) {
  return ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
  );
}

describe('useUrlState', () => {
  it('reads initial state from URL search params', () => {
    const { result } = renderHook(
      () => useUrlState({ tab: 'overview', filter: '' }),
      { wrapper: createWrapper(['/?tab=events&filter=agent']) },
    );
    expect(result.current[0].tab).toBe('events');
    expect(result.current[0].filter).toBe('agent');
  });

  it('falls back to defaults for missing params', () => {
    const { result } = renderHook(
      () => useUrlState({ tab: 'overview', filter: '' }),
      { wrapper: createWrapper(['/']) },
    );
    expect(result.current[0].tab).toBe('overview');
    expect(result.current[0].filter).toBe('');
  });

  it('updates state when setState called', () => {
    const { result } = renderHook(
      () => useUrlState({ tab: 'overview' }),
      { wrapper: createWrapper(['/']) },
    );
    act(() => {
      result.current[1]({ tab: 'events' });
    });
    expect(result.current[0].tab).toBe('events');
  });

  it('removes param when set to empty string', () => {
    const { result } = renderHook(
      () => useUrlState({ tab: 'overview', filter: '' }),
      { wrapper: createWrapper(['/?filter=agent']) },
    );
    act(() => {
      result.current[1]({ filter: '' });
    });
    expect(result.current[0].filter).toBe('');
  });
});
