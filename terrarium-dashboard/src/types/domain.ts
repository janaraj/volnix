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
  response_body?: Record<string, unknown>;
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
// Mirrors: http_rest.py entity detail handler response

export interface StateChange {
  event_id: string;
  event_type: string;
  timestamp: string;
  operation: string; // 'create' | 'update' | 'delete'
  fields: Record<string, unknown>;
  previous_fields: Record<string, unknown>;
}

export interface Entity {
  entity_id: string; // backend field name (not "id")
  entity_type: string;
  current_state: Record<string, unknown>; // backend field name (not "fields")
  state_history?: StateChange[];
  // List endpoint may include these:
  service_id?: string;
  created_at?: string;
  updated_at?: string;
}

// -- Actors -----------------------------------------------------------------
// Mirrors: http_rest.py actor detail handler response

export interface AgentSummary {
  actor_id: string;
  definition: Record<string, unknown>; // contains role, type, permissions, budget
  scorecard: Record<string, number> | null;
  action_count: number;
  last_action_at: string | null;
}

/** Helper: extract role from actor definition. */
export function getActorRole(actor: AgentSummary): string {
  return String(actor.definition?.role ?? 'unknown');
}

/** Helper: extract actor type from definition. */
export function getActorType(actor: AgentSummary): string {
  return String(actor.definition?.type ?? 'external');
}

/** Helper: extract governance score from scorecard. */
export function getGovernanceScore(actor: AgentSummary): number | null {
  return actor.scorecard?.overall_score ?? null;
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
// Mirrors: reporter/capability_gaps.py GapAnalyzer.analyze() output

export type GapResponse = 'hallucinated' | 'adapted' | 'escalated' | 'skipped';

export interface CapabilityGap {
  tick: string;
  agent: string;
  tool: string;
  response: string; // GapResponse value
  response_label: string; // GapResponse name (HALLUCINATED, ADAPTED, etc.)
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
