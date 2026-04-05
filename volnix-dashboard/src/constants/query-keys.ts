// ---------------------------------------------------------------------------
// TanStack Query key factories
// ---------------------------------------------------------------------------

import type { RunListParams, EventFilterParams, EntityFilterParams } from '@/types/api';

export const queryKeys = {
  runs: {
    all: ['runs'] as const,
    list: (params?: RunListParams) => ['runs', 'list', params] as const,
    detail: (id: string) => ['runs', id] as const,
    events: (id: string, params?: EventFilterParams) => ['runs', id, 'events', params] as const,
    event: (runId: string, eventId: string) => ['runs', runId, 'events', eventId] as const,
    scorecard: (id: string) => ['runs', id, 'scorecard'] as const,
    entities: (id: string, params?: EntityFilterParams) =>
      ['runs', id, 'entities', params] as const,
    entity: (runId: string, entityId: string) => ['runs', runId, 'entities', entityId] as const,
    gaps: (id: string) => ['runs', id, 'gaps'] as const,
    actor: (runId: string, actorId: string) => ['runs', runId, 'actors', actorId] as const,
  },
  worlds: {
    all: ['worlds'] as const,
    list: () => ['worlds', 'list'] as const,
    detail: (id: string) => ['worlds', id] as const,
  },
  compare: {
    // Lexicographic sort ensures same cache key regardless of selection order.
    // slice() prevents mutation of caller's array.
    detail: (runIds: string[]) => ['compare', ...runIds.slice().sort()] as const,
  },
} as const;
