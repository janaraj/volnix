import type { WsMessage } from '@/types/ws';

export class MockWsServer {
  private handlers: Set<(data: string) => void> = new Set();

  /** Simulate sending a typed message to all connected clients */
  send(message: WsMessage): void {
    const data = JSON.stringify(message);
    this.handlers.forEach((handler) => handler(data));
  }

  /** Register a handler (simulates WebSocket.onmessage) */
  addConnection(handler: (data: string) => void): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  /** Get number of active connections */
  getConnectionCount(): number {
    return this.handlers.size;
  }
}
