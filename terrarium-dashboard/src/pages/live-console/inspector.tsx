import type { Run } from '@/types/domain';
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
              <ActorBadge actorId={agent.actor_id} role={agent.role} />
              <span className="rounded bg-bg-elevated px-2 py-0.5 text-xs font-mono text-text-secondary">
                {agent.actor_type}
              </span>
            </div>

            {/* Budget bars */}
            <div className="space-y-2">
              <p className="text-xs uppercase text-text-muted">Budgets</p>
              {Object.entries(BUDGET_LABELS).map(([key, label]) => {
                const remaining = agent.budget_remaining[key as keyof typeof agent.budget_remaining] ?? 0;
                const total = agent.budget_total[key as keyof typeof agent.budget_total] ?? 1;
                return <ScoreBar key={key} value={total > 0 ? remaining / total : 0} label={label} />;
              })}
            </div>

            {/* Action count + governance */}
            <div className="flex items-center gap-4 text-sm">
              <span className="text-text-muted">
                Actions: <span className="font-mono text-text-primary">{agent.action_count}</span>
              </span>
              {agent.governance_score != null && (
                <span className="text-text-muted">
                  Governance: <span className="font-mono text-text-primary">{agent.governance_score}</span>
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
  return (
    <div className="space-y-4">
      <p className="text-xs uppercase text-text-muted">Inspector</p>

      {/* Mode / preset / behavior badges */}
      <div className="flex flex-wrap gap-2">
        <span className="rounded bg-bg-elevated px-2 py-0.5 text-xs font-mono text-text-secondary">
          {capitalize(run.mode)}
        </span>
        <span className="rounded bg-bg-elevated px-2 py-0.5 text-xs font-mono text-text-secondary">
          {capitalize(run.reality_preset)}
        </span>
        <span className="rounded bg-bg-elevated px-2 py-0.5 text-xs font-mono text-text-secondary">
          {capitalize(run.config_snapshot?.behavior ?? 'static')}
        </span>
      </div>

      {/* Counts */}
      <div className="flex items-center gap-4 text-sm">
        <span className="text-text-muted">
          Actors: <span className="font-mono text-text-primary">{run.actor_count ?? 0}</span>
        </span>
        <span className="text-text-muted">
          Services: <span className="font-mono text-text-primary">{(run.services ?? []).length}</span>
        </span>
      </div>

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
