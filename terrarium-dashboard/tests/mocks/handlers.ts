import { http, HttpResponse } from 'msw';
import { createMockRun, createMockRunList } from './data/runs';
import { createMockEventList } from './data/events';
import { createMockScorecardResponse } from './data/scorecard';
import { createMockEntity } from './data/entities';
import { createMockCapabilityGap } from './data/gaps';
import { createMockCompareResponse } from './data/comparison';

export const handlers = [
  http.get('/api/v1/runs', () => {
    return HttpResponse.json({
      runs: createMockRunList(),
      total: 3,
    });
  }),

  http.get('/api/v1/runs/:id', ({ params }) => {
    return HttpResponse.json(createMockRun({ run_id: params.id as string }));
  }),

  http.get('/api/v1/runs/:id/events', () => {
    return HttpResponse.json({
      events: createMockEventList(),
      total: 10,
    });
  }),

  http.get('/api/v1/runs/:id/events/:eventId', () => {
    return HttpResponse.json(createMockEventList()[0]);
  }),

  http.get('/api/v1/runs/:id/scorecard', () => {
    return HttpResponse.json(createMockScorecardResponse());
  }),

  http.get('/api/v1/runs/:id/entities', () => {
    return HttpResponse.json({
      entities: [createMockEntity()],
      total: 1,
    });
  }),

  http.get('/api/v1/runs/:id/entities/:entityId', () => {
    return HttpResponse.json(createMockEntity());
  }),

  http.get('/api/v1/runs/:id/gaps', () => {
    return HttpResponse.json({
      run_id: 'run-test-001',
      gaps: [createMockCapabilityGap()],
      summary: { hallucinated: 0, adapted: 1, escalated: 0, skipped: 0 },
    });
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
    return HttpResponse.json(createMockCompareResponse());
  }),
];
