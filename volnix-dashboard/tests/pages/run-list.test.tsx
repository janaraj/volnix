import { describe, it, expect, vi, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { server } from '../mocks/server';
import { http, HttpResponse } from 'msw';
import { ApiClient } from '@/services/api-client';
import { RunListPage } from '@/pages/run-list';
import { useCompareStore } from '@/stores/compare-store';

const testApi = new ApiClient('');
vi.mock('@/providers/services-provider', () => ({
  useApiClient: () => testApi,
}));

beforeAll(() => server.listen());
afterEach(() => {
  server.resetHandlers();
  useCompareStore.setState({ selectedRunIds: [] });
});
afterAll(() => server.close());

function renderPage(route = '/') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>
        <RunListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('RunListPage', () => {
  it('renders page header with title "Runs"', () => {
    renderPage();
    expect(screen.getByText('Runs')).toBeInTheDocument();
    expect(screen.getByText('All simulation runs')).toBeInTheDocument();
  });

  it('shows loading state initially', () => {
    renderPage();
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('renders run cards after data loads', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('exp-1-baseline')).toBeInTheDocument();
    });
    expect(screen.getByText('exp-2-hostile')).toBeInTheDocument();
    expect(screen.getByText('exp-3-edge')).toBeInTheDocument();
  });

  it('shows empty state when no runs', async () => {
    server.use(
      http.get('/api/v1/runs', () =>
        HttpResponse.json({ runs: [], total: 0 }),
      ),
    );
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('No runs yet')).toBeInTheDocument();
    });
  });

  it('renders status filter dropdown with options', () => {
    renderPage();
    // Find the select by its displayed text
    expect(screen.getByText('All statuses')).toBeInTheDocument();
  });

  it('renders preset filter dropdown with options', () => {
    renderPage();
    expect(screen.getByText('All presets')).toBeInTheDocument();
  });

  it('renders tag search input', () => {
    renderPage();
    expect(screen.getByPlaceholderText('Search tags...')).toBeInTheDocument();
  });

  it('shows RunStatusBadge for each run', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Completed')).toBeInTheDocument();
    });
    expect(screen.getByText('Running')).toBeInTheDocument();
    expect(screen.getByText('Failed')).toBeInTheDocument();
  });

  it('shows compare checkboxes on each card', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('exp-1-baseline')).toBeInTheDocument();
    });
    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes.length).toBeGreaterThanOrEqual(3);
  });

  it('shows compare toolbar when runs selected', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('exp-1-baseline')).toBeInTheDocument();
    });
    const checkboxes = screen.getAllByRole('checkbox');
    await user.click(checkboxes[0]);
    expect(screen.getByText(/1 run selected/)).toBeInTheDocument();
  });

  it('compare button disabled with < 2 selected', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('exp-1-baseline')).toBeInTheDocument();
    });
    const checkboxes = screen.getAllByRole('checkbox');
    await user.click(checkboxes[0]);
    const compareBtn = screen.getByText('Compare Selected');
    expect(compareBtn.closest('button')).toBeDisabled();
  });

  it('compare button enabled with >= 2 selected', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('exp-1-baseline')).toBeInTheDocument();
    });
    const checkboxes = screen.getAllByRole('checkbox');
    await user.click(checkboxes[0]);
    await user.click(checkboxes[1]);
    const compareBtn = screen.getByText('Compare Selected');
    expect(compareBtn.closest('button')).not.toBeDisabled();
  });

  it('shows score bar for runs with governance_score', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('exp-1-baseline')).toBeInTheDocument();
    });
    // Run 1 has governance_score: 0.87 → ScoreBar renders "87"
    expect(screen.getByText('87')).toBeInTheDocument();
  });

  it('does not show score bar for runs without governance_score', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('exp-2-hostile')).toBeInTheDocument();
    });
    // Run 2 has governance_score: null → no ScoreBar rendered
    // Verify the Governance label only appears for runs WITH scores
    const governanceLabels = screen.getAllByText('Governance');
    // Run 1 (0.87) and Run 3 (0.42) have scores, Run 2 does not
    expect(governanceLabels.length).toBe(2);
  });

  it('renders View button for completed runs', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('exp-1-baseline')).toBeInTheDocument();
    });
    expect(screen.getAllByText('View').length).toBeGreaterThanOrEqual(1);
  });

  it('renders Watch Live button for running runs', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('exp-2-hostile')).toBeInTheDocument();
    });
    expect(screen.getByText('Watch Live')).toBeInTheDocument();
  });
});
