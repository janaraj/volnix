import { useMemo } from 'react';
import { AlertTriangle, CheckCircle2, Circle } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useCapabilityGaps } from '@/hooks/queries/use-gaps';
import { QueryGuard } from '@/components/feedback/query-guard';
import { SectionLoading } from '@/components/feedback/section-loading';
import { EmptyState } from '@/components/feedback/empty-state';
import { ActorBadge } from '@/components/domain/actor-badge';
import { gapResponseToLabel } from '@/lib/classifiers';
import { truncateId } from '@/lib/formatters';
import type { CapabilityGap } from '@/types/domain';

interface GapsTabProps {
  runId: string;
}

// Data-driven response styling
const GAP_RESPONSE_COLORS: Record<string, string> = {
  hallucinated: 'text-error',
  adapted: 'text-success',
  escalated: 'text-success',
  skipped: 'text-neutral',
};
const GAP_RESPONSE_BG: Record<string, string> = {
  hallucinated: 'bg-error/10',
  adapted: 'bg-success/10',
  escalated: 'bg-success/10',
  skipped: 'bg-neutral/10',
};
const GAP_RESPONSE_ICONS: Record<string, LucideIcon> = {
  hallucinated: AlertTriangle,
  adapted: CheckCircle2,
  escalated: CheckCircle2,
  skipped: Circle,
};

// -- Distribution Summary --
function GapDistribution({ gaps }: { gaps: CapabilityGap[] }) {
  const distribution = useMemo(() => {
    const counts: Record<string, number> = { hallucinated: 0, adapted: 0, escalated: 0, skipped: 0 };
    for (const g of gaps) counts[g.response] = (counts[g.response] ?? 0) + 1;
    const total = gaps.length;
    return Object.entries(counts).map(([response, count]) => ({
      response, count, pct: total > 0 ? Math.round((count / total) * 100) : 0,
    }));
  }, [gaps]);

  return (
    <div className="mb-4 flex flex-wrap gap-3">
      {distribution.map(({ response, count, pct }) => {
        const Icon = GAP_RESPONSE_ICONS[response] ?? Circle;
        const color = GAP_RESPONSE_COLORS[response] ?? 'text-text-muted';
        const bg = GAP_RESPONSE_BG[response] ?? '';
        return (
          <div key={response} className={`flex items-center gap-2 rounded-lg border border-bg-elevated px-3 py-2 ${bg}`}>
            <Icon size={14} className={color} />
            <span className="text-sm font-medium text-text-primary">{gapResponseToLabel(response)}:</span>
            <span className="font-mono text-sm text-text-secondary">{count} ({pct}%)</span>
          </div>
        );
      })}
    </div>
  );
}

// -- Main Component --
export function GapsTab({ runId }: GapsTabProps) {
  const gapsQuery = useCapabilityGaps(runId);

  return (
    <QueryGuard query={gapsQuery} loadingFallback={<SectionLoading />}>
      {(gaps) => {
        if (gaps.length === 0) {
          return (
            <div>
              <h2 className="mb-3 text-lg font-semibold">
                CAPABILITY GAPS <span className="font-normal text-text-muted">(0 detected)</span>
              </h2>
              <EmptyState title="No capability gaps detected"
                description="All requested tools were available in the world." />
            </div>
          );
        }
        return (
          <div>
            <h2 className="mb-3 text-lg font-semibold">
              CAPABILITY GAPS <span className="font-normal text-text-muted">({gaps.length} detected)</span>
            </h2>
            <GapDistribution gaps={gaps} />
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-bg-elevated">
                    <th className="px-3 py-2 text-left text-xs font-medium uppercase text-text-muted">Event</th>
                    <th className="px-3 py-2 text-left text-xs font-medium uppercase text-text-muted">Agent</th>
                    <th className="px-3 py-2 text-left text-xs font-medium uppercase text-text-muted">Gap</th>
                    <th className="px-3 py-2 text-left text-xs font-medium uppercase text-text-muted">Response</th>
                  </tr>
                </thead>
                <tbody>
                  {gaps.map((gap) => {
                    const Icon = GAP_RESPONSE_ICONS[gap.response] ?? Circle;
                    const color = GAP_RESPONSE_COLORS[gap.response] ?? 'text-text-muted';
                    return (
                      <tr key={gap.event_id} className="border-b border-bg-elevated">
                        <td className="px-3 py-2">
                          <span className="font-mono text-xs text-text-muted">{truncateId(gap.event_id, 12)}</span>
                        </td>
                        <td className="px-3 py-2"><ActorBadge actorId={gap.actor_id} /></td>
                        <td className="px-3 py-2">
                          <span className="font-mono text-xs text-info">{gap.requested_tool}</span>
                          <p className="text-xs text-text-muted">{gap.description}</p>
                        </td>
                        <td className="px-3 py-2">
                          <span className={`inline-flex items-center gap-1 text-xs font-medium ${color}`}>
                            <Icon size={14} />
                            {gapResponseToLabel(gap.response)}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        );
      }}
    </QueryGuard>
  );
}
