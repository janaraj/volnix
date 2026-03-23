// ---------------------------------------------------------------------------
// Causal graph construction utilities
// ---------------------------------------------------------------------------

import type { WorldEvent } from '@/types/domain';

/** A node in a causal event tree. */
export interface CausalNode {
  event: WorldEvent;
  children: CausalNode[];
}

/**
 * Build a tree of causally-linked events starting from a given root event.
 * Uses causal_child_ids for traversal. Handles cycles via visited set.
 */
export function buildCausalTree(events: WorldEvent[], rootEventId: string): CausalNode | null {
  const eventMap = new Map<string, WorldEvent>();
  for (const event of events) {
    eventMap.set(event.event_id, event);
  }

  const rootEvent = eventMap.get(rootEventId);
  if (!rootEvent) return null;

  const visited = new Set<string>();

  function buildNode(event: WorldEvent): CausalNode {
    visited.add(event.event_id);
    const children: CausalNode[] = [];
    for (const childId of event.causal_child_ids) {
      if (!visited.has(childId)) {
        const childEvent = eventMap.get(childId);
        if (childEvent) {
          children.push(buildNode(childEvent));
        }
      }
    }
    return { event, children };
  }

  return buildNode(rootEvent);
}
