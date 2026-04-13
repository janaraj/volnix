import { useState } from 'react';
import { ChevronDown, ChevronRight, CheckCircle2, XCircle, Shield } from 'lucide-react';
import type { DecisionTraceResponse, DecisionTraceActivation, DecisionTraceAction } from '@/types/api';
import { useDecisionTrace } from '@/hooks/queries/use-decision-trace';
import { QueryGuard } from '@/components/feedback/query-guard';
import { SectionLoading } from '@/components/feedback/section-loading';
import { EmptyState } from '@/components/feedback/empty-state';
import { ActorBadge } from '@/components/domain/actor-badge';
import { cn } from '@/lib/cn';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pct(ratio: number): string {
  return `${(ratio * 100).toFixed(1)}%`;
}

function governanceLabel(gov: DecisionTraceAction['governance']): string | null {
  if (gov.permission === 'deny') return 'denied';
  if (gov.policy === 'block') return 'blocked';
  if (gov.policy === 'flag') return 'flagged';
  return null;
}

function governanceBadgeClass(label: string): string {
  if (label === 'denied' || label === 'blocked') return 'bg-error/15 text-error';
  if (label === 'flagged') return 'bg-warning/15 text-warning';
  return 'bg-neutral/15 text-text-muted';
}

// ---------------------------------------------------------------------------
// ActionRow
// ---------------------------------------------------------------------------

function ActionRow({ action }: { action: DecisionTraceAction }) {
  const govLabel = governanceLabel(action.governance);
  return (
    <tr className="border-b border-border/20 text-xs">
      <td className="py-1.5 pr-3 font-mono text-text-secondary">{action.tool_name}</td>
      <td className="py-1.5 pr-3 text-text-muted">{action.service}</td>
      <td className="py-1.5 pr-3">
        {action.committed ? (
          <CheckCircle2 size={13} className="text-success" />
        ) : (
          <XCircle size={13} className="text-error" />
        )}
      </td>
      <td className="py-1.5 pr-3">
        {govLabel && (
          <span className={cn('rounded px-1.5 py-0.5 text-xs font-medium', governanceBadgeClass(govLabel))}>
            {govLabel}
          </span>
        )}
      </td>
      <td className="py-1.5 text-text-muted">
        {action.effect
          ? <span className="font-mono">{action.effect.operation} {action.effect.entity_type} {action.effect.entity_id}</span>
          : action.learned && Object.keys(action.learned).length > 0
            ? <span className="italic text-info">read: {Object.keys(action.learned).join(', ')}</span>
            : null}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// ActivationRow (collapsible)
// ---------------------------------------------------------------------------

function ActivationRow({ activation }: { activation: DecisionTraceActivation }) {
  const [open, setOpen] = useState(true);
  const hasGov = activation.actions.some((a) => governanceLabel(a.governance) !== null);
  const committed = activation.actions.filter((a) => a.committed).length;

  return (
    <div className="rounded-lg border border-border/30 bg-bg-surface">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-bg-hover/40"
      >
        {open ? <ChevronDown size={14} className="shrink-0 text-text-muted" /> : <ChevronRight size={14} className="shrink-0 text-text-muted" />}
        <span className="font-mono text-xs text-text-muted">{activation.activation_id}</span>
        <ActorBadge actorId={activation.actor_id} />
        <span className={cn(
          'rounded px-1.5 py-0.5 text-xs',
          activation.reason === 'kickstart' ? 'bg-accent/15 text-accent' : 'bg-neutral/15 text-text-muted',
        )}>
          {activation.reason}
        </span>
        <span className="ml-auto text-xs text-text-muted">
          {committed}/{activation.actions.length} committed
          {hasGov && <Shield size={12} className="ml-2 inline text-warning" />}
        </span>
      </button>
      {open && activation.actions.length > 0 && (
        <div className="overflow-x-auto border-t border-border/20 px-4 pb-3 pt-2">
          <table className="w-full">
            <thead>
              <tr className="text-left text-xs text-text-muted">
                <th className="pb-1 pr-3 font-medium">Action</th>
                <th className="pb-1 pr-3 font-medium">Service</th>
                <th className="pb-1 pr-3 font-medium">OK</th>
                <th className="pb-1 pr-3 font-medium">Gov</th>
                <th className="pb-1 font-medium">Effect / Learned</th>
              </tr>
            </thead>
            <tbody>
              {activation.actions.map((a, i) => (
                <ActionRow key={`${a.tool_name}-${i}`} action={a} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {activation.world_response.animator_reactions.length > 0 && open && (
        <div className="border-t border-border/20 px-4 py-2">
          {activation.world_response.animator_reactions.map((r, i) => (
            <p key={i} className="text-xs italic text-text-muted">⟳ {r.summary}</p>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sections
// ---------------------------------------------------------------------------

function GameOutcomeBanner({ outcome }: { outcome: NonNullable<DecisionTraceResponse['game_outcome']> }) {
  return (
    <div className="rounded-lg border border-accent/30 bg-accent/5 px-4 py-3">
      <p className="text-sm font-semibold text-text-primary">
        Game outcome: <span className="text-accent">{outcome.reason}</span>
        {outcome.winner && <> — winner: <span className="text-success">{outcome.winner}</span></>}
      </p>
      <p className="mt-0.5 text-xs text-text-muted">
        {outcome.total_events} events
        {outcome.wall_clock_seconds != null && ` · ${outcome.wall_clock_seconds.toFixed(1)}s`}
      </p>
    </div>
  );
}

function InformationTable({ analysis }: { analysis: DecisionTraceResponse['information_analysis'] }) {
  const actors = Object.keys(analysis);
  if (actors.length === 0) return null;
  return (
    <section>
      <h2 className="mb-3 text-base font-semibold">Information Coverage</h2>
      <div className="overflow-x-auto rounded-lg border border-border/30">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/30 bg-bg-elevated/30 text-xs font-medium uppercase text-text-muted">
              <th className="px-3 py-2 text-left">Actor</th>
              <th className="px-3 py-2 text-right">Queried</th>
              <th className="px-3 py-2 text-right">Available</th>
              <th className="px-3 py-2 text-right">Coverage</th>
              <th className="px-3 py-2 text-right">Utilized</th>
              <th className="px-3 py-2 text-right">Utilization</th>
              <th className="px-3 py-2 text-left">Services</th>
            </tr>
          </thead>
          <tbody>
            {actors.map((id) => {
              const a = analysis[id];
              return (
                <tr key={id} className="border-b border-border/20">
                  <td className="px-3 py-2"><ActorBadge actorId={id} /></td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{a.entities_queried}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{a.entities_available > 0 ? a.entities_available : '—'}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{a.entities_available > 0 ? pct(a.coverage_ratio) : '—'}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{a.entities_utilized}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{a.entities_queried > 0 && a.utilization_ratio != null ? pct(a.utilization_ratio) : '—'}</td>
                  <td className="px-3 py-2 text-xs text-text-muted">{a.unique_services_used.join(', ')}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function GovernanceTable({ summary }: { summary: DecisionTraceResponse['governance_summary'] }) {
  const actors = Object.keys(summary);
  if (actors.length === 0) return null;
  return (
    <section>
      <h2 className="mb-3 text-base font-semibold">Governance Pressure</h2>
      <div className="overflow-x-auto rounded-lg border border-border/30">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/30 bg-bg-elevated/30 text-xs font-medium uppercase text-text-muted">
              <th className="px-3 py-2 text-left">Actor</th>
              <th className="px-3 py-2 text-right">Actions</th>
              <th className="px-3 py-2 text-right">Policy hits</th>
              <th className="px-3 py-2 text-right">Policy rate</th>
              <th className="px-3 py-2 text-right">Perm denied</th>
              <th className="px-3 py-2 text-right">Rejection rate</th>
              <th className="px-3 py-2 text-right">Budget used</th>
            </tr>
          </thead>
          <tbody>
            {actors.map((id) => {
              const g = summary[id];
              return (
                <tr key={id} className="border-b border-border/20">
                  <td className="px-3 py-2"><ActorBadge actorId={id} /></td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{g.total_world_actions}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{g.policies_triggered}</td>
                  <td className={cn('px-3 py-2 text-right font-mono text-xs', (g.policy_pressure_rate ?? 0) > 0.3 ? 'text-warning' : '')}>
                    {g.total_world_actions > 0 && g.policy_pressure_rate != null ? pct(g.policy_pressure_rate) : '—'}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{g.permissions_denied}</td>
                  <td className={cn('px-3 py-2 text-right font-mono text-xs', (g.permission_rejection_rate ?? 0) > 0.3 ? 'text-error' : '')}>
                    {g.permissions_checked > 0 && g.permission_rejection_rate != null ? pct(g.permission_rejection_rate) : '—'}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">
                    {g.budget_total != null && g.budget_total > 0 && g.budget_utilization != null ? pct(g.budget_utilization) : `${g.budget_consumed}`}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// DecisionTraceTab
// ---------------------------------------------------------------------------

export function DecisionTraceTab({ runId }: { runId: string }) {
  const traceQuery = useDecisionTrace(runId);

  return (
    <QueryGuard query={traceQuery} loadingFallback={<SectionLoading />}>
      {(data: DecisionTraceResponse) => {
        if (data.activations.length === 0 && Object.keys(data.information_analysis).length === 0) {
          return <EmptyState title="No trace data" description="This run produced no decision trace." />;
        }
        return (
          <div className="space-y-6">
            {data.game_outcome && <GameOutcomeBanner outcome={data.game_outcome} />}

            {data.domain_narrative && data.domain_narrative.length > 0 && (
              <section className="rounded-lg border border-border/30 bg-bg-surface px-4 py-3">
                <h2 className="mb-2 text-base font-semibold">Narrative</h2>
                <ul className="space-y-1">
                  {data.domain_narrative.map((line, i) => (
                    <li key={i} className="text-sm text-text-secondary">{line}</li>
                  ))}
                </ul>
              </section>
            )}

            {data.activations.length > 0 && (
              <section>
                <h2 className="mb-3 text-base font-semibold">
                  Activation Timeline
                  <span className="ml-2 font-normal text-sm text-text-muted">({data.activations.length})</span>
                </h2>
                <div className="space-y-2">
                  {data.activations.map((act) => (
                    <ActivationRow key={act.activation_id} activation={act} />
                  ))}
                </div>
              </section>
            )}

            <InformationTable analysis={data.information_analysis} />
            <GovernanceTable summary={data.governance_summary} />
          </div>
        );
      }}
    </QueryGuard>
  );
}
