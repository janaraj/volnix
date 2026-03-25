import { describe, it, expect, vi, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router';
import { server } from '../mocks/server';
import { http, HttpResponse } from 'msw';
import { ApiClient } from '@/services/api-client';
import { RunReportPage } from '@/pages/run-report';

const testApi = new ApiClient('');
vi.mock('@/providers/services-provider', () => ({
  useApiClient: () => testApi,
}));

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderPage(runId = 'run-test-001', searchParams = '') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/runs/${runId}${searchParams}`]}>
        <Routes>
          <Route path="/runs/:id" element={<RunReportPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('RunReportPage', () => {
  // ── Shell tests ──────────────────────────────────────────────────

  it('shows loading state initially', () => {
    renderPage();
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('renders report header with world name', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Acme Support Organization')).toBeInTheDocument();
    });
  });

  it('renders governance score in header', async () => {
    renderPage();
    await waitFor(() => {
      // Mock run has governance_score: 0.87 → ScoreBar shows "87"
      expect(screen.getByText('87')).toBeInTheDocument();
    });
  });

  it('renders all 6 tab buttons', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Overview')).toBeInTheDocument();
    });
    expect(screen.getByText('Scorecard')).toBeInTheDocument();
    // "Events" may appear in both tab and metric card — use getAllByText
    expect(screen.getAllByText('Events').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Entities')).toBeInTheDocument();
    expect(screen.getByText('Gaps')).toBeInTheDocument();
    expect(screen.getByText('Conditions')).toBeInTheDocument();
  });

  it('overview tab is active by default', async () => {
    renderPage();
    await waitFor(() => {
      // Overview tab content should be visible — look for metric cards
      expect(screen.getByText('Overview')).toBeInTheDocument();
    });
  });

  it('respects ?tab= URL parameter', async () => {
    renderPage('run-test-001', '?tab=conditions');
    await waitFor(() => {
      expect(screen.getByText('Information Quality')).toBeInTheDocument();
    });
  });

  // ── Tab switching ──────────────────────────────────────────────

  it('switches to scorecard tab when clicked', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Scorecard')).toBeInTheDocument();
    });
    await user.click(screen.getByText('Scorecard'));
    await waitFor(() => {
      // Scorecard tab should render dimension names from mock scorecard
      expect(screen.getByText('Policy Compliance')).toBeInTheDocument();
    });
  });

  it('switches to conditions tab when clicked', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Conditions')).toBeInTheDocument();
    });
    await user.click(screen.getByText('Conditions'));
    await waitFor(() => {
      expect(screen.getByText('Information Quality')).toBeInTheDocument();
    });
  });

  // ── Overview tab ───────────────────────────────────────────────

  it('shows event count metric card', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('847')).toBeInTheDocument();
    });
  });

  it('shows actor count metric card', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('4')).toBeInTheDocument();
    });
  });

  // ── Scorecard tab ──────────────────────────────────────────────

  it('renders scorecard dimension names', async () => {
    renderPage('run-test-001', '?tab=scorecard');
    await waitFor(() => {
      expect(screen.getByText('Policy Compliance')).toBeInTheDocument();
    });
  });

  it('renders fidelity confidence', async () => {
    renderPage('run-test-001', '?tab=scorecard');
    await waitFor(() => {
      expect(screen.getByText(/HIGH/i)).toBeInTheDocument();
    });
  });

  it('shows scorecard click hint text', async () => {
    renderPage('run-test-001', '?tab=scorecard');
    await waitFor(() => {
      expect(screen.getByText(/Click any score/)).toBeInTheDocument();
    });
  });

  it('renders collective column in scorecard', async () => {
    renderPage('run-test-001', '?tab=scorecard');
    await waitFor(() => {
      expect(screen.getByText('collective')).toBeInTheDocument();
    });
  });

  // ── Conditions tab ─────────────────────────────────────────────

  it('renders all 5 dimension cards with full titles', async () => {
    renderPage('run-test-001', '?tab=conditions');
    await waitFor(() => {
      expect(screen.getByText('Information Quality')).toBeInTheDocument();
    });
    expect(screen.getByText('Service Reliability')).toBeInTheDocument();
    expect(screen.getByText('Social Friction')).toBeInTheDocument();
    expect(screen.getByText('Task Complexity')).toBeInTheDocument();
    expect(screen.getByText('Governance Boundaries')).toBeInTheDocument();
  });

  it('shows reality and behavior header on conditions tab', async () => {
    renderPage('run-test-001', '?tab=conditions');
    await waitFor(() => {
      // "messy" appears in both report header badges and conditions tab header
      // Verify the conditions-specific labels "Reality:" and "Behavior:" exist
      expect(screen.getByText('Reality:')).toBeInTheDocument();
      expect(screen.getByText('Behavior:')).toBeInTheDocument();
    });
  });

  // ── Events tab ──────────────────────────────────────────────────

  it('renders events tab header with total count', async () => {
    renderPage('run-test-001', '?tab=events');
    await waitFor(() => {
      expect(screen.getByText(/EVENTS/)).toBeInTheDocument();
      expect(screen.getByText(/10 total/)).toBeInTheDocument();
    });
  });

  it('renders event table column headers', async () => {
    renderPage('run-test-001', '?tab=events');
    await waitFor(() => {
      expect(screen.getByText('Tick')).toBeInTheDocument();
      expect(screen.getByText('Time')).toBeInTheDocument();
      expect(screen.getByText('Actor')).toBeInTheDocument();
      expect(screen.getByText('Action')).toBeInTheDocument();
    });
  });

  it('renders event rows from mock data', async () => {
    renderPage('run-test-001', '?tab=events');
    await waitFor(() => {
      expect(screen.getAllByText('email_read_inbox').length).toBeGreaterThan(0);
    });
  });

  it('renders event filter dropdowns', async () => {
    renderPage('run-test-001', '?tab=events');
    await waitFor(() => {
      expect(screen.getByLabelText('Filter by actor')).toBeInTheDocument();
      expect(screen.getByLabelText('Filter by service')).toBeInTheDocument();
      expect(screen.getByLabelText('Filter by outcome')).toBeInTheDocument();
      expect(screen.getByLabelText('Filter by type')).toBeInTheDocument();
    });
  });

  it('renders event search input', async () => {
    renderPage('run-test-001', '?tab=events');
    await waitFor(() => {
      expect(screen.getByLabelText('Search events')).toBeInTheDocument();
    });
  });

  it('shows event detail panel when row clicked', async () => {
    const user = userEvent.setup();
    renderPage('run-test-001', '?tab=events');
    await waitFor(() => {
      expect(screen.getAllByText('email_read_inbox').length).toBeGreaterThan(0);
    });
    const rows = screen.getAllByText('email_read_inbox');
    await user.click(rows[0].closest('tr')!);
    await waitFor(() => {
      expect(screen.getByText(/Event:/)).toBeInTheDocument();
    });
  });

  it('closes event detail when close button clicked', async () => {
    const user = userEvent.setup();
    renderPage('run-test-001', '?tab=events');
    await waitFor(() => {
      expect(screen.getAllByText('email_read_inbox').length).toBeGreaterThan(0);
    });
    await user.click(screen.getAllByText('email_read_inbox')[0].closest('tr')!);
    await waitFor(() => {
      expect(screen.getByText(/Event:/)).toBeInTheDocument();
    });
    await user.click(screen.getByLabelText('Close event detail'));
    await waitFor(() => {
      expect(screen.queryByText(/Event:/)).not.toBeInTheDocument();
    });
  });

  // ── Entities tab ───────────────────────────────────────────────

  it('renders entities tab header with total count', async () => {
    renderPage('run-test-001', '?tab=entities');
    await waitFor(() => {
      expect(screen.getByText(/ENTITIES/)).toBeInTheDocument();
      expect(screen.getByText(/1 total/)).toBeInTheDocument();
    });
  });

  it('renders entity card with ID and type', async () => {
    renderPage('run-test-001', '?tab=entities');
    await waitFor(() => {
      expect(screen.getByText('TK-2847')).toBeInTheDocument();
      // 'ticket' appears in both entity card badge and dynamic filter dropdown
      expect(screen.getAllByText('ticket').length).toBeGreaterThanOrEqual(1);
    });
  });

  it('renders entity type filter dropdown', async () => {
    renderPage('run-test-001', '?tab=entities');
    await waitFor(() => {
      expect(screen.getByLabelText('Filter by entity type')).toBeInTheDocument();
    });
  });

  it('shows entity detail when View clicked', async () => {
    const user = userEvent.setup();
    renderPage('run-test-001', '?tab=entities');
    await waitFor(() => {
      expect(screen.getByText('TK-2847')).toBeInTheDocument();
    });
    await user.click(screen.getByText('View'));
    await waitFor(() => {
      expect(screen.getByText(/Entity:/)).toBeInTheDocument();
    });
  });

  it('closes entity detail when close button clicked', async () => {
    const user = userEvent.setup();
    renderPage('run-test-001', '?tab=entities');
    await waitFor(() => {
      expect(screen.getByText('TK-2847')).toBeInTheDocument();
    });
    await user.click(screen.getByText('View'));
    await waitFor(() => {
      expect(screen.getByText(/Entity:/)).toBeInTheDocument();
    });
    await user.click(screen.getByLabelText('Close entity detail'));
    await waitFor(() => {
      expect(screen.queryByText(/Entity:/)).not.toBeInTheDocument();
    });
  });

  // ── Gaps tab ───────────────────────────────────────────────────

  it('renders gaps tab header with count', async () => {
    renderPage('run-test-001', '?tab=gaps');
    await waitFor(() => {
      expect(screen.getByText(/CAPABILITY GAPS/)).toBeInTheDocument();
      expect(screen.getByText(/1 detected/)).toBeInTheDocument();
    });
  });

  it('renders gap table column headers', async () => {
    renderPage('run-test-001', '?tab=gaps');
    await waitFor(() => {
      expect(screen.getByText('Event')).toBeInTheDocument();
      expect(screen.getByText('Agent')).toBeInTheDocument();
      expect(screen.getByText('Gap')).toBeInTheDocument();
      expect(screen.getByText('Response')).toBeInTheDocument();
    });
  });

  it('renders gap row with tool name', async () => {
    renderPage('run-test-001', '?tab=gaps');
    await waitFor(() => {
      expect(screen.getByText('crm_lookup_customer')).toBeInTheDocument();
    });
  });

  it('renders gap distribution summary', async () => {
    renderPage('run-test-001', '?tab=gaps');
    await waitFor(() => {
      expect(screen.getByText(/Adapted:/)).toBeInTheDocument();
    });
  });

  it('shows empty state when no gaps', async () => {
    server.use(
      http.get('/api/v1/runs/:id/gaps', () => HttpResponse.json([])),
    );
    renderPage('run-test-001', '?tab=gaps');
    await waitFor(() => {
      expect(screen.getByText('No capability gaps detected')).toBeInTheDocument();
    });
  });

  // ── Error handling ─────────────────────────────────────────────

  it('shows error state when run fetch fails', async () => {
    server.use(
      http.get('/api/v1/runs/:id', () =>
        HttpResponse.json({ code: 'NOT_FOUND', message: 'Not found' }, { status: 404 }),
      ),
    );
    renderPage('nonexistent');
    await waitFor(() => {
      expect(screen.getByText('Not found')).toBeInTheDocument();
    });
  });
});
