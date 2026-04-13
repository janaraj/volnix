// ---------------------------------------------------------------------------
// API request / response types
// ---------------------------------------------------------------------------

import type { Run, WorldEvent, Entity, CapabilityGap, World } from '@/types/domain';

// -- Endpoint-specific response types (match backend shapes) ----------------

export interface RunsListResponse {
  runs: Run[];
  total: number;
}

export interface EventsListResponse {
  run_id?: string; // present in backend response, not used by frontend
  events: WorldEvent[];
  total: number;
}

export interface EventDetailResponse {
  event: WorldEvent;
  causal_ancestors: string[];
  causal_descendants: string[];
}

export interface EntitiesListResponse {
  run_id?: string; // present in backend response, not used by frontend
  entities: Entity[];
  total: number;
}

export interface GapsResponse {
  run_id: string;
  gaps: CapabilityGap[];
  summary: Record<string, unknown>;
}

export interface ScorecardResponse {
  run_id: string;
  per_actor: Record<string, Record<string, number>>;
  collective: Record<string, number>;
}

export interface DecisionTraceAction {
  step_index: number;
  tool_name: string;
  service: string;
  arguments: Record<string, unknown>;
  governance: {
    permission: 'allow' | 'deny';
    policy: 'pass' | 'block' | 'flag';
    budget_deducted: number;
  };
  outcome: string;
  committed: boolean;
  learned?: Record<string, unknown>;
  effect?: {
    operation: string;
    entity_type?: string;
    entity_id?: string;
    key_changes?: Record<string, unknown>;
  };
}

export interface DecisionTraceActivation {
  activation_id: string;
  actor_id: string;
  reason: 'kickstart' | 're_activation';
  cause_event_id: string | null;
  time_start: string | null;
  time_end: string | null;
  terminated_by: string;
  actions: DecisionTraceAction[];
  world_response: {
    animator_reactions: Array<{ summary: string }>;
  };
}

export interface DecisionTraceInfoAnalysis {
  role: string;
  entities_available: number;
  entities_queried: number;
  entities_utilized: number;
  coverage_ratio: number;
  utilization_ratio: number | null;
  utilization_method: string;
  unique_services_used: string[];
}

export interface DecisionTraceGovernanceSummary {
  role: string;
  total_world_actions: number;
  policies_triggered: number;
  policies_blocked: number;
  policy_pressure_rate: number | null;
  permissions_denied: number;
  permissions_checked: number;
  permission_rejection_rate: number | null;
  budget_consumed: number;
  budget_total: number | null;
  budget_utilization: number | null;
}

export interface DecisionTraceResponse {
  activations: DecisionTraceActivation[];
  information_analysis: Record<string, DecisionTraceInfoAnalysis>;
  governance_summary: Record<string, DecisionTraceGovernanceSummary>;
  game_outcome?: {
    reason: string;
    winner?: string;
    total_events: number;
    wall_clock_seconds?: number;
  };
  domain_narrative?: string[];
}

export interface CompareResponse {
  run_ids: string[];
  labels: Record<string, string>;
  scores: {
    metrics: Record<string, { values: Record<string, number>; deltas: Record<string, number> }>;
  };
  events: {
    totals: Record<string, number>;
    by_type: Record<string, Record<string, number>>;
  };
  entity_states: Record<string, unknown>;
}

export interface WorldsListResponse {
  worlds: World[];
  total: number;
}

// -- Request params ---------------------------------------------------------

export interface RunListParams {
  status?: string;
  preset?: string;
  from_date?: string;
  to_date?: string;
  tag?: string;
  limit?: number;
  offset?: number;
  sort?: string;
}

export interface EventFilterParams {
  actor_id?: string;
  service_id?: string;
  event_type?: string;
  outcome?: string;
  tick_from?: number;
  tick_to?: number;
  limit?: number;
  offset?: number;
  sort?: 'asc' | 'desc';
}

export interface EntityFilterParams {
  entity_type?: string;
  service_id?: string;
  limit?: number;
  offset?: number;
}

// -- Error ------------------------------------------------------------------

export class ApiError extends Error {
  status: number;
  code: string;
  details?: Record<string, unknown>;

  constructor(
    status: number,
    code: string,
    message: string,
    details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}
