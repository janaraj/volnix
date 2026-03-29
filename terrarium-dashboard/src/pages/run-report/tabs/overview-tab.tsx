import type { LucideIcon } from 'lucide-react';
import { Shield, Zap, Users, Layers } from 'lucide-react';
import type { Run, WorldEvent } from '@/types/domain';
import type { ScorecardResponse } from '@/types/api';
import { useRunEvents } from '@/hooks/queries/use-events';
import { useScorecard } from '@/hooks/queries/use-scorecard';
import { ScoreGrade } from '@/components/domain/score-grade';
import { OutcomeIcon } from '@/components/domain/outcome-icon';
import { ActorBadge } from '@/components/domain/actor-badge';
import { TimestampCell } from '@/components/domain/timestamp-cell';
import { ScoreBar } from '@/components/domain/score-bar';
import { QueryGuard } from '@/components/feedback/query-guard';
import { SectionLoading } from '@/components/feedback/section-loading';
import { EmptyState } from '@/components/feedback/empty-state';

interface OverviewTabProps {
  runId: string;
  run: Run;
}

const KEY_EVENT_TYPES = new Set([
  'policy_hold',
  'policy_block',
  'policy_escalate',
  'permission_denied',
  'capability_gap',
  'budget_exhausted',
  'budget_warning',
]);

const MAX_KEY_EVENTS = 10;

// ---------------------------------------------------------------------------
// MetricCard
// ---------------------------------------------------------------------------

function MetricCard({ title, value, icon: Icon }: { title: string; value: React.ReactNode; icon?: LucideIcon }) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-1.5">
        {Icon && <Icon size={12} className="text-text-muted" />}
        <p className="text-[10px] font-semibold uppercase tracking-widest text-text-muted">{title}</p>
      </div>
      <div className="mt-1.5 text-2xl font-bold tabular-nums">{value}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// MetricCards section
// ---------------------------------------------------------------------------

function MetricCards({ run }: { run: Run }) {
  const hasScore = run.governance_score != null;

  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
      <MetricCard title="Score" icon={Shield} value={hasScore ? <ScoreGrade score={run.governance_score!} /> : <span className="text-text-muted">&mdash;</span>} />
      <MetricCard title="Events" icon={Zap} value={run.event_count != null ? run.event_count : '\u2014'} />
      <MetricCard title="Actors" icon={Users} value={run.actor_count != null ? run.actor_count : '\u2014'} />
      <MetricCard title="Services" icon={Layers} value={(run.services ?? []).length > 0 ? (run.services ?? []).length : '\u2014'} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Key Events section
// ---------------------------------------------------------------------------

function KeyEvents({ runId }: { runId: string }) {
  const eventsQuery = useRunEvents(runId);

  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold">Key Events</h2>
      <QueryGuard query={eventsQuery} loadingFallback={<SectionLoading />}>
        {(data) => {
          const keyEvents = data.events
            .filter((e: WorldEvent) => KEY_EVENT_TYPES.has(e.event_type))
            .slice(0, MAX_KEY_EVENTS);

          if (keyEvents.length === 0) {
            return <EmptyState title="No key events recorded" />;
          }

          return (
            <div className="space-y-2">
              {keyEvents.map((event: WorldEvent) => (
                <div
                  key={event.event_id}
                  className="card px-4 py-2.5 flex items-center gap-3"
                >
                  <OutcomeIcon outcome={event.outcome ?? 'success'} size={16} />
                  <ActorBadge actorId={event.actor_id} role={event.actor_role} />
                  <span className="flex-1 truncate text-sm text-text-secondary">
                    {event.action ?? event.event_type}
                  </span>
                  <TimestampCell iso={event.timestamp?.wall_time ?? ''} />
                </div>
              ))}
            </div>
          );
        }}
      </QueryGuard>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Agent Summary section
// ---------------------------------------------------------------------------

function AgentSummary({ runId }: { runId: string }) {
  const scorecardQuery = useScorecard(runId);

  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold">Agent Summary</h2>
      <QueryGuard query={scorecardQuery} loadingFallback={<SectionLoading />}>
        {(data: ScorecardResponse) => {
          const actorIds = Object.keys(data.per_actor);
          if (actorIds.length === 0) {
            return <EmptyState title="No agent scorecards available" />;
          }

          return (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {actorIds.map((actorId) => {
                const scores = data.per_actor[actorId];
                const overall = scores['overall'] ?? 0;
                return (
                  <div
                    key={actorId}
                    className="card elevate-on-hover p-4"
                  >
                    <div className="mb-2">
                      <ActorBadge actorId={actorId} />
                    </div>
                    <ScoreBar value={overall / 100} />
                    <div className="mt-2 flex gap-4 text-xs text-text-muted">
                      {Object.entries(scores)
                        .filter(([key, val]) => key !== 'overall' && key !== 'scores' && typeof val === 'number')
                        .map(([key, value]) => (
                          <span key={key}>
                            {key}: {value}
                          </span>
                        ))}
                    </div>
                  </div>
                );
              })}
            </div>
          );
        }}
      </QueryGuard>
    </section>
  );
}

// ---------------------------------------------------------------------------
// OverviewTab
// ---------------------------------------------------------------------------

export function OverviewTab({ runId, run }: OverviewTabProps) {
  return (
    <div className="space-y-6">
      <MetricCards run={run} />
      <KeyEvents runId={runId} />
      <AgentSummary runId={runId} />
    </div>
  );
}
