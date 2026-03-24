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

  it('renders run world_name', async () => {
    renderPage();
    await waitFor(() => {
      // World name appears in header and possibly overview
      expect(screen.getAllByText('Acme Support Organization').length).toBeGreaterThanOrEqual(1);
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
      expect(screen.getByText('Live')).toBeInTheDocument();
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
      expect(screen.getByText('Live')).toBeInTheDocument();
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

  // ── Context View ──────────────────────────────────────────────

  it('default center view shows run overview', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Run Overview')).toBeInTheDocument();
    });
  });

  it('run overview shows metric cards', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Tick')).toBeInTheDocument();
      expect(screen.getByText('Agents')).toBeInTheDocument();
    });
  });

  it('click event in feed shows event detail in center', async () => {
    const user = (await import('@testing-library/user-event')).default.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText('email_read_inbox').length).toBeGreaterThan(0);
    });
    // Click the first event row (it's a button)
    const eventButtons = screen.getAllByText('email_read_inbox');
    await user.click(eventButtons[0].closest('button')!);
    await waitFor(() => {
      expect(screen.getByText(/Event:/)).toBeInTheDocument();
    });
  });

  it('event detail shows input/output labels', async () => {
    const user = (await import('@testing-library/user-event')).default.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText('email_read_inbox').length).toBeGreaterThan(0);
    });
    await user.click(screen.getAllByText('email_read_inbox')[0].closest('button')!);
    await waitFor(() => {
      expect(screen.getByText('Input')).toBeInTheDocument();
      expect(screen.getByText('Output')).toBeInTheDocument();
    });
  });

  it('close button in context view clears selection', async () => {
    const user = (await import('@testing-library/user-event')).default.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText('email_read_inbox').length).toBeGreaterThan(0);
    });
    await user.click(screen.getAllByText('email_read_inbox')[0].closest('button')!);
    await waitFor(() => {
      expect(screen.getByText(/Event:/)).toBeInTheDocument();
    });
    await user.click(screen.getByLabelText('Close detail'));
    await waitFor(() => {
      expect(screen.getByText('Run Overview')).toBeInTheDocument();
    });
  });

  // ── Inspector ────────────────────────────────────────────────

  it('inspector shows run metadata when no actor selected', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Inspector')).toBeInTheDocument();
    });
  });

  it('inspector shows services list', async () => {
    renderPage();
    await waitFor(() => {
      // Mock run has 3 services
      expect(screen.getAllByText(/email|chat|payments/).length).toBeGreaterThan(0);
    });
  });

  // ── Agent Selection ─────────────────────────────────────────

  it('selecting event updates inspector to agent mode', async () => {
    const user = (await import('@testing-library/user-event')).default.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText('email_read_inbox').length).toBeGreaterThan(0);
    });
    // Click an event (which also sets selectedActorId via handleSelectEvent)
    await user.click(screen.getAllByText('email_read_inbox')[0].closest('button')!);
    // Inspector should switch to agent mode
    await waitFor(() => {
      expect(screen.getByText('Agent Inspector')).toBeInTheDocument();
    });
  });

  it('inspector updates to agent mode when actor selected', async () => {
    const user = (await import('@testing-library/user-event')).default.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText('email_read_inbox').length).toBeGreaterThan(0);
    });
    // Click an event (which also sets selectedActorId)
    await user.click(screen.getAllByText('email_read_inbox')[0].closest('button')!);
    await waitFor(() => {
      expect(screen.getByText('Agent Inspector')).toBeInTheDocument();
    });
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
