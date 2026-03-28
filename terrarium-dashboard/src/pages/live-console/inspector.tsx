import type { Run } from '@/types/domain';
import { getActorRole, getActorType, getGovernanceScore } from '@/types/domain';
import { useActor } from '@/hooks/queries/use-actors';
import { QueryGuard } from '@/components/feedback/query-guard';
import { SectionLoading } from '@/components/feedback/section-loading';
import { ActorBadge } from '@/components/domain/actor-badge';
import { ScoreBar } from '@/components/domain/score-bar';
import { ServiceBadge } from '@/components/domain/service-badge';
import { capitalize } from '@/lib/formatters';

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

function RunInspector({ run }: { run: Run }) {
  const actorSpecs = run.world_def?.actor_specs ?? run.world_def?.actors ?? [];

  return (
    <div className="space-y-4">
      <p className="text-xs uppercase text-text-muted">Inspector</p>

      {/* Mode / preset / behavior badges */}
      <div className="flex flex-wrap gap-2">
        <span className="rounded-md border border-accent/20 bg-accent/10 px-2 py-0.5 text-xs font-medium text-accent">
          {capitalize(run.mode)}
        </span>
        <span className="rounded-md border border-warning/20 bg-warning/10 px-2 py-0.5 text-xs font-medium text-warning">
          {capitalize(run.config_snapshot?.behavior ?? 'static')}
        </span>
      </div>

      {/* Actors */}
      {actorSpecs.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs uppercase text-text-muted">Actors</p>
          <div className="space-y-1">
            {actorSpecs.map((a: Record<string, unknown>, i: number) => (
              <div key={a.id as string ?? i} className="flex items-center justify-between text-xs">
                <span className="text-text-primary">
                  {a.id as string ?? capitalize(a.role as string ?? '')}
                </span>
                <div className="flex items-center gap-1.5">
                  {(a.count as number) > 1 && (
                    <span className="font-mono text-text-muted">&times;{a.count as number}</span>
                  )}
                  <span className={
                    (a.type as string) === 'external'
                      ? 'rounded bg-info/10 px-1.5 py-0.5 text-info'
                      : 'rounded bg-bg-elevated px-1.5 py-0.5 text-text-muted'
                  }>
                    {a.type as string}
                  </span>
                </div>
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

  return <RunInspector run={run} />;
}
