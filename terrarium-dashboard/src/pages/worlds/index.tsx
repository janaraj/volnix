import { useNavigate } from 'react-router';
import { Globe, Box, Users, Layers, Hash, Clock, ChevronRight } from 'lucide-react';
import { PageHeader } from '@/components/layout/page-header';
import { QueryGuard } from '@/components/feedback/query-guard';
import { EmptyState } from '@/components/feedback/empty-state';
import { useWorlds } from '@/hooks/queries/use-worlds';
import { formatRelativeTime, truncateId, capitalize } from '@/lib/formatters';
import { cn } from '@/lib/cn';
import type { World } from '@/types/domain';

function StatusBadge({ status }: { status: World['status'] }) {
  if (status === 'created') {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-warning/20 bg-warning/10 px-2.5 py-0.5 text-xs font-medium text-warning">
        <span className="h-2 w-2 animate-pulse rounded-full bg-warning" />
        Creating...
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-success/20 bg-success/10 px-2.5 py-0.5 text-xs font-medium text-success">
      <span className="h-2 w-2 rounded-full bg-success" />
      Ready
    </span>
  );
}

function WorldCard({ world }: { world: World }) {
  const navigate = useNavigate();

  return (
    <div
      className="card elevate-on-hover cursor-pointer overflow-hidden p-0"
      onClick={() => navigate(`/?world_id=${world.world_id}`)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && navigate(`/?world_id=${world.world_id}`)}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-5 pt-4 pb-2">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-accent/10 p-1.5">
            <Globe size={16} className="text-accent" />
          </div>
          <div>
            <p className="text-sm font-semibold text-text-primary">{capitalize(world.name)}</p>
            <p className="font-mono text-xs text-text-muted">{truncateId(world.world_id, 20)}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={world.status} />
          <ChevronRight size={16} className="text-text-muted" />
        </div>
      </div>

      {/* Services */}
      {world.services.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-5 pb-3">
          {world.services.map((s) => (
            <span
              key={s}
              className="rounded-md border border-info/20 bg-info/10 px-2 py-0.5 text-[11px] font-medium text-info"
            >
              {s}
            </span>
          ))}
        </div>
      )}

      {/* Stats footer */}
      <div className="flex items-center justify-between border-t border-border/20 bg-bg-elevated/30 px-5 py-2.5 text-xs text-text-muted">
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {world.entity_count > 0 && (
            <span className="inline-flex items-center gap-1"><Box size={11} /> {world.entity_count} entities</span>
          )}
          {world.actor_count > 0 && (
            <span className="inline-flex items-center gap-1"><Users size={11} /> {world.actor_count} actors</span>
          )}
          <span className="inline-flex items-center gap-1"><Layers size={11} /> {world.services.length} services</span>
          <span className="inline-flex items-center gap-1"><Hash size={11} /> seed {world.seed}</span>
        </div>
        <span className="inline-flex items-center gap-1">
          <Clock size={11} /> {formatRelativeTime(world.created_at)}
        </span>
      </div>
    </div>
  );
}

export function WorldsListPage() {
  const worldsQuery = useWorlds();

  return (
    <div>
      <PageHeader
        title="Worlds"
        subtitle="Compiled world stages — the environments agents perform in"
      />

      <QueryGuard query={worldsQuery}>
        {(data) => {
          if (data.worlds.length === 0) {
            return (
              <EmptyState
                title="No worlds yet"
                description="Start a simulation from the CLI to create a world."
              />
            );
          }

          return (
            <div className="grid gap-3">
              {data.worlds.map((world) => (
                <WorldCard key={world.world_id} world={world} />
              ))}
            </div>
          );
        }}
      </QueryGuard>
    </div>
  );
}
