// ---------------------------------------------------------------------------
// UI-specific types (not derived from backend)
// ---------------------------------------------------------------------------

export type ReportTabId = 'overview' | 'deliverable' | 'scorecard' | 'events' | 'entities' | 'gaps' | 'conditions';

export type OutcomeCategory = 'success' | 'denied' | 'policy' | 'world' | 'system' | 'gap';

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'reconnecting';

export interface FilterState {
  actor_id?: string;
  service_id?: string;
  event_type?: string;
  outcome?: string;
}
