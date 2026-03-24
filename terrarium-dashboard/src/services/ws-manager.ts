import type { WsMessage } from '@/types/ws';
import type { ConnectionStatus } from '@/types/ui';
import {
  WS_RECONNECT_BASE_MS,
  WS_RECONNECT_MAX_MS,
  WS_RECONNECT_MULTIPLIER,
} from '@/constants/defaults';

type WsHandler = (message: WsMessage) => void;

export class WsManager {
  private ws: WebSocket | null = null;
  private handlers: Set<WsHandler> = new Set();
  private statusListeners: Set<(status: ConnectionStatus) => void> = new Set();
  private status: ConnectionStatus = 'disconnected';
  private currentRunId: string | null = null;
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private baseUrl: string;

  constructor(baseUrl: string = '') {
    this.baseUrl = baseUrl || `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`;
  }

  getStatus(): ConnectionStatus {
    return this.status;
  }

  getCurrentRunId(): string | null {
    return this.currentRunId;
  }

  /** Subscribe to connection status changes. Returns unsubscribe function. */
  subscribeStatus(handler: (status: ConnectionStatus) => void): () => void {
    this.statusListeners.add(handler);
    return () => { this.statusListeners.delete(handler); };
  }

  private setStatus(newStatus: ConnectionStatus): void {
    if (this.status !== newStatus) {
      this.status = newStatus;
      this.statusListeners.forEach((listener) => listener(newStatus));
    }
  }

  connect(runId: string): void {
    // Disconnect existing connection if any
    if (this.ws) {
      this.disconnect();
    }

    this.currentRunId = runId;
    this.setStatus('connecting');

    const url = `${this.baseUrl}/ws/runs/${runId}/live`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.setStatus('connected');
      this.reconnectAttempts = 0;
    };

    this.ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as WsMessage;
        this.handlers.forEach((handler) => handler(message));
      } catch {
        // Ignore malformed messages
      }
    };

    this.ws.onclose = () => {
      if (this.currentRunId === runId) {
        this.scheduleReconnect(runId);
      }
    };

    this.ws.onerror = () => {
      // onclose will fire after onerror
    };
  }

  disconnect(): void {
    this.currentRunId = null;
    this.setStatus('disconnected');
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.onclose = null; // prevent reconnection
      this.ws.close();
      this.ws = null;
    }
  }

  subscribe(handler: WsHandler): () => void {
    this.handlers.add(handler);
    return () => {
      this.handlers.delete(handler);
    };
  }

  private scheduleReconnect(runId: string): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.setStatus('reconnecting');
    const delay = Math.min(
      WS_RECONNECT_BASE_MS * Math.pow(WS_RECONNECT_MULTIPLIER, this.reconnectAttempts),
      WS_RECONNECT_MAX_MS,
    );
    this.reconnectAttempts++;
    this.reconnectTimer = setTimeout(() => {
      if (this.currentRunId === runId) {
        this.connect(runId);
      }
    }, delay);
  }
}
