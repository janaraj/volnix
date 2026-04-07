import { X, GitBranch } from 'lucide-react';
import type { Run } from '@/types/domain';
import { getActorRole, getActorType, getGovernanceScore } from '@/types/domain';
import { useRunEvent } from '@/hooks/queries/use-events';
import { useActor } from '@/hooks/queries/use-actors';
import { QueryGuard } from '@/components/feedback/query-guard';
import { SectionLoading } from '@/components/feedback/section-loading';
import { OutcomeIcon } from '@/components/domain/outcome-icon';
import { ActorBadge } from '@/components/domain/actor-badge';
import { TimestampCell } from '@/components/domain/timestamp-cell';
import { EnforcementBadge } from '@/components/domain/enforcement-badge';
import { JsonViewer } from '@/components/domain/json-viewer';
import { EntityLink } from '@/components/domain/entity-link';
import { FidelityIndicator } from '@/components/domain/fidelity-indicator';
import { ScoreBar } from '@/components/domain/score-bar';
import { ServiceBadge } from '@/components/domain/service-badge';
import { capitalize, formatCurrency, truncateId } from '@/lib/formatters';

interface ContextViewProps {
  runId: string;
  run: Run;
  selectedEventId: string | null;
  selectedActorId: string | null;
  eventCount: number;
  onSelectEvent: (eventId: string) => void;
  onClearSelection: () => void;
}

const BUDGET_LABELS: Record<string, string> = {
  api_calls: 'API Calls',
  llm_spend_usd: 'LLM Spend',
  world_actions: 'World Actions',
};

function CausalLink({ eventId, onSelect }: { eventId: string; onSelect: (id: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onSelect(eventId)}
      className="font-mono text-xs text-info hover:underline underline-offset-2"
      title={eventId}
    >
      {truncateId(eventId, 12)}
    </button>
  );
}

function RunOverviewView({ run, eventCount }: { run: Run; eventCount: number }) {
  const agentCount = ((run.world_def as any)?.actor_specs ?? (run.world_def as any)?.actors ?? []).length;
  const serviceCount = (run.services ?? []).length;

  return (
    <div className="space-y-4">
      {/* Header — status + badges already shown in RunHeaderBar, just show world name */}
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-text-secondary">{capitalize(run.world_def.name)}</span>
        <div className="flex items-center gap-2">
          <span className="rounded-md border border-accent/40 px-2 py-0.5 text-xs font-medium text-accent">
            {capitalize(run.mode)}
          </span>
          <span className="rounded-md border border-warning/40 px-2 py-0.5 text-xs font-medium text-warning">
            {capitalize(run.config_snapshot?.behavior ?? 'static')}
          </span>
        </div>
      </div>

      {/* Telemetry strip — compact 4-column row */}
      <div className="grid grid-cols-4 gap-2">
        <div className="rounded border border-border p-2.5">
          <p className="text-[10px] uppercase tracking-wider text-text-muted">Tick</p>
          <p className="text-lg font-semibold font-mono text-text-primary">
            {(run.current_tick ?? 0) > 0 ? run.current_tick : <span className="text-info">Live</span>}
          </p>
        </div>
        <div className="rounded border border-border p-2.5">
          <p className="text-[10px] uppercase tracking-wider text-text-muted">Agents</p>
          <p className="text-lg font-semibold font-mono text-text-primary">{agentCount}</p>
        </div>
        <div className="rounded border border-border p-2.5">
          <p className="text-[10px] uppercase tracking-wider text-text-muted">Events</p>
          <p className="text-lg font-semibold font-mono text-text-primary">{eventCount}</p>
        </div>
        <div className="rounded border border-border p-2.5">
          <p className="text-[10px] uppercase tracking-wider text-text-muted">Services</p>
          <p className="text-lg font-semibold font-mono text-text-primary">{serviceCount}</p>
        </div>
      </div>

      {/* Services list */}
      {serviceCount > 0 && (
        <div className="flex flex-wrap gap-2">
          {(run.services ?? []).map((s) => (
            <ServiceBadge key={s.service_id} serviceId={s.service_id} tier={s.fidelity_tier} />
          ))}
        </div>
      )}
    </div>
  );
}

function EventDetailView({
  runId,
  eventId,
  onSelectEvent,
  onClearSelection,
}: {
  runId: string;
  eventId: string;
  onSelectEvent: (id: string) => void;
  onClearSelection: () => void;
}) {
  const query = useRunEvent(runId, eventId);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">
          Event: <span className="font-mono">{truncateId(eventId)}</span>
        </h3>
        <button
          type="button"
          aria-label="Close detail"
          onClick={onClearSelection}
          className="rounded p-1 hover:bg-bg-hover transition-colors"
        >
          <X size={16} />
        </button>
      </div>

      <QueryGuard query={query} loadingFallback={<SectionLoading />}>
        {(data) => {
          const event = data.event;
          const ancestors = data.causal_ancestors ?? [];
          const descendants = data.causal_descendants ?? [];
          return (
          <div className="space-y-4">
            {/* Summary line */}
            <div className="flex items-center gap-2 text-sm">
              {event.event_type?.startsWith('world.') ? (
                <>
                  <ActorBadge actorId={event.actor_id} role={event.actor_role} />
                  <span className="text-text-muted">&rarr;</span>
                  <span className="font-mono text-text-secondary">{event.action ?? event.event_type}</span>
                  <span className="text-text-muted">&rarr;</span>
                  <OutcomeIcon outcome={event.outcome ?? 'success'} />
                  <span className="text-xs font-medium uppercase">{event.outcome ?? ''}</span>
                </>
              ) : (
                <>
                  <span className="font-mono text-warning">{event.event_type}</span>
                  <span className="text-text-muted">&middot;</span>
                  <ActorBadge actorId={event.actor_id} role={event.actor_role} />
                </>
              )}
            </div>

            {/* Timestamp */}
            <TimestampCell iso={event.timestamp?.wall_time ?? ''} />

            {/* Type-specific detail */}
            {event.event_type?.startsWith('budget.') ? (
              <div className="space-y-2">
                <div className="grid grid-cols-3 gap-3 font-mono text-sm">
                  <div className="space-y-1">
                    <p className="text-xs uppercase text-text-muted">Budget Type</p>
                    <p className="text-text-primary">{event.budget_type ?? event.budget_delta !== undefined ? 'api_calls' : '-'}</p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs uppercase text-text-muted">Amount</p>
                    <p className="text-warning">-{event.amount ?? event.budget_delta ?? 0}</p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs uppercase text-text-muted">Remaining</p>
                    <p className="text-text-primary">{event.remaining ?? event.budget_remaining ?? 0}</p>
                  </div>
                </div>
                <p className="text-xs text-text-muted">Triggered by: <span className="font-mono text-text-secondary">{event.action}</span></p>
              </div>
            ) : event.event_type?.startsWith('policy.') ? (
              <div className="space-y-2">
                <div className="space-y-1">
                  <p className="text-xs uppercase text-text-muted">Policy</p>
                  <p className="font-mono text-sm text-text-primary">{event.policy_id ?? event.policy_hit?.policy_name ?? '-'}</p>
                </div>
                <p className="text-xs text-text-muted">Triggered by: <span className="font-mono text-text-secondary">{event.action}</span> on <span className="text-text-secondary">{event.service_id}</span></p>
              </div>
            ) : (
              <>
                {/* World event: Input / Output */}
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  <div className="space-y-1">
                    <p className="text-xs uppercase text-text-muted">Input</p>
                    <JsonViewer data={event.input_data} />
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs uppercase text-text-muted">Output</p>
                    <JsonViewer data={event.response_body} />
                  </div>
                </div>

                {/* Budget impact */}
                <div className="space-y-1">
                  <p className="text-xs uppercase text-text-muted">Budget Impact</p>
                  <div className="flex items-center gap-3 font-mono text-sm">
                    <span className="text-text-secondary">
                      Delta: <span className="text-warning">{formatCurrency(event.budget_delta ?? 0)}</span>
                    </span>
                    <span className="text-text-secondary">
                      Remaining: <span className="font-mono">{formatCurrency(event.budget_remaining ?? 0)}</span>
                    </span>
                  </div>
                </div>
              </>
            )}

            {/* Policy hit */}
            {event.policy_hit && (
              <div className="space-y-1">
                <p className="text-xs uppercase text-text-muted">Policy</p>
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-mono text-text-secondary">{event.policy_hit.policy_name}</span>
                  <EnforcementBadge enforcement={event.policy_hit.enforcement} />
                  {event.policy_hit.resolution && (
                    <span className="text-xs text-text-muted">{event.policy_hit.resolution}</span>
                  )}
                </div>
              </div>
            )}

            {/* Entity IDs */}
            {(event.entity_ids ?? []).length > 0 && (
              <div className="space-y-1">
                <p className="text-xs uppercase text-text-muted">Entities</p>
                <div className="flex flex-wrap gap-2">
                  {(event.entity_ids ?? []).map((eid) => (
                    <EntityLink key={eid} runId={runId} entityId={eid} />
                  ))}
                </div>
              </div>
            )}

            {/* Causal chain */}
            {(ancestors.length > 0 || descendants.length > 0) && (
              <div className="space-y-2">
                <p className="flex items-center gap-1 text-xs uppercase text-text-muted">
                  <GitBranch size={12} /> Causal Chain
                </p>
                {ancestors.length > 0 && (
                  <div className="space-y-1">
                    <p className="text-xs text-text-muted">Caused by:</p>
                    <div className="flex flex-wrap gap-2">
                      {ancestors.map((pid) => (
                        <CausalLink key={pid} eventId={pid} onSelect={onSelectEvent} />
                      ))}
                    </div>
                  </div>
                )}
                {descendants.length > 0 && (
                  <div className="space-y-1">
                    <p className="text-xs text-text-muted">Caused:</p>
                    <div className="flex flex-wrap gap-2">
                      {descendants.map((cid) => (
                        <CausalLink key={cid} eventId={cid} onSelect={onSelectEvent} />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Fidelity — only for world events */}
            {event.event_type?.startsWith('world.') && (
              <FidelityIndicator tier={event.fidelity_tier ?? 2} source={event.fidelity?.fidelity_source ?? undefined} />
            )}
          </div>
          );
        }}
      </QueryGuard>
    </div>
  );
}

function AgentDetailView({
  runId,
  actorId,
  onClearSelection,
}: {
  runId: string;
  actorId: string;
  onClearSelection: () => void;
}) {
  const query = useActor(runId, actorId);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">
          Agent: <span className="font-mono">{truncateId(actorId)}</span>
        </h3>
        <button
          type="button"
          aria-label="Close detail"
          onClick={onClearSelection}
          className="rounded p-1 hover:bg-bg-hover transition-colors"
        >
          <X size={16} />
        </button>
      </div>

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

export function ContextView({
  runId,
  run,
  selectedEventId,
  selectedActorId,
  eventCount,
  onSelectEvent,
  onClearSelection,
}: ContextViewProps) {
  if (selectedEventId) {
    return (
      <EventDetailView
        runId={runId}
        eventId={selectedEventId}
        onSelectEvent={onSelectEvent}
        onClearSelection={onClearSelection}
      />
    );
  }

  if (selectedActorId) {
    return (
      <AgentDetailView
        runId={runId}
        actorId={selectedActorId}
        onClearSelection={onClearSelection}
      />
    );
  }

  return <RunOverviewView run={run} eventCount={eventCount} />;
}
