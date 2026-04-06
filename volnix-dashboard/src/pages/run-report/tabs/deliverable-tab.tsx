import { useDeliverable } from '@/hooks/queries/use-deliverable';
import { QueryGuard } from '@/components/feedback/query-guard';
import { EmptyState } from '@/components/feedback/empty-state';
import { cn } from '@/lib/cn';

interface DeliverableTabProps {
  runId: string;
}

const CONFIDENCE_COLORS: Record<string, string> = {
  low: 'bg-warning/10 text-warning border-warning/20',
  medium: 'bg-info/10 text-info border-info/20',
  high: 'bg-success/10 text-success border-success/20',
};

function formatKey(key: string): string {
  return key
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-border/30 bg-bg-surface p-4">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-text-muted">{title}</h3>
      {children}
    </section>
  );
}

function RenderValue({ label, value }: { label: string; value: unknown }) {
  if (value == null) return null;

  // Confidence badge (string or number)
  if (label === 'confidence') {
    const display = String(value);
    const colorKey = typeof value === 'number'
      ? (value >= 0.7 ? 'high' : value >= 0.4 ? 'medium' : 'low')
      : display;
    return (
      <span className={cn(
        'inline-flex items-center rounded-md border px-2.5 py-1 text-xs font-medium',
        CONFIDENCE_COLORS[colorKey] ?? CONFIDENCE_COLORS.medium,
      )}>
        Confidence: {typeof value === 'number' ? `${(value * 100).toFixed(0)}%` : display}
      </span>
    );
  }

  // String → paragraph
  if (typeof value === 'string') {
    return (
      <Section title={formatKey(label)}>
        <p className="text-text-secondary text-sm leading-relaxed">{value}</p>
      </Section>
    );
  }

  // Number → inline
  if (typeof value === 'number') {
    return (
      <Section title={formatKey(label)}>
        <p className="text-text-secondary text-sm font-mono">{value}</p>
      </Section>
    );
  }

  // Array of strings → bullet list
  if (Array.isArray(value) && value.length > 0 && typeof value[0] === 'string') {
    return (
      <Section title={formatKey(label)}>
        <ul className="list-disc space-y-1.5 pl-5">
          {value.map((item: string, i: number) => (
            <li key={i} className="text-text-secondary text-sm leading-relaxed">{item}</li>
          ))}
        </ul>
      </Section>
    );
  }

  // Array of objects → card list
  if (Array.isArray(value) && value.length > 0 && typeof value[0] === 'object') {
    return (
      <Section title={formatKey(label)}>
        <div className="space-y-3">
          {value.map((item: Record<string, unknown>, i: number) => (
            <div key={i} className="rounded-md border border-border/20 bg-bg-elevated/30 p-3">
              {Object.entries(item).map(([k, v]) => (
                <div key={k} className="mb-1 text-sm">
                  <span className="font-medium text-text-muted">{formatKey(k)}: </span>
                  <span className="text-text-secondary">{String(v)}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </Section>
    );
  }

  // Object → key-value pairs
  if (typeof value === 'object' && !Array.isArray(value)) {
    return (
      <Section title={formatKey(label)}>
        <div className="space-y-1">
          {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
            <div key={k} className="text-sm">
              <span className="font-medium text-text-muted">{formatKey(k)}: </span>
              <span className="text-text-secondary">{String(v)}</span>
            </div>
          ))}
        </div>
      </Section>
    );
  }

  return null;
}

// Fields to show at the top as headline, not in the sections list
const HEADLINE_FIELDS = new Set(['title', 'prediction', 'recommendation', 'assessment']);

export function DeliverableTab({ runId }: DeliverableTabProps) {
  const query = useDeliverable(runId);

  return (
    <QueryGuard query={query}>
      {(data) => {
        if ('error' in data) {
          return <EmptyState title="No deliverable" description="This run did not produce a deliverable." />;
        }

        const entries = Object.entries(data);
        const headline = entries.find(([k]) => HEADLINE_FIELDS.has(k));
        const confidence = entries.find(([k]) => k === 'confidence');
        const rest = entries.filter(([k]) => !HEADLINE_FIELDS.has(k) && k !== 'confidence');

        return (
          <div className="space-y-4">
            {headline && (
              <h2 className="text-xl font-bold tracking-tight leading-relaxed">
                {String(headline[1])}
              </h2>
            )}

            {confidence && <RenderValue label="confidence" value={confidence[1]} />}

            {rest.map(([key, value]) => (
              <RenderValue key={key} label={key} value={value} />
            ))}
          </div>
        );
      }}
    </QueryGuard>
  );
}
