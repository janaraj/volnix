import { describe, it, expect, vi, beforeAll, afterAll, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { server } from '../../mocks/server';
import { ApiClient } from '@/services/api-client';
import { useScorecard } from '@/hooks/queries/use-scorecard';
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

describe('useScorecard', () => {
  it('fetches scorecard for a run', async () => {
    const { result } = renderHook(() => useScorecard('run-1'), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.per_actor).toBeDefined();
    expect(result.current.data?.collective).toBeDefined();
    expect(result.current.data?.collective.overall_score).toBe(85);
  });

  it('returns scorecard with per_actor scores', async () => {
    const { result } = renderHook(() => useScorecard('run-1'), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const perActor = result.current.data?.per_actor ?? {};
    expect(Object.keys(perActor).length).toBeGreaterThan(0);
    expect(perActor['agent-alpha']?.policy_compliance).toBe(94);
  });
});
