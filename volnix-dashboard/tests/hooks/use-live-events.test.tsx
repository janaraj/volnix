import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { WsManager } from '@/services/ws-manager';
import { MockWebSocket } from '../helpers/mock-websocket';
import { useLiveEvents } from '@/hooks/use-live-events';
import { queryKeys } from '@/constants/query-keys';
import { createMockWorldEvent } from '../mocks/data/events';
import { createMockRun } from '../mocks/data/runs';
import type { ReactNode } from 'react';

let testWs: WsManager;
let queryClient: QueryClient;

vi.mock('@/providers/services-provider', () => ({
  useWsManager: () => testWs,
}));

beforeEach(() => {
  MockWebSocket.reset();
  vi.stubGlobal('WebSocket', MockWebSocket);
  testWs = new WsManager('ws://localhost');
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

afterEach(() => {
  vi.restoreAllMocks();
});

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe('useLiveEvents', () => {
  it('connects to WsManager for the run', () => {
    renderHook(() => useLiveEvents('run-1'), { wrapper });
    expect(MockWebSocket.instances).toHaveLength(1);
    expect(MockWebSocket.instances[0].url).toContain('run-1');
  });

  it('appends events to query cache with dedup', () => {
    queryClient.setQueryData(queryKeys.runs.events('run-1'), {
      events: [createMockWorldEvent({ event_id: 'existing-1' })],
      total: 1,
    });

    renderHook(() => useLiveEvents('run-1'), { wrapper });
    MockWebSocket.instances[0].simulateOpen();

    act(() => {
      MockWebSocket.instances[0].simulateMessage(JSON.stringify({
        type: 'event',
        data: createMockWorldEvent({ event_id: 'new-1' }),
      }));
    });

    const cached = queryClient.getQueryData(queryKeys.runs.events('run-1')) as { events: { event_id: string }[] };
    expect(cached.events).toHaveLength(2);

    // Dedup: same event again should not add
    act(() => {
      MockWebSocket.instances[0].simulateMessage(JSON.stringify({
        type: 'event',
        data: createMockWorldEvent({ event_id: 'new-1' }),
      }));
    });
    const cached2 = queryClient.getQueryData(queryKeys.runs.events('run-1')) as { events: { event_id: string }[] };
    expect(cached2.events).toHaveLength(2);
  });

  it('patches run detail on status message', () => {
    queryClient.setQueryData(
      queryKeys.runs.detail('run-1'),
      createMockRun({ run_id: 'run-1', current_tick: 10 }),
    );

    renderHook(() => useLiveEvents('run-1'), { wrapper });
    MockWebSocket.instances[0].simulateOpen();

    act(() => {
      MockWebSocket.instances[0].simulateMessage(JSON.stringify({
        type: 'status',
        data: { status: 'running', tick: 42, world_time: '2026-03-01T10:00:00Z' },
      }));
    });

    const cached = queryClient.getQueryData(queryKeys.runs.detail('run-1')) as { current_tick: number };
    expect(cached.current_tick).toBe(42);
  });

  it('invalidates queries on run_complete', () => {
    const spy = vi.spyOn(queryClient, 'invalidateQueries');

    renderHook(() => useLiveEvents('run-1'), { wrapper });
    MockWebSocket.instances[0].simulateOpen();

    act(() => {
      MockWebSocket.instances[0].simulateMessage(JSON.stringify({
        type: 'run_complete',
        data: createMockRun({ run_id: 'run-1', status: 'completed' }),
      }));
    });

    expect(spy).toHaveBeenCalled();
  });

  it('cleans up on unmount', () => {
    const { unmount } = renderHook(() => useLiveEvents('run-1'), { wrapper });
    unmount();
    expect(testWs.getCurrentRunId()).toBeNull();
  });
});
