import { describe, it, expect, vi, beforeAll, beforeEach, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router';
import { server } from '../mocks/server';
import { http, HttpResponse } from 'msw';
import { ApiClient } from '@/services/api-client';
import { WsManager } from '@/services/ws-manager';
import { MockWebSocket } from '../helpers/mock-websocket';
import { LiveConsolePage } from '@/pages/live-console';
import { createMockRun } from '../mocks/data/runs';

const testApi = new ApiClient('');
let testWs: WsManager;

vi.mock('@/providers/services-provider', () => ({
  useApiClient: () => testApi,
  useWsManager: () => testWs,
}));

beforeAll(() => server.listen());
beforeEach(() => {
  MockWebSocket.reset();
  vi.stubGlobal('WebSocket', MockWebSocket);
  testWs = new WsManager('ws://localhost');
  // Default: return a running run
  server.use(
    http.get('/api/v1/runs/:id', () =>
      HttpResponse.json(createMockRun({ status: 'running', completed_at: null })),
    ),
  );
});
afterEach(() => {
  server.resetHandlers();
  vi.restoreAllMocks();
});
afterAll(() => server.close());

function renderPage(runId = 'run-test-001') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/runs/${runId}/live`]}>
        <Routes>
          <Route path="/runs/:id/live" element={<LiveConsolePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('LiveConsolePage', () => {
  // ── Shell / Header ───────────────────────────────────────────

  it('shows loading state initially', () => {
    renderPage();
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('renders breadcrumb with Live label', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Live')).toBeInTheDocument();
    });
  });

  it('renders run world_name in header', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Acme Support Organization')).toBeInTheDocument();
    });
  });

  it('renders tick counter', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Tick:')).toBeInTheDocument();
    });
  });

  it('renders agent count', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Agents:')).toBeInTheDocument();
    });
  });

  it('renders event count', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Events:')).toBeInTheDocument();
    });
  });

  it('renders disabled control buttons', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Acme Support Organization')).toBeInTheDocument();
    });
    // Both Pause and Stop buttons have the same title
    const buttons = screen.getAllByTitle('Not available in v1');
    expect(buttons.length).toBe(2);
    buttons.forEach((btn) => expect(btn).toBeDisabled());
  });

  // ── Event Feed ───────────────────────────────────────────────

  it('renders event feed items from mock data', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText('email_read_inbox').length).toBeGreaterThan(0);
    });
  });

  it('renders event feed header with count', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/Event Feed/)).toBeInTheDocument();
    });
  });

  it('renders outcome filter dropdown', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByLabelText('Filter by outcome')).toBeInTheDocument();
    });
  });

  it('renders event type filter dropdown', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByLabelText('Filter by event type')).toBeInTheDocument();
    });
  });

  it('renders actor filter dropdown', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByLabelText('Filter by actor')).toBeInTheDocument();
    });
  });

  it('renders service filter dropdown', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByLabelText('Filter by service')).toBeInTheDocument();
    });
  });

  // ── Transition Banner ────────────────────────────────────────

  it('transition banner hidden when run is running', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Acme Support Organization')).toBeInTheDocument();
    });
    expect(screen.queryByText('Run completed')).not.toBeInTheDocument();
  });

  it('transition banner visible when run is completed', async () => {
    // Override the beforeEach mock with completed status
    server.use(
      http.get('/api/v1/runs/:id', () =>
        HttpResponse.json(createMockRun({ status: 'completed' })),
      ),
    );
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Run completed')).toBeInTheDocument();
    });
    expect(screen.getByText('View report')).toBeInTheDocument();
  });

  // ── Error Handling ───────────────────────────────────────────

  it('shows error state when run fetch fails', async () => {
    server.use(
      http.get('/api/v1/runs/:id', () =>
        HttpResponse.json({ code: 'NOT_FOUND', message: 'Run not found' }, { status: 404 }),
      ),
    );
    renderPage('nonexistent');
    await waitFor(() => {
      expect(screen.getByText('Run not found')).toBeInTheDocument();
    });
  });
});
