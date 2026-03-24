import { http, HttpResponse } from 'msw';
import { createMockRun, createMockRunList } from './data/runs';
import { createMockEventList } from './data/events';
import { createMockScorecard } from './data/scorecard';
import { createMockEntity } from './data/entities';
import { createMockCapabilityGap } from './data/gaps';
import { createMockRunComparison } from './data/comparison';

export const handlers = [
  http.get('/api/v1/runs', () => {
    return HttpResponse.json({
      items: createMockRunList(),
      total: 3,
      limit: 20,
      offset: 0,
      has_more: false,
    });
  }),

  http.get('/api/v1/runs/:id', ({ params }) => {
    return HttpResponse.json(createMockRun({ id: params.id as string }));
  }),

  http.get('/api/v1/runs/:id/events', () => {
    return HttpResponse.json({
      items: createMockEventList(),
      total: 10,
      limit: 50,
      offset: 0,
      has_more: false,
    });
  }),

  http.get('/api/v1/runs/:id/events/:eventId', () => {
    return HttpResponse.json(createMockEventList()[0]);
  }),

  http.get('/api/v1/runs/:id/scorecard', () => {
    return HttpResponse.json([
      createMockScorecard({ actor_id: 'agent-alpha', overall_score: 0.9 }),
      createMockScorecard({ actor_id: 'agent-beta', overall_score: 0.81 }),
      createMockScorecard({ actor_id: 'collective', overall_score: 0.85 }),
    ]);
  }),

  http.get('/api/v1/runs/:id/entities', () => {
    return HttpResponse.json({
      items: [createMockEntity()],
      total: 1,
      limit: 50,
      offset: 0,
      has_more: false,
    });
  }),

  http.get('/api/v1/runs/:id/entities/:entityId', () => {
    return HttpResponse.json(createMockEntity());
  }),

  http.get('/api/v1/runs/:id/gaps', () => {
    return HttpResponse.json([createMockCapabilityGap()]);
  }),

  http.get('/api/v1/runs/:id/actors/:actorId', () => {
    return HttpResponse.json({
      actor_id: 'agent-alpha',
      role: 'support-agent',
      actor_type: 'agent',
      budget_total: { api_calls: 500, llm_spend_usd: 10, world_actions: 200 },
      budget_remaining: { api_calls: 361, llm_spend_usd: 7.2, world_actions: 153 },
      action_count: 47,
      governance_score: 0.9,
    });
  }),

  http.get('/api/v1/compare', () => {
    return HttpResponse.json(createMockRunComparison());
  }),
];
