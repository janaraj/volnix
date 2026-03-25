// ---------------------------------------------------------------------------
// Domain types — mirrors Python backend models
// ---------------------------------------------------------------------------

// -- Run types --------------------------------------------------------------

export type RunStatus = 'created' | 'running' | 'completed' | 'failed' | 'stopped';

export type FidelitySource = 'verified_pack' | 'curated_profile' | 'bootstrapped';

export interface ServiceSummary {
  service_id: string;
  service_name: string;
  category: string;
  fidelity_tier: 1 | 2;
  fidelity_source: FidelitySource;
  entity_count: number;
}

export interface ConfigSnapshot {
  seed?: number | null;
  mode?: string;
  behavior?: 'static' | 'reactive' | 'dynamic';
}

export interface WorldDef {
  name: string;
}

export interface Run {
  run_id: string;
  status: RunStatus;
  world_def: WorldDef;
  mode: 'governed' | 'ungoverned';
  reality_preset: string;
  fidelity_mode: string;
  tag: string;
  config_snapshot: ConfigSnapshot;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  // Backend will add these — optional until then:
  description?: string;
  current_tick?: number;
  actor_count?: number;
  event_count?: number;
  governance_score?: number | null;
  services?: ServiceSummary[];
  conditions?: WorldConditions;
  error?: string | null;
}

// -- World conditions (5 reality dimensions) --------------------------------

export interface WorldConditions {
  information: InformationDimension;
  reliability: ReliabilityDimension;
  friction: FrictionDimension;
  complexity: ComplexityDimension;
  boundaries: BoundariesDimension;
}

export interface InformationDimension {
  staleness: number;
  incompleteness: number;
  inconsistency: number;
  noise: number;
}

export interface ReliabilityDimension {
  failures: number;
  timeouts: number;
  degradation: number;
}

export interface FrictionDimension {
  uncooperative: number;
  deceptive: number;
  hostile: number;
  sophistication: 'low' | 'medium' | 'high';
}

export interface ComplexityDimension {
  ambiguity: number;
  edge_cases: number;
  contradictions: number;
  urgency: number;
  volatility: number;
}

export interface BoundariesDimension {
  access_limits: number;
  rule_clarity: number;
  boundary_gaps: number;
}

// -- Events -----------------------------------------------------------------

export type EventType =
  | 'agent_action'
  | 'policy_hold'
  | 'policy_block'
  | 'policy_escalate'
  | 'policy_flag'
  | 'permission_denied'
  | 'budget_deduction'
  | 'budget_warning'
  | 'budget_exhausted'
  | 'capability_gap'
  | 'animator_event'
  | 'state_change'
  | 'side_effect'
  | 'system_event';

export type Outcome =
  | 'success'
  | 'denied'
  | 'held'
  | 'escalated'
  | 'error'
  | 'gap'
  | 'flagged';

export interface EventTimestamp {
  world_time: string;
  wall_time: string;
  tick: number;
}

export interface FidelityMetadata {
  tier: 1 | 2;
  source: string;
  fidelity_source: FidelitySource | null;
  profile_version: string | null;
  deterministic: boolean;
  replay_stable: boolean;
  benchmark_grade: boolean;
}

export interface WorldEvent {
  event_type: EventType | string;
  actor_id: string;
  // Backend will add these — optional until then:
  event_id?: string;
  timestamp?: EventTimestamp;
  caused_by?: string | null;
  actor_role?: string;
  service_id?: string | null;
  action?: string;
  outcome?: Outcome;
  entity_ids?: string[];
  input_data?: Record<string, unknown>;
  output_data?: Record<string, unknown>;
  policy_hit?: PolicyHit | null;
  budget_delta?: number;
  budget_remaining?: number;
  causal_parent_ids?: string[];
  causal_child_ids?: string[];
  fidelity_tier?: 1 | 2;
  fidelity?: FidelityMetadata | null;
  run_id?: string;
  metadata?: Record<string, unknown>;
}

// -- Entities ---------------------------------------------------------------

export interface StateChange {
  event_id: string;
  timestamp: string;
  actor_id: string;
  field: string;
  old_value: unknown;
  new_value: unknown;
}

export interface Entity {
  id: string;
  entity_type: string;
  service_id?: string;
  fields?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
  state_history?: StateChange[];
}

// -- Actors -----------------------------------------------------------------

export interface BudgetValues {
  api_calls: number;
  llm_spend_usd: number;
  world_actions: number;
}

export interface AgentSummary {
  actor_id: string;
  role: string;
  actor_type: 'agent' | 'human' | 'system';
  budget_total: BudgetValues;
  budget_remaining: BudgetValues;
  action_count: number;
  governance_score: number | null;
  action_history?: WorldEvent[];
}

// -- Governance -------------------------------------------------------------

export interface Score {
  name: string;
  value: number;
  weight: number;
  formula: string;
  event_count: number;
  violations: string[];
}

export interface FidelityBasis {
  tier1_percentage: number;
  tier2_percentage: number;
  confidence: 'high' | 'moderate' | 'low';
  recommendation: string;
}

export interface PolicyHit {
  policy_id: string;
  policy_name: string;
  enforcement: 'hold' | 'block' | 'escalate' | 'log';
  condition: string;
  resolution: string | null;
}

// -- Capability gaps --------------------------------------------------------

export type GapResponse = 'hallucinated' | 'adapted' | 'escalated' | 'skipped';

export interface CapabilityGap {
  event_id: string;
  timestamp: string;
  actor_id: string;
  requested_tool: string;
  response: GapResponse;
  description: string;
  next_actions: string[];
}

// -- Entity updates (WebSocket push) ----------------------------------------

export interface EntityUpdate {
  entity_id: string;
  entity_type: string;
  service_id: string;
  fields: Record<string, unknown>;
  changed_fields: string[];
  caused_by_event: string;
}
