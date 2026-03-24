import type { WorldConditions } from '@/types/domain';

interface ConditionsTabProps {
  conditions: WorldConditions;
  realityPreset: string;
  behavior: string;
}

// ---------------------------------------------------------------------------
// Data-driven dimension config
// ---------------------------------------------------------------------------

interface FieldDef {
  key: string;
  label: string;
  type: 'number' | 'text';
}

interface DimensionDef {
  title: string;
  fields: FieldDef[];
}

const DIMENSION_CONFIG: Record<keyof WorldConditions, DimensionDef> = {
  information: {
    title: 'Information Quality',
    fields: [
      { key: 'staleness', label: 'Staleness', type: 'number' },
      { key: 'incompleteness', label: 'Incompleteness', type: 'number' },
      { key: 'inconsistency', label: 'Inconsistency', type: 'number' },
      { key: 'noise', label: 'Noise', type: 'number' },
    ],
  },
  reliability: {
    title: 'Service Reliability',
    fields: [
      { key: 'failures', label: 'Failures', type: 'number' },
      { key: 'timeouts', label: 'Timeouts', type: 'number' },
      { key: 'degradation', label: 'Degradation', type: 'number' },
    ],
  },
  friction: {
    title: 'Social Friction',
    fields: [
      { key: 'uncooperative', label: 'Uncooperative', type: 'number' },
      { key: 'deceptive', label: 'Deceptive', type: 'number' },
      { key: 'hostile', label: 'Hostile', type: 'number' },
      { key: 'sophistication', label: 'Sophistication', type: 'text' },
    ],
  },
  complexity: {
    title: 'Task Complexity',
    fields: [
      { key: 'ambiguity', label: 'Ambiguity', type: 'number' },
      { key: 'edge_cases', label: 'Edge Cases', type: 'number' },
      { key: 'contradictions', label: 'Contradictions', type: 'number' },
      { key: 'urgency', label: 'Urgency', type: 'number' },
      { key: 'volatility', label: 'Volatility', type: 'number' },
    ],
  },
  boundaries: {
    title: 'Governance Boundaries',
    fields: [
      { key: 'access_limits', label: 'Access Limits', type: 'number' },
      { key: 'rule_clarity', label: 'Rule Clarity', type: 'number' },
      { key: 'boundary_gaps', label: 'Boundary Gaps', type: 'number' },
    ],
  },
};

// ---------------------------------------------------------------------------
// DimensionCard
// ---------------------------------------------------------------------------

function NumericField({ label, value }: { label: string; value: number }) {
  const pct = Math.max(0, Math.min(100, value * 100));

  return (
    <div className="flex items-center gap-3">
      <span className="w-28 shrink-0 text-sm text-text-secondary">{label}</span>
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-bg-elevated">
        <div
          className="h-full rounded-full bg-info transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="font-mono text-xs text-text-muted">{value}</span>
    </div>
  );
}

function TextField({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-28 shrink-0 text-sm text-text-secondary">{label}</span>
      <span className="rounded-full bg-bg-elevated px-2.5 py-0.5 text-xs text-text-secondary">
        {value}
      </span>
    </div>
  );
}

function DimensionCard({
  dimension,
  config,
}: {
  dimension: Record<string, unknown>;
  config: DimensionDef;
}) {
  return (
    <div className="rounded-lg border border-bg-elevated bg-bg-surface p-4">
      <h3 className="mb-3 text-base font-semibold">{config.title}</h3>
      <div className="space-y-2">
        {config.fields.map((field) => {
          const raw = dimension[field.key];
          if (field.type === 'number') {
            return (
              <NumericField
                key={field.key}
                label={field.label}
                value={typeof raw === 'number' ? raw : 0}
              />
            );
          }
          return (
            <TextField
              key={field.key}
              label={field.label}
              value={typeof raw === 'string' ? raw : String(raw ?? '')}
            />
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ConditionsTab
// ---------------------------------------------------------------------------

const DIMENSION_KEYS = Object.keys(DIMENSION_CONFIG) as (keyof WorldConditions)[];

export function ConditionsTab({ conditions, realityPreset, behavior }: ConditionsTabProps) {
  return (
    <div>
      <div className="mb-4 flex items-center gap-2 text-sm text-text-secondary">
        <span>Reality:</span>
        <span className="rounded-full bg-bg-elevated px-2 py-0.5 text-xs font-medium text-text-primary">{realityPreset}</span>
        <span className="text-text-muted">·</span>
        <span>Behavior:</span>
        <span className="rounded-full bg-bg-elevated px-2 py-0.5 text-xs font-medium text-text-primary">{behavior}</span>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      {DIMENSION_KEYS.map((key) => (
        <DimensionCard
          key={key}
          dimension={conditions[key] as unknown as Record<string, unknown>}
          config={DIMENSION_CONFIG[key]}
        />
      ))}
      </div>
    </div>
  );
}
