import type { Run, WorldEvent } from '@/types/domain';
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

function MetricCard({ title, value }: { title: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-bg-elevated bg-bg-surface p-4 transition-colors hover:border-border">
      <p className="text-xs font-medium uppercase text-text-muted">{title}</p>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
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
      <MetricCard
        title="Score"
        value={hasScore ? <ScoreGrade score={run.governance_score!} /> : <span className="text-text-muted">--</span>}
      />
      <MetricCard title="Events" value={run.event_count} />
      <MetricCard title="Actors" value={run.actor_count} />
      <MetricCard title="Services" value={run.services.length} />
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
          const keyEvents = data.items
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
                  className="flex items-center gap-3 rounded-lg border border-bg-elevated bg-bg-surface px-4 py-2 transition-colors hover:border-border hover:bg-bg-hover"
                >
                  <OutcomeIcon outcome={event.outcome} size={16} />
                  <ActorBadge actorId={event.actor_id} role={event.actor_role} />
                  <span className="flex-1 truncate text-sm text-text-secondary">
                    {event.action}
                  </span>
                  <TimestampCell iso={event.timestamp.wall_time} />
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
        {(scorecards) => {
          if (scorecards.length === 0) {
            return <EmptyState title="No agent scorecards available" />;
          }

          return (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {scorecards.map((card) => {
                const violationCount = card.scores.reduce(
                  (sum, s) => sum + s.violations.length,
                  0,
                );
                return (
                  <div
                    key={card.actor_id}
                    className="rounded-lg border border-bg-elevated bg-bg-surface p-4 transition-colors hover:border-border hover:bg-bg-hover"
                  >
                    <div className="mb-2">
                      <ActorBadge actorId={card.actor_id} />
                    </div>
                    <ScoreBar value={card.overall_score} />
                    <div className="mt-2 flex gap-4 text-xs text-text-muted">
                      <span>
                        Policy hits: {card.policy_hits.length}
                      </span>
                      <span>
                        Violations: {violationCount}
                      </span>
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
