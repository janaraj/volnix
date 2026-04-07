// ---------------------------------------------------------------------------
// Classification helpers — map domain values to UI labels / Tailwind classes.
// All mappings are data-driven Record lookups. No heuristics.
// ---------------------------------------------------------------------------

const EVENT_TYPE_COLORS: Record<string, string> = {
  'world': 'text-info',
  'policy.hold': 'text-warning',
  'policy.block': 'text-error',
  'policy.escalate': 'text-warning',
  'policy.flag': 'text-warning',
  'permission.denied': 'text-error',
  'budget.deduction': 'text-warning',
  'budget.warning': 'text-warning',
  'budget.exhausted': 'text-error',
  'capability.gap': 'text-neutral',
  'animator': 'text-info',
  'world.populate': 'text-text-secondary',
  'feedback': 'text-text-secondary',
  'world.generation_complete': 'text-text-muted',
};

/** Map an event type to a Tailwind text color class. */
export function eventTypeToColorClass(eventType: string): string {
  return EVENT_TYPE_COLORS[eventType] ?? 'text-text-muted';
}

const OUTCOME_COLORS: Record<string, string> = {
  success: 'text-success',
  denied: 'text-error',
  held: 'text-warning',
  escalated: 'text-warning',
  error: 'text-error',
  gap: 'text-neutral',
  flagged: 'text-info',
};

/** Map an outcome to a Tailwind text color class. */
export function outcomeToColorClass(outcome: string): string {
  return OUTCOME_COLORS[outcome] ?? 'text-text-muted';
}

const ENFORCEMENT_COLORS: Record<string, string> = {
  hold: 'text-warning',
  block: 'text-error',
  escalate: 'text-warning',
  log: 'text-text-muted',
};

/** Map a policy enforcement level to a Tailwind text color class. */
export function enforcementToColorClass(enforcement: string): string {
  return ENFORCEMENT_COLORS[enforcement] ?? 'text-text-muted';
}

const GAP_LABELS: Record<string, string> = {
  hallucinated: 'Hallucinated',
  adapted: 'Adapted',
  escalated: 'Escalated',
  skipped: 'Skipped',
};

/** Map a capability gap response to a human-readable label. */
export function gapResponseToLabel(response: string): string {
  return GAP_LABELS[response] ?? response;
}

const RUN_STATUS_COLORS: Record<string, string> = {
  created: 'text-neutral',
  running: 'text-info',
  completed: 'text-success',
  failed: 'text-error',
  stopped: 'text-warning',
};

/** Map a run status to a Tailwind color class. */
export function runStatusToColorClass(status: string): string {
  return RUN_STATUS_COLORS[status] ?? 'text-text-muted';
}

const GRADE_THRESHOLDS: Array<{ min: number; label: string }> = [
  { min: 0.9, label: 'A' },
  { min: 0.75, label: 'B' },
  { min: 0.6, label: 'C' },
  { min: 0, label: 'D' },
];

/** Convert a 0-1 score value to a letter grade label. */
export function scoreToGradeLabel(value: number): string {
  const entry = GRADE_THRESHOLDS.find((t) => value >= t.min);
  return entry?.label ?? 'D';
}
