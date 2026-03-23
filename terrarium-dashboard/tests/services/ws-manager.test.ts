import { describe, it } from 'vitest';

describe('WsManager', () => {
  describe('connect', () => {
    it.todo('opens WebSocket connection for run ID');
    it.todo('sets status to connecting then connected');
  });

  describe('disconnect', () => {
    it.todo('closes WebSocket and clears run ID');
    it.todo('cancels pending reconnect timer');
  });

  describe('reconnection', () => {
    it.todo('reconnects with exponential backoff on close');
    it.todo('caps backoff at WS_RECONNECT_MAX_MS');
    it.todo('resets backoff on successful reconnect');
  });

  describe('subscribe', () => {
    it.todo('dispatches parsed messages to handlers');
    it.todo('returns unsubscribe function');
    it.todo('ignores malformed messages');
  });
});
