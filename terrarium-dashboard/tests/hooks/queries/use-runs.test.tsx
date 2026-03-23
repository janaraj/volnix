import { describe, it, expect, vi, beforeAll, afterAll, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { server } from '../../mocks/server';
import { ApiClient } from '@/services/api-client';
import { useRuns, useRun } from '@/hooks/queries/use-runs';
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

describe('useRuns', () => {
  it('fetches runs on mount', async () => {
    const { result } = renderHook(() => useRuns(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toHaveLength(3);
  });

  it('passes params to query', async () => {
    const { result } = renderHook(() => useRuns({ status: 'running' }), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });

  it('returns paginated response shape', async () => {
    const { result } = renderHook(() => useRuns(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveProperty('items');
    expect(result.current.data).toHaveProperty('total');
    expect(result.current.data).toHaveProperty('has_more');
  });
});

describe('useRun', () => {
  it('fetches single run by ID', async () => {
    const { result } = renderHook(() => useRun('run-test-001'), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.id).toBe('run-test-001');
  });

  it('returns run with world_name', async () => {
    const { result } = renderHook(() => useRun('run-test-001'), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.world_name).toBeDefined();
  });
});
