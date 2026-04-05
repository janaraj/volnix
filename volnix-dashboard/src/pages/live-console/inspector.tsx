import { useMemo } from 'react';
import type { Run, WorldEvent } from '@/types/domain';
import { getActorRole, getActorType, getGovernanceScore } from '@/types/domain';
import { useActor } from '@/hooks/queries/use-actors';
import { useRunEvents } from '@/hooks/queries/use-events';
import { QueryGuard } from '@/components/feedback/query-guard';
import { SectionLoading } from '@/components/feedback/section-loading';
import { ActorBadge } from '@/components/domain/actor-badge';
import { ScoreBar } from '@/components/domain/score-bar';
import { ServiceBadge } from '@/components/domain/service-badge';
// formatters import removed — capitalize no longer used

interface InspectorProps {
  runId: string;
  selectedActorId: string | null;
  run: Run;
}

const BUDGET_LABELS: Record<string, string> = {
  api_calls: 'API Calls',
  llm_spend_usd: 'LLM Spend',
  world_actions: 'World Actions',
};

function AgentInspector({ runId, actorId }: { runId: string; actorId: string }) {
  const query = useActor(runId, actorId);

  return (
    <div className="space-y-4">
      <p className="text-xs uppercase text-text-muted">Agent Inspector</p>

      <QueryGuard query={query} loadingFallback={<SectionLoading />}>
        {(agent) => (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <ActorBadge actorId={agent.actor_id} role={getActorRole(agent)} />
              <span className="rounded bg-bg-elevated px-2 py-0.5 text-xs font-mono text-text-secondary">
                {getActorType(agent)}
              </span>
            </div>

            {/* Budget bars */}
            <div className="space-y-2">
              <p className="text-xs uppercase text-text-muted">Budgets</p>
              {Object.entries(BUDGET_LABELS).map(([key, label]) => {
                const budgetRemaining = (agent.definition?.budget as any)?.remaining ?? {};
                const budgetTotal = (agent.definition?.budget as any)?.total ?? {};
                const remaining = (budgetRemaining[key] as number) ?? 0;
                const total = (budgetTotal[key] as number) ?? 1;
                return <ScoreBar key={key} value={total > 0 ? remaining / total : 0} label={label} />;
              })}
            </div>

            {/* Action count + governance */}
            <div className="flex items-center gap-4 text-sm">
              <span className="text-text-muted">
                Actions: <span className="font-mono text-text-primary">{agent.action_count}</span>
              </span>
              {getGovernanceScore(agent) != null && (
                <span className="text-text-muted">
                  Governance: <span className="font-mono text-text-primary">{getGovernanceScore(agent)}</span>
                </span>
              )}
            </div>
          </div>
        )}
      </QueryGuard>
    </div>
  );
}

function RunInspector({ run, runId }: { run: Run; runId: string }) {
  const eventsQuery = useRunEvents(runId, { sort: 'desc', limit: 500 });
  const events = eventsQuery.data?.events ?? [];

  // Derive active actors from events (the truth of who acted)
  const INTERNAL = new Set(['world_compiler', 'animator', 'system', 'policy', 'budget', 'state', 'permission', 'responder']);
  const activeActors = useMemo(() => {
    const counts: Record<string, number> = {};
    events.forEach((e: WorldEvent) => {
      if (!INTERNAL.has(e.actor_id)) {
        counts[e.actor_id] = (counts[e.actor_id] || 0) + 1;
      }
    });
    return Object.entries(counts).sort(([, a], [, b]) => b - a);
  }, [events]);

  return (
    <div className="space-y-4">
      <p className="text-xs uppercase text-text-muted">Inspector</p>

      {/* Active agents — derived from events */}
      {activeActors.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs uppercase text-text-muted">Active Agents</p>
          <div className="space-y-1">
            {activeActors.map(([actorId, count]) => (
              <div key={actorId} className="flex items-center justify-between text-xs">
                <span className="text-info font-mono">{actorId}</span>
                <span className="font-mono text-text-muted">{count} actions</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Services list */}
      {(run.services ?? []).length > 0 && (
        <div className="space-y-2">
          <p className="text-xs uppercase text-text-muted">Services</p>
          <div className="flex flex-wrap gap-2">
            {(run.services ?? []).map((s) => (
              <ServiceBadge key={s.service_id} serviceId={s.service_id} tier={s.fidelity_tier} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function Inspector({ runId, selectedActorId, run }: InspectorProps) {
  if (selectedActorId) {
    return <AgentInspector runId={runId} actorId={selectedActorId} />;
  }

  return <RunInspector run={run} runId={runId} />;
}
