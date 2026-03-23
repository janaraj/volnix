import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { WsManager } from '@/services/ws-manager';
import { MockWebSocket } from '../helpers/mock-websocket';

beforeEach(() => {
  MockWebSocket.reset();
  vi.stubGlobal('WebSocket', MockWebSocket);
  vi.useFakeTimers();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('WsManager', () => {
  describe('connect', () => {
    it('opens WebSocket connection for run ID', () => {
      const ws = new WsManager('ws://localhost');
      ws.connect('run-1');
      expect(MockWebSocket.instances).toHaveLength(1);
      expect(MockWebSocket.instances[0].url).toBe('ws://localhost/ws/runs/run-1/live');
    });

    it('sets status to connecting then connected', () => {
      const ws = new WsManager('ws://localhost');
      ws.connect('run-1');
      expect(ws.getStatus()).toBe('connecting');
      MockWebSocket.instances[0].simulateOpen();
      expect(ws.getStatus()).toBe('connected');
    });

    it('disconnects existing connection before new one', () => {
      const ws = new WsManager('ws://localhost');
      ws.connect('run-1');
      ws.connect('run-2');
      expect(ws.getCurrentRunId()).toBe('run-2');
      expect(MockWebSocket.instances).toHaveLength(2);
    });
  });

  describe('disconnect', () => {
    it('closes WebSocket and clears run ID', () => {
      const ws = new WsManager('ws://localhost');
      ws.connect('run-1');
      ws.disconnect();
      expect(ws.getStatus()).toBe('disconnected');
      expect(ws.getCurrentRunId()).toBeNull();
    });

    it('cancels pending reconnect timer', () => {
      const ws = new WsManager('ws://localhost');
      ws.connect('run-1');
      MockWebSocket.instances[0].simulateOpen();
      MockWebSocket.instances[0].simulateClose();
      expect(ws.getStatus()).toBe('reconnecting');
      ws.disconnect();
      expect(ws.getStatus()).toBe('disconnected');
      vi.advanceTimersByTime(60_000);
      expect(MockWebSocket.instances).toHaveLength(1);
    });
  });

  describe('reconnection', () => {
    it('reconnects with exponential backoff on close', () => {
      const ws = new WsManager('ws://localhost');
      ws.connect('run-1');
      MockWebSocket.instances[0].simulateOpen();
      MockWebSocket.instances[0].simulateClose();
      expect(ws.getStatus()).toBe('reconnecting');
      vi.advanceTimersByTime(1_000);
      expect(MockWebSocket.instances).toHaveLength(2);
    });

    it('caps backoff at WS_RECONNECT_MAX_MS', () => {
      const ws = new WsManager('ws://localhost');
      ws.connect('run-1');
      for (let i = 0; i < 20; i++) {
        const instance = MockWebSocket.instances[MockWebSocket.instances.length - 1];
        instance.simulateOpen();
        instance.simulateClose();
        vi.advanceTimersByTime(30_000);
      }
      expect(MockWebSocket.instances.length).toBeGreaterThan(10);
    });

    it('resets backoff on successful reconnect', () => {
      const ws = new WsManager('ws://localhost');
      ws.connect('run-1');
      MockWebSocket.instances[0].simulateOpen();
      MockWebSocket.instances[0].simulateClose();
      vi.advanceTimersByTime(1_000);
      MockWebSocket.instances[1].simulateOpen();
      expect(ws.getStatus()).toBe('connected');
      MockWebSocket.instances[1].simulateClose();
      vi.advanceTimersByTime(1_000);
      expect(MockWebSocket.instances).toHaveLength(3);
    });
  });

  describe('subscribe', () => {
    it('dispatches parsed messages to handlers', () => {
      const ws = new WsManager('ws://localhost');
      const handler = vi.fn();
      ws.subscribe(handler);
      ws.connect('run-1');
      MockWebSocket.instances[0].simulateOpen();
      MockWebSocket.instances[0].simulateMessage(
        JSON.stringify({ type: 'event', data: { event_id: 'e1' } }),
      );
      expect(handler).toHaveBeenCalledWith({ type: 'event', data: { event_id: 'e1' } });
    });

    it('returns unsubscribe function', () => {
      const ws = new WsManager('ws://localhost');
      const handler = vi.fn();
      const unsub = ws.subscribe(handler);
      unsub();
      ws.connect('run-1');
      MockWebSocket.instances[0].simulateOpen();
      MockWebSocket.instances[0].simulateMessage(JSON.stringify({ type: 'event', data: {} }));
      expect(handler).not.toHaveBeenCalled();
    });

    it('ignores malformed messages', () => {
      const ws = new WsManager('ws://localhost');
      const handler = vi.fn();
      ws.subscribe(handler);
      ws.connect('run-1');
      MockWebSocket.instances[0].simulateOpen();
      MockWebSocket.instances[0].simulateMessage('not json {{{');
      expect(handler).not.toHaveBeenCalled();
    });
  });

  describe('subscribeStatus', () => {
    it('notifies listeners on status changes', () => {
      const ws = new WsManager('ws://localhost');
      const listener = vi.fn();
      ws.subscribeStatus(listener);
      ws.connect('run-1');
      expect(listener).toHaveBeenCalledWith('connecting');
      MockWebSocket.instances[0].simulateOpen();
      expect(listener).toHaveBeenCalledWith('connected');
    });

    it('returns unsubscribe function that stops notifications', () => {
      const ws = new WsManager('ws://localhost');
      const listener = vi.fn();
      const unsub = ws.subscribeStatus(listener);
      unsub();
      ws.connect('run-1');
      expect(listener).not.toHaveBeenCalled();
    });
  });
});
