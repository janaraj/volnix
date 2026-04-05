import type { ServiceSummary } from '@/types/domain';
import type { ScorecardResponse } from '@/types/api';
import { useScorecard } from '@/hooks/queries/use-scorecard';
import { QueryGuard } from '@/components/feedback/query-guard';
import { EmptyState } from '@/components/feedback/empty-state';
import { ScorecardGridSkeleton } from '@/components/feedback/skeletons';
import { ServiceBadge } from '@/components/domain/service-badge';
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

// ---------------------------------------------------------------------------
// ScorecardGrid
// ---------------------------------------------------------------------------

function ScorecardGrid({ data }: { data: ScorecardResponse }) {
  const actorIds = Object.keys(data.per_actor);
  const dimensions = Object.keys(data.collective).filter(
    (k) => k !== 'overall_score' && k !== 'scores',
  );

  if (actorIds.length === 0) {
    return <EmptyState title="No scorecard data available" />;
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-border/30 shadow-sm">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border/30 bg-bg-elevated/30">
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
            <tr key={dim} className="border-b border-border/30">
              <td className="px-3 py-2 text-text-secondary">
                {formatDimensionName(dim)}
              </td>
              {actorIds.map((actorId) => {
                const raw = data.per_actor[actorId]?.[dim];
                const value = typeof raw === 'number' ? raw : null;
                return (
                  <td key={actorId} className="px-3 py-2 text-center">
                    {value != null ? (
                      <span
                        className={cn(
                          'inline-block rounded-md px-2.5 py-1 font-mono text-xs',
                          scoreToColorClass(value / 100),
                        )}
                      >
                        {formatScore(value / 100)}
                      </span>
                    ) : (
                      <span className="text-text-muted">--</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
          {data.collective.overall_score != null && (
            <tr className="border-t-2 border-border/30 font-semibold">
              <td className="px-3 py-2 text-text-primary">Overall</td>
              {actorIds.map((actorId) => (
                <td key={actorId} className="px-3 py-2 text-center">
                  <span
                    className={cn(
                      'inline-block rounded-md px-2.5 py-1 font-mono text-xs',
                      scoreToColorClass(data.collective.overall_score / 100),
                    )}
                  >
                    {formatScore(data.collective.overall_score / 100)}
                  </span>
                </td>
              ))}
            </tr>
          )}
        </tbody>
      </table>
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
        <QueryGuard query={scorecardQuery} loadingFallback={<ScorecardGridSkeleton />}>
          {(data: ScorecardResponse) => (
            <div className="space-y-6">
              <ScorecardGrid data={data} />

              {services.length > 0 && (
                <div className="rounded-lg border border-bg-elevated bg-bg-surface p-4">
                  <h3 className="mb-3 text-lg font-semibold">Service Fidelity</h3>
                  <div className="flex flex-wrap gap-3">
                    {services.map((svc) => (
                      <ServiceBadge key={svc.service_id} serviceId={svc.service_id} tier={svc.fidelity_tier} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </QueryGuard>
      </section>
    </div>
  );
}
