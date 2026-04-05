import { describe, it, expect } from 'vitest';
import { buildCausalTree } from '@/lib/causal-graph';
import type { WorldEvent } from '@/types/domain';

function mockEvent(id: string, childIds: string[] = []): WorldEvent {
  return {
    event_id: id,
    event_type: 'agent_action',
    timestamp: { world_time: '', wall_time: '', tick: 0 },
    caused_by: null,
    actor_id: 'a',
    actor_role: 'agent',
    service_id: null,
    action: 'test',
    entity_ids: [],
    input_data: {},
    output_data: {},
    outcome: 'success',
    policy_hit: null,
    budget_delta: 0,
    budget_remaining: 0,
    causal_parent_ids: [],
    causal_child_ids: childIds,
    fidelity_tier: 1,
    fidelity: null,
    run_id: 'r1',
    metadata: {},
  };
}

describe('buildCausalTree', () => {
  it('returns null when root event not found', () => {
    expect(buildCausalTree([], 'missing')).toBeNull();
  });

  it('builds single-node tree for event with no children', () => {
    const tree = buildCausalTree([mockEvent('e1')], 'e1');
    expect(tree).not.toBeNull();
    expect(tree!.event.event_id).toBe('e1');
    expect(tree!.children).toHaveLength(0);
  });

  it('builds one-level tree', () => {
    const events = [mockEvent('root', ['c1', 'c2']), mockEvent('c1'), mockEvent('c2')];
    const tree = buildCausalTree(events, 'root');
    expect(tree!.children).toHaveLength(2);
    expect(tree!.children[0].event.event_id).toBe('c1');
    expect(tree!.children[1].event.event_id).toBe('c2');
  });

  it('builds multi-level tree', () => {
    const events = [mockEvent('root', ['c1']), mockEvent('c1', ['c2']), mockEvent('c2')];
    const tree = buildCausalTree(events, 'root');
    expect(tree!.children[0].children[0].event.event_id).toBe('c2');
  });

  it('skips children not in events list', () => {
    const events = [mockEvent('root', ['missing'])];
    const tree = buildCausalTree(events, 'root');
    expect(tree!.children).toHaveLength(0);
  });

  it('handles cycles gracefully', () => {
    const events = [mockEvent('a', ['b']), mockEvent('b', ['a'])];
    const tree = buildCausalTree(events, 'a');
    expect(tree!.children).toHaveLength(1);
    expect(tree!.children[0].children).toHaveLength(0); // cycle broken
  });
});
