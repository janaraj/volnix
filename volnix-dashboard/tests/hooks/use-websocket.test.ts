import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { WsManager } from '@/services/ws-manager';
import { MockWebSocket } from '../helpers/mock-websocket';
import { useWebSocket } from '@/hooks/use-websocket';

let testWs: WsManager;

vi.mock('@/providers/services-provider', () => ({
  useWsManager: () => testWs,
}));

beforeEach(() => {
  MockWebSocket.reset();
  vi.stubGlobal('WebSocket', MockWebSocket);
  testWs = new WsManager('ws://localhost');
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('useWebSocket', () => {
  it('connects on mount when runId provided', () => {
    renderHook(() => useWebSocket('run-1'));
    expect(MockWebSocket.instances).toHaveLength(1);
    expect(MockWebSocket.instances[0].url).toContain('run-1');
  });

  it('does not connect when runId is null', () => {
    renderHook(() => useWebSocket(null));
    expect(MockWebSocket.instances).toHaveLength(0);
  });

  it('disconnects on unmount', () => {
    const { unmount } = renderHook(() => useWebSocket('run-1'));
    unmount();
    expect(testWs.getCurrentRunId()).toBeNull();
  });

  it('reports connection status changes', () => {
    const { result } = renderHook(() => useWebSocket('run-1'));
    expect(result.current.status).toBe('connecting');
    act(() => {
      MockWebSocket.instances[0].simulateOpen();
    });
    expect(result.current.status).toBe('connected');
  });
});
