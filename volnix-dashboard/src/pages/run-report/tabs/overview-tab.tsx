import type { LucideIcon } from 'lucide-react';
import { Shield, Zap, Users, Layers, Clock } from 'lucide-react';
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
import { capitalize } from '@/lib/formatters';

interface OverviewTabProps {
  runId: string;
  run: Run;
}

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
  const duration =
    run.started_at && run.completed_at
      ? Math.round((new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()) / 1000)
      : null;

  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
      <MetricCard
        title="Score"
        icon={Shield}
        value={hasScore ? <ScoreGrade score={run.governance_score!} /> : <span className="text-text-muted">&mdash;</span>}
      />
      <MetricCard title="Events" icon={Zap} value={run.event_count ?? '\u2014'} />
      <MetricCard title="Actors" icon={Users} value={run.actor_count ?? '\u2014'} />
      <MetricCard
        title="Duration"
        icon={Clock}
        value={duration != null ? <span className="font-mono">{duration}s</span> : '\u2014'}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Event Activity Breakdown
// ---------------------------------------------------------------------------

function EventBreakdown({ runId }: { runId: string }) {
  const eventsQuery = useRunEvents(runId);

  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold">Event Activity</h2>
      <QueryGuard query={eventsQuery} loadingFallback={<SectionLoading />}>
        {(data) => {
          const events = data.events;
          if (events.length === 0) {
            return <EmptyState title="No events recorded" />;
          }

          // Group by actor
          const byActor: Record<string, number> = {};
          events.forEach((e: WorldEvent) => {
            byActor[e.actor_id] = (byActor[e.actor_id] || 0) + 1;
          });

          // Group by outcome
          const byOutcome: Record<string, number> = {};
          events.forEach((e: WorldEvent) => {
            const o = e.outcome || 'success';
            byOutcome[o] = (byOutcome[o] || 0) + 1;
          });

          // Group by service
          const byService: Record<string, number> = {};
          events.forEach((e: WorldEvent) => {
            const s = e.service_id || 'unknown';
            byService[s] = (byService[s] || 0) + 1;
          });

          const maxActorCount = Math.max(...Object.values(byActor), 1);

          return (
            <div className="card p-4 space-y-4">
              {/* By Actor - horizontal bars */}
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-widest text-text-muted mb-2">By Agent</p>
                <div className="space-y-1.5">
                  {Object.entries(byActor)
                    .sort(([, a], [, b]) => b - a)
                    .map(([actor, count]) => (
                      <div key={actor} className="flex items-center gap-2">
                        <span className="w-36 truncate text-xs text-info font-mono">{actor}</span>
                        <div className="flex-1 h-5 bg-bg-elevated rounded overflow-hidden">
                          <div
                            className="h-full bg-info/25 rounded transition-all duration-300"
                            style={{ width: `${(count / maxActorCount) * 100}%` }}
                          />
                        </div>
                        <span className="font-mono text-xs text-text-secondary w-8 text-right">{count}</span>
                      </div>
                    ))}
                </div>
              </div>

              {/* By Outcome + By Service - side by side */}
              <div className="flex gap-8">
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-widest text-text-muted mb-2">By Outcome</p>
                  <div className="flex flex-wrap gap-3">
                    {Object.entries(byOutcome)
                      .sort(([, a], [, b]) => b - a)
                      .map(([outcome, count]) => (
                        <div key={outcome} className="flex items-center gap-1.5">
                          <OutcomeIcon outcome={outcome as any} size={12} />
                          <span className="text-xs text-text-secondary">
                            {outcome}: <span className="font-mono text-text-primary">{count}</span>
                          </span>
                        </div>
                      ))}
                  </div>
                </div>
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-widest text-text-muted mb-2">By Service</p>
                  <div className="flex flex-wrap gap-3">
                    {Object.entries(byService)
                      .sort(([, a], [, b]) => b - a)
                      .map(([service, count]) => (
                        <div key={service} className="flex items-center gap-1.5">
                          <Layers size={12} className="text-text-muted" />
                          <span className="text-xs text-text-secondary">
                            {service}: <span className="font-mono text-text-primary">{count}</span>
                          </span>
                        </div>
                      ))}
                  </div>
                </div>
              </div>
            </div>
          );
        }}
      </QueryGuard>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Key Events / Recent Activity
// ---------------------------------------------------------------------------

function KeyEvents({ runId }: { runId: string }) {
  const eventsQuery = useRunEvents(runId);

  return (
    <section>
      <QueryGuard query={eventsQuery} loadingFallback={<SectionLoading />}>
        {(data) => {
          const events = data.events;

          // First try non-success events (policy violations, denials, etc.)
          let keyEvents = events
            .filter((e: WorldEvent) => e.outcome && e.outcome !== 'success')
            .slice(0, MAX_KEY_EVENTS);

          const title = keyEvents.length > 0 ? 'Policy & Permission Events' : 'Recent Activity';

          // If all success, show last 5 events as recent activity
          if (keyEvents.length === 0) {
            keyEvents = events.slice(0, 5);
          }

          if (keyEvents.length === 0) {
            return null;
          }

          return (
            <>
              <h2 className="mb-3 text-lg font-semibold">{title}</h2>
              <div className="space-y-2">
                {keyEvents.map((event: WorldEvent) => (
                  <div
                    key={event.event_id}
                    className="card px-4 py-2.5 flex items-center gap-3"
                  >
                    <OutcomeIcon outcome={event.outcome ?? 'success'} size={14} />
                    <ActorBadge actorId={event.actor_id} role={event.actor_role} />
                    <span className="text-text-muted">&rarr;</span>
                    <span className="flex-1 truncate font-mono text-sm text-text-secondary">
                      {event.event_type?.startsWith('world.') ? (event.action ?? event.event_type) : event.event_type}
                    </span>
                    {event.outcome && event.outcome !== 'success' && (
                      <span className="text-xs font-medium uppercase text-error">
                        {event.outcome}
                      </span>
                    )}
                    <TimestampCell iso={event.timestamp?.wall_time ?? ''} />
                  </div>
                ))}
              </div>
            </>
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
                  <div key={actorId} className="card p-4">
                    <div className="mb-2">
                      <ActorBadge actorId={actorId} />
                    </div>
                    <ScoreBar value={overall / 100} label="Overall" />
                    <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1">
                      {Object.entries(scores)
                        .filter(([key, val]) => key !== 'overall' && key !== 'scores' && typeof val === 'number')
                        .map(([key, value]) => (
                          <div key={key} className="flex items-center justify-between text-xs">
                            <span className="text-text-muted truncate">{key.replace(/_/g, ' ')}</span>
                            <span className="font-mono text-text-secondary">{value as number}</span>
                          </div>
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
// Run Details section
// ---------------------------------------------------------------------------

function RunInfo({ run }: { run: Run }) {
  const duration =
    run.started_at && run.completed_at
      ? Math.round((new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()) / 1000)
      : null;

  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold">Run Details</h2>
      <div className="card p-4">
        <div className="grid grid-cols-2 gap-x-8 gap-y-2.5 text-sm md:grid-cols-4">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-widest text-text-muted">Duration</p>
            <p className="font-mono text-text-primary">{duration != null ? `${duration}s` : '—'}</p>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-widest text-text-muted">Mode</p>
            <p className="text-text-primary">{capitalize(run.mode)}</p>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-widest text-text-muted">Behavior</p>
            <p className="text-text-primary">{capitalize(run.config_snapshot?.behavior ?? 'static')}</p>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-widest text-text-muted">Reality</p>
            <p className="text-text-primary">{capitalize(run.reality_preset)}</p>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-widest text-text-muted">Fidelity</p>
            <p className="text-text-primary">{capitalize(run.fidelity_mode)}</p>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-widest text-text-muted">Services</p>
            <p className="font-mono text-text-primary">{(run.services ?? []).length}</p>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-widest text-text-muted">Seed</p>
            <p className="font-mono text-text-primary">{run.config_snapshot?.seed ?? '—'}</p>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-widest text-text-muted">Run ID</p>
            <p className="font-mono text-xs text-text-secondary">{run.run_id}</p>
          </div>
        </div>
      </div>
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
      <EventBreakdown runId={runId} />
      <KeyEvents runId={runId} />
      <AgentSummary runId={runId} />
      <RunInfo run={run} />
    </div>
  );
}
