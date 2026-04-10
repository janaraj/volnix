import { useMemo } from 'react';
import type { Run, WorldEvent } from '@/types/domain';
import { getActorRole, getActorType, getGovernanceScore } from '@/types/domain';
import { useActor } from '@/hooks/queries/use-actors';
import { QueryGuard } from '@/components/feedback/query-guard';
import { SectionLoading } from '@/components/feedback/section-loading';
import { ActorBadge } from '@/components/domain/actor-badge';
import { ScoreBar } from '@/components/domain/score-bar';
import { ServiceBadge } from '@/components/domain/service-badge';

interface InspectorProps {
  runId: string;
  selectedActorId: string | null;
  run: Run;
  events: WorldEvent[];
}

const BUDGET_LABELS: Record<string, string> = {
  api_calls: 'API',
  llm_spend_usd: 'LLM',
  world_actions: 'World',
};

const INTERNAL_ACTORS = new Set([
  'world_compiler',
  'animator',
  'system',
  'policy',
  'budget',
  'state',
  'permission',
  'responder',
]);

// ---------------------------------------------------------------------------
// Section wrapper — small label + inline content
// ---------------------------------------------------------------------------

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-shrink-0 items-center gap-2">
      <span className="text-[9px] font-semibold uppercase tracking-wider text-text-muted">
        {label}
      </span>
      <div className="flex items-center gap-2">{children}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AgentInspectorBar — compact horizontal detail for a selected actor
// ---------------------------------------------------------------------------

function AgentInspectorBar({ runId, actorId }: { runId: string; actorId: string }) {
  const query = useActor(runId, actorId);

  return (
    <QueryGuard query={query} loadingFallback={<SectionLoading />}>
      {(agent) => {
        const budgetRemaining = (agent.definition?.budget as any)?.remaining ?? {};
        const budgetTotal = (agent.definition?.budget as any)?.total ?? {};
        return (
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <Section label="Agent">
              <ActorBadge actorId={agent.actor_id} role={getActorRole(agent)} />
              <span className="rounded bg-bg-elevated px-1.5 py-0.5 font-mono text-[10px] text-text-secondary">
                {getActorType(agent)}
              </span>
            </Section>

            <Section label="Budgets">
              <div className="flex items-center gap-3">
                {Object.entries(BUDGET_LABELS).map(([key, label]) => {
                  const remaining = (budgetRemaining[key] as number) ?? 0;
                  const total = (budgetTotal[key] as number) ?? 1;
                  return (
                    <div key={key} className="flex items-center gap-1.5">
                      <span className="text-[10px] text-text-muted">{label}</span>
                      <div className="w-16">
                        <ScoreBar value={total > 0 ? remaining / total : 0} label="" />
                      </div>
                    </div>
                  );
                })}
              </div>
            </Section>

            <Section label="Actions">
              <span className="font-mono text-xs text-text-primary">{agent.action_count}</span>
            </Section>

            {getGovernanceScore(agent) != null && (
              <Section label="Governance">
                <span className="font-mono text-xs text-text-primary">
                  {getGovernanceScore(agent)}
                </span>
              </Section>
            )}
          </div>
        );
      }}
    </QueryGuard>
  );
}

// ---------------------------------------------------------------------------
// RunInspectorBar — compact horizontal overview when no actor selected
// ---------------------------------------------------------------------------

function RunInspectorBar({ run, events }: { run: Run; events: WorldEvent[] }) {
  const activeActors = useMemo(() => {
    const counts: Record<string, number> = {};
    events.forEach((e: WorldEvent) => {
      if (!INTERNAL_ACTORS.has(e.actor_id)) {
        counts[e.actor_id] = (counts[e.actor_id] || 0) + 1;
      }
    });
    return Object.entries(counts).sort(([, a], [, b]) => b - a);
  }, [events]);

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
      {activeActors.length > 0 && (
        <Section label="Active Agents">
          <div className="flex flex-wrap items-center gap-2">
            {activeActors.map(([actorId, count]) => (
              <span
                key={actorId}
                className="inline-flex items-center gap-1 rounded bg-bg-elevated px-2 py-0.5 font-mono text-[11px]"
              >
                <span className="text-info">{actorId}</span>
                <span className="text-text-muted">· {count}</span>
              </span>
            ))}
          </div>
        </Section>
      )}

      {(run.services ?? []).length > 0 && (
        <Section label="Services">
          <div className="flex flex-wrap items-center gap-2">
            {(run.services ?? []).map((s) => (
              <ServiceBadge key={s.service_id} serviceId={s.service_id} tier={s.fidelity_tier} />
            ))}
          </div>
        </Section>
      )}

      {activeActors.length === 0 && (run.services ?? []).length === 0 && (
        <span className="text-[11px] italic text-text-muted">
          No activity yet — waiting for events...
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Exported Inspector — compact horizontal strip for the bottom of Live Console
// ---------------------------------------------------------------------------

export function Inspector({ runId, selectedActorId, run, events }: InspectorProps) {
  return (
    <div className="flex items-start gap-4 px-4 py-2.5">
      <span className="flex-shrink-0 text-[10px] font-bold uppercase tracking-wider text-text-muted">
        Inspector
      </span>
      <div className="min-w-0 flex-1 overflow-x-auto">
        {selectedActorId ? (
          <AgentInspectorBar runId={runId} actorId={selectedActorId} />
        ) : (
          <RunInspectorBar run={run} events={events} />
        )}
      </div>
    </div>
  );
}
