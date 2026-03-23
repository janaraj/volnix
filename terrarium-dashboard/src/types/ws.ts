// ---------------------------------------------------------------------------
// WebSocket message types
// ---------------------------------------------------------------------------

import type { WorldEvent, Run, EntityUpdate } from './domain';

export interface WsEventMessage {
  type: 'event';
  data: WorldEvent;
}

export interface WsStatusMessage {
  type: 'status';
  data: {
    status: 'running' | 'paused';
    tick: number;
    world_time: string;
  };
}

export interface WsBudgetUpdateMessage {
  type: 'budget_update';
  data: {
    actor_id: string;
    remaining: number;
    total: number;
    budget_type: string;
  };
}

export interface WsEntityUpdateMessage {
  type: 'entity_update';
  data: EntityUpdate;
}

export interface WsRunCompleteMessage {
  type: 'run_complete';
  data: Run;
}

export type WsMessage =
  | WsEventMessage
  | WsStatusMessage
  | WsBudgetUpdateMessage
  | WsEntityUpdateMessage
  | WsRunCompleteMessage;
