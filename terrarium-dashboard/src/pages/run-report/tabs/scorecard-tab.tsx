import { useMemo } from 'react';
import type { ServiceSummary, GovernanceScorecard } from '@/types/domain';
import { useScorecard } from '@/hooks/queries/use-scorecard';
import { QueryGuard } from '@/components/feedback/query-guard';
import { SectionLoading } from '@/components/feedback/section-loading';
import { EmptyState } from '@/components/feedback/empty-state';
import { ServiceBadge } from '@/components/domain/service-badge';
import { FidelityIndicator } from '@/components/domain/fidelity-indicator';
import { formatScore } from '@/lib/formatters';
import { scoreToColorClass } from '@/lib/color-utils';
import { cn } from '@/lib/cn';

interface ScorecardTabProps {
  runId: string;
  services: ServiceSummary[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDimensionName(name: string): string {
  return name
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function findScore(
  scorecard: GovernanceScorecard,
  dimensionName: string,
): number | null {
  const found = scorecard.scores.find((s) => s.name === dimensionName);
  return found ? found.value : null;
}

const TIER_LABELS: Record<string, string> = {
  tier1_percentage: 'Tier 1',
  tier2_percentage: 'Tier 2',
};

const CONFIDENCE_COLORS: Record<string, string> = {
  high: 'bg-success/15 text-success',
  moderate: 'bg-warning/15 text-warning',
  low: 'bg-error/15 text-error',
};

// ---------------------------------------------------------------------------
// ScorecardGrid
// ---------------------------------------------------------------------------

function ScorecardGrid({ scorecards }: { scorecards: GovernanceScorecard[] }) {
  const { dimensions, actorIds } = useMemo(() => {
    const dimSet = new Set<string>();
    for (const sc of scorecards) {
      for (const s of sc.scores) {
        dimSet.add(s.name);
      }
    }
    return {
      dimensions: Array.from(dimSet),
      actorIds: scorecards.map((sc) => sc.actor_id),
    };
  }, [scorecards]);

  if (scorecards.length === 0) {
    return <EmptyState title="No scorecard data available" />;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-bg-elevated">
            <th className="px-3 py-2 text-left text-xs font-medium uppercase text-text-muted">
              Dimension
            </th>
            {actorIds.map((id) => (
              <th
                key={id}
                className="px-3 py-2 text-center text-xs font-medium uppercase text-text-muted"
              >
                {id}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {dimensions.map((dim) => (
            <tr key={dim} className="border-b border-bg-elevated">
              <td className="px-3 py-2 text-text-secondary">
                {formatDimensionName(dim)}
              </td>
              {scorecards.map((sc) => {
                const value = findScore(sc, dim);
                return (
                  <td key={sc.actor_id} className="px-3 py-2 text-center">
                    {value != null ? (
                      <span
                        className={cn(
                          'inline-block rounded px-2 py-0.5 font-mono text-xs',
                          scoreToColorClass(value),
                        )}
                      >
                        {formatScore(value)}
                      </span>
                    ) : (
                      <span className="text-text-muted">--</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
          <tr className="border-t-2 border-bg-elevated font-semibold">
            <td className="px-3 py-2 text-text-primary">Overall</td>
            {scorecards.map((sc) => (
              <td key={sc.actor_id} className="px-3 py-2 text-center">
                <span
                  className={cn(
                    'inline-block rounded px-2 py-0.5 font-mono text-xs',
                    scoreToColorClass(sc.overall_score),
                  )}
                >
                  {formatScore(sc.overall_score)}
                </span>
              </td>
            ))}
          </tr>
        </tbody>
      </table>
      <p className="mt-3 text-xs text-text-muted">
        Click any score to see the events that contributed to it.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// FidelityBasisCard
// ---------------------------------------------------------------------------

function FidelityBasisCard({
  scorecards,
  services,
}: {
  scorecards: GovernanceScorecard[];
  services: ServiceSummary[];
}) {
  const basis = scorecards[0]?.fidelity_basis;

  if (!basis) {
    return null;
  }

  return (
    <div className="rounded-lg border border-bg-elevated bg-bg-surface p-4">
      <h3 className="mb-3 text-lg font-semibold">Fidelity Basis</h3>

      {services.length > 0 && (
        <div className="mb-4 space-y-2">
          <p className="text-xs font-medium uppercase text-text-muted">Services</p>
          <div className="flex flex-wrap gap-3">
            {services.map((svc) => (
              <div key={svc.service_id} className="flex items-center gap-2">
                <ServiceBadge serviceId={svc.service_id} tier={svc.fidelity_tier} />
                <FidelityIndicator tier={svc.fidelity_tier} source={svc.fidelity_source} />
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mb-4 flex gap-6">
        {(['tier1_percentage', 'tier2_percentage'] as const).map((key) => (
          <div key={key}>
            <p className="text-xs font-medium uppercase text-text-muted">
              {TIER_LABELS[key]}
            </p>
            <p className="mt-0.5 text-lg font-semibold">
              {Math.round(basis[key] * 100)}%
            </p>
          </div>
        ))}
      </div>

      <div>
        <p className="text-xs font-medium uppercase text-text-muted">Confidence</p>
        <span
          className={cn(
            'mt-1 inline-block rounded-full px-2.5 py-0.5 text-xs font-medium uppercase',
            CONFIDENCE_COLORS[basis.confidence] ?? 'bg-bg-elevated text-text-muted',
          )}
        >
          {basis.confidence}
        </span>
      </div>

      {basis.recommendation && (
        <div className="mt-3">
          <p className="text-xs font-medium uppercase text-text-muted">Recommendation</p>
          <p className="mt-0.5 text-sm text-text-secondary">{basis.recommendation}</p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ScorecardTab
// ---------------------------------------------------------------------------

export function ScorecardTab({ runId, services }: ScorecardTabProps) {
  const scorecardQuery = useScorecard(runId);

  return (
    <div className="space-y-6">
      <section>
        <h2 className="mb-3 text-lg font-semibold">Scorecard Grid</h2>
        <QueryGuard query={scorecardQuery} loadingFallback={<SectionLoading />}>
          {(scorecards) => (
            <div className="space-y-6">
              <ScorecardGrid scorecards={scorecards} />
              <FidelityBasisCard scorecards={scorecards} services={services} />
            </div>
          )}
        </QueryGuard>
      </section>
    </div>
  );
}
