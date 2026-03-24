import { useMemo } from 'react';
import { Eye, X } from 'lucide-react';
import { useEntities, useEntity } from '@/hooks/queries/use-entities';
import { useUrlState } from '@/hooks/use-url-state';
import { QueryGuard } from '@/components/feedback/query-guard';
import { SectionLoading } from '@/components/feedback/section-loading';
import { EmptyState } from '@/components/feedback/empty-state';
import { JsonViewer } from '@/components/domain/json-viewer';
import { TimestampCell } from '@/components/domain/timestamp-cell';
import { ActorBadge } from '@/components/domain/actor-badge';
import { cn } from '@/lib/cn';
import type { Entity, StateChange } from '@/types/domain';

interface EntitiesTabProps {
  runId: string;
}

const ENTITY_DEFAULTS = { entity: '', entity_type: '' };

const ENTITY_TYPE_OPTIONS: Record<string, string> = {
  '': 'All types',
  ticket: 'Tickets',
  customer: 'Customers',
  charge: 'Charges',
  message: 'Messages',
};

// ---------------------------------------------------------------------------
// StateChangeRow
// ---------------------------------------------------------------------------

function StateChangeRow({ change, isLast }: { change: StateChange; isLast: boolean }) {
  return (
    <div className="flex gap-3">
      {/* Timeline dot + connector */}
      <div className="flex flex-col items-center">
        <div className="mt-1.5 h-2 w-2 rounded-full bg-info" />
        {!isLast && <div className="w-px flex-1 border-l border-bg-elevated" />}
      </div>
      {/* Content */}
      <div className="pb-4">
        <p className="text-sm text-text-primary">
          <span className="font-medium">{change.field}</span>
          <span className="text-text-muted"> → </span>
          <span className="font-mono text-xs text-info">{String(change.new_value)}</span>
        </p>
        <p className="mt-0.5 flex items-center gap-1 text-xs text-text-muted">
          <TimestampCell iso={change.timestamp} />
          <span> · by </span>
          <ActorBadge actorId={change.actor_id} />
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// EntityDetailPanel
// ---------------------------------------------------------------------------

function EntityDetailPanel({
  runId,
  entityId,
  onClose,
}: {
  runId: string;
  entityId: string;
  onClose: () => void;
}) {
  const entityQuery = useEntity(runId, entityId);

  return (
    <div className="mt-4 rounded-lg border border-border bg-bg-surface p-4">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-lg font-semibold">
          Entity: <span className="font-mono">{entityId}</span>
        </h3>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close entity detail"
          className="rounded p-1 text-text-muted hover:bg-bg-hover hover:text-text-primary transition-colors"
        >
          <X size={18} />
        </button>
      </div>

      <QueryGuard query={entityQuery} loadingFallback={<SectionLoading />}>
        {(entity) => (
          <div className="space-y-6">
            {/* Current State */}
            <section>
              <h4 className="mb-2 text-sm font-medium uppercase text-text-muted">Current State</h4>
              <JsonViewer data={entity.fields} />
            </section>

            {/* History */}
            {entity.state_history && entity.state_history.length > 0 && (
              <section>
                <h4 className="mb-2 text-sm font-medium uppercase text-text-muted">History</h4>
                <div>
                  {entity.state_history.map((change, idx) => (
                    <StateChangeRow
                      key={change.event_id}
                      change={change}
                      isLast={idx === entity.state_history!.length - 1}
                    />
                  ))}
                </div>
              </section>
            )}
          </div>
        )}
      </QueryGuard>
    </div>
  );
}

// ---------------------------------------------------------------------------
// EntityCard
// ---------------------------------------------------------------------------

function EntityCard({
  entity,
  isSelected,
  onSelect,
}: {
  entity: Entity;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const keyFields = useMemo(
    () => Object.entries(entity.fields).slice(0, 4),
    [entity.fields],
  );
  const changeCount = entity.state_history?.length ?? 0;

  return (
    <div
      className={cn(
        'rounded-lg border bg-bg-surface p-4 transition-colors',
        isSelected ? 'border-info bg-bg-elevated' : 'border-bg-elevated hover:border-border',
      )}
    >
      <div className="mb-2 flex items-start justify-between">
        <div>
          <p className="font-mono text-sm font-semibold text-text-primary">{entity.entity_id}</p>
          <span className="mt-0.5 inline-block rounded-full bg-bg-elevated px-2 py-0.5 text-xs text-text-muted">
            {entity.entity_type}
          </span>
        </div>
        <button
          type="button"
          onClick={onSelect}
          className="flex items-center gap-1 rounded px-2 py-1 text-xs text-info hover:bg-bg-elevated transition-colors"
        >
          <Eye size={14} />
          View
        </button>
      </div>

      {/* Key fields */}
      <div className="mb-2 space-y-1">
        {keyFields.map(([key, value]) => (
          <div key={key} className="flex justify-between text-xs">
            <span className="text-text-muted">{key}</span>
            <span className="font-mono text-text-secondary">{String(value)}</span>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between text-xs text-text-muted">
        <span>{changeCount} change{changeCount !== 1 ? 's' : ''}</span>
        <TimestampCell iso={entity.updated_at} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// EntitiesTab
// ---------------------------------------------------------------------------

export function EntitiesTab({ runId }: EntitiesTabProps) {
  const [urlState, setUrlState] = useUrlState(ENTITY_DEFAULTS);
  const selectedEntityId = urlState.entity;

  const entitiesQuery = useEntities(runId, {
    entity_type: urlState.entity_type || undefined,
  });

  return (
    <div>
      <QueryGuard query={entitiesQuery} loadingFallback={<SectionLoading />}>
        {(data) => (
          <>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">
                ENTITIES <span className="font-normal text-text-muted">({data.total} total)</span>
              </h2>
              <select
                aria-label="Filter by entity type"
                value={urlState.entity_type}
                onChange={(e) => setUrlState({ entity_type: e.target.value })}
                className="rounded border border-bg-elevated bg-bg-surface px-3 py-1.5 text-sm text-text-primary"
              >
                {Object.entries(ENTITY_TYPE_OPTIONS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>

            {data.items.length === 0 ? (
              <EmptyState title="No entities match your filter" />
            ) : (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
                {data.items.map((entity) => (
                  <EntityCard
                    key={entity.entity_id}
                    entity={entity}
                    isSelected={entity.entity_id === selectedEntityId}
                    onSelect={() => setUrlState({ entity: entity.entity_id })}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </QueryGuard>

      {selectedEntityId && (
        <EntityDetailPanel
          runId={runId}
          entityId={selectedEntityId}
          onClose={() => setUrlState({ entity: '' })}
        />
      )}
    </div>
  );
}
