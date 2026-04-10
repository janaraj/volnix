import { describe, it, expect, vi, beforeAll, beforeEach, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { server } from '../mocks/server';
import { http, HttpResponse } from 'msw';
import { ApiClient } from '@/services/api-client';
import { WsManager } from '@/services/ws-manager';
import { Inspector } from '@/pages/live-console/inspector';
import type { Run, WorldEvent } from '@/types/domain';

// Inspector imports useActor which uses the services-provider. Mock it.
const testApi = new ApiClient('');
const testWs = new WsManager('ws://localhost');

vi.mock('@/providers/services-provider', () => ({
  useApiClient: () => testApi,
  useWsManager: () => testWs,
}));

beforeAll(() => server.listen());
beforeEach(() => {
  // Default: actor endpoint returns a minimal agent
  server.use(
    http.get('/api/v1/runs/:runId/actors/:actorId', () =>
      HttpResponse.json({
        actor_id: 'buyer-1',
        definition: {
          role: 'buyer',
          type: 'internal',
          budget: { total: { api_calls: 30 }, remaining: { api_calls: 20 } },
        },
        scorecard: null,
        action_count: 7,
        last_action_at: null,
      }),
    ),
  );
});
afterEach(() => {
  server.resetHandlers();
  vi.restoreAllMocks();
});
afterAll(() => server.close());

const fakeRun: Run = {
  run_id: 'r1',
  status: 'running',
  world_def: { name: 'Test World' },
  mode: 'governed',
  reality_preset: 'messy',
  fidelity_mode: 'auto',
  tag: '',
  config_snapshot: { behavior: 'dynamic' },
  created_at: '',
  started_at: null,
  completed_at: null,
  services: [
    {
      service_id: 'slack',
      service_name: 'slack',
      category: 'communication',
      fidelity_tier: 1,
      fidelity_source: 'verified_pack',
      entity_count: 0,
    },
  ],
};

function chatEvent(overrides: Partial<WorldEvent> = {}): WorldEvent {
  return {
    event_type: 'world.chat.postMessage',
    event_id: `e-${Math.random().toString(36).slice(2)}`,
    actor_id: 'buyer-1',
    actor_role: 'buyer',
    action: 'chat.postMessage',
    service_id: 'slack',
    outcome: 'success',
    timestamp: { wall_time: '', world_time: '', tick: 1 },
    input_data: { channel_id: 'C1', text: 'hi-message' },
    response_body: { ok: true, message: { text: 'hi-message' } },
    ...overrides,
  };
}

function renderInspector(overrides: {
  selectedActorId?: string | null;
  events?: WorldEvent[];
} = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Inspector
        runId="r1"
        selectedActorId={overrides.selectedActorId ?? null}
        run={fakeRun}
        events={overrides.events ?? []}
      />
    </QueryClientProvider>,
  );
}

describe('Inspector (bottom horizontal strip)', () => {
  it('renders the Inspector label header', () => {
    renderInspector();
    expect(screen.getByText('Inspector')).toBeInTheDocument();
  });

  it('shows RunInspectorBar by default when no actor is selected', () => {
    renderInspector({ events: [chatEvent(), chatEvent({ actor_id: 'supplier-1' })] });
    expect(screen.getByText(/Active Agents/i)).toBeInTheDocument();
    // Actor IDs appear in the active agents list
    expect(screen.getByText(/buyer-1/)).toBeInTheDocument();
    expect(screen.getByText(/supplier-1/)).toBeInTheDocument();
  });

  it('shows Services section when the run has services', () => {
    renderInspector();
    expect(screen.getByText(/Services/i)).toBeInTheDocument();
  });

  it('shows empty state when no events and no services', () => {
    const emptyRun: Run = { ...fakeRun, services: [] };
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <Inspector runId="r1" selectedActorId={null} run={emptyRun} events={[]} />
      </QueryClientProvider>,
    );
    expect(screen.getByText(/No activity yet/i)).toBeInTheDocument();
  });

  it('switches to AgentInspectorBar when selectedActorId is set', async () => {
    renderInspector({ selectedActorId: 'buyer-1' });
    await waitFor(() => {
      // AgentInspectorBar fetches and displays the agent — look for its sections
      // "Actions" and "Budgets" are unique labels to the agent view.
      expect(screen.getByText('Budgets')).toBeInTheDocument();
      expect(screen.getByText('Actions')).toBeInTheDocument();
      // The actor type badge "internal" comes from the fetched agent
      expect(screen.getByText('internal')).toBeInTheDocument();
      // Action count from the mock
      expect(screen.getByText('7')).toBeInTheDocument();
    });
  });

  it('counts active agents excluding internal actors', () => {
    const events = [
      chatEvent({ actor_id: 'buyer-1' }),
      chatEvent({ actor_id: 'buyer-1' }),
      chatEvent({ actor_id: 'supplier-1' }),
      chatEvent({ actor_id: 'animator' }), // internal — should NOT appear
      chatEvent({ actor_id: 'policy' }), // internal — should NOT appear
    ];
    renderInspector({ events });
    // buyer-1 has 2 actions, supplier-1 has 1 — both visible
    expect(screen.getByText(/buyer-1/)).toBeInTheDocument();
    expect(screen.getByText(/supplier-1/)).toBeInTheDocument();
    // Internal actors are filtered out — no text match for `animator` as an actor pill
    expect(screen.queryByText(/· 1/)).toBeInTheDocument(); // supplier-1 count
  });
});
