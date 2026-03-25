import { describe, it, expect, vi, beforeAll, afterAll, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { server } from '../../mocks/server';
import { ApiClient } from '@/services/api-client';
import { useRunEvents, useRunEvent } from '@/hooks/queries/use-events';
import type { ReactNode } from 'react';

const testApi = new ApiClient('');
vi.mock('@/providers/services-provider', () => ({
  useApiClient: () => testApi,
}));

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe('useRunEvents', () => {
  it('fetches events for a run', async () => {
    const { result } = renderHook(() => useRunEvents('run-test-001'), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.events.length).toBeGreaterThan(0);
  });

  it('passes filter params', async () => {
    const { result } = renderHook(
      () => useRunEvents('run-1', { actor_id: 'agent-alpha' }),
      { wrapper: createWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

describe('useRunEvent', () => {
  it('fetches single event', async () => {
    const { result } = renderHook(() => useRunEvent('run-1', 'evt-test-001'), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.event_id).toBeDefined();
  });

  it('disables query when eventId is empty', () => {
    const { result } = renderHook(() => useRunEvent('run-1', ''), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
  });
});
