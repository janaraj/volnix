import { describe, it, expect, vi, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router';
import { server } from '../mocks/server';
import { ApiClient } from '@/services/api-client';
import { ComparePage } from '@/pages/compare';

const testApi = new ApiClient('');
vi.mock('@/providers/services-provider', () => ({
  useApiClient: () => testApi,
}));

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderPage(runIds = 'run-1,run-2') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/compare?runs=${runIds}`]}>
        <Routes>
          <Route path="/compare" element={<ComparePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ComparePage', () => {
  it('shows empty state when < 2 runs', () => {
    renderPage('');
    expect(screen.getByText(/Select at least 2 runs/)).toBeInTheDocument();
  });

  it('shows loading state initially', () => {
    renderPage();
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('renders breadcrumb with Compare', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Compare')).toBeInTheDocument();
    });
  });

  it('renders Comparing header with run tags', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/Comparing:/)).toBeInTheDocument();
    });
  });

  it('renders world info with reality and behavior', async () => {
    renderPage();
    await waitFor(() => {
      // Spec requires "World: {name} · {reality} · {behavior} · {mode}"
      expect(screen.getByText(/World:/)).toBeInTheDocument();
      // "messy" appears in both header and export area
      expect(screen.getAllByText(/messy/).length).toBeGreaterThanOrEqual(1);
    });
  });

  it('renders Export button', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/Export/)).toBeInTheDocument();
    });
  });

  it('renders comparison table with metric rows', async () => {
    renderPage();
    await waitFor(() => {
      // "Governance Score" appears in both table and score bars
      expect(screen.getAllByText('Governance Score').length).toBeGreaterThanOrEqual(1);
    });
  });

  it('renders comparison table column headers with run tags', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText('exp-1-baseline').length).toBeGreaterThanOrEqual(1);
    });
  });

  it('highlights winner with best label', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText(/best/).length).toBeGreaterThanOrEqual(1);
    });
  });

  it('renders divergence points section', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Divergence Points')).toBeInTheDocument();
    });
  });

  it('renders divergence point description', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/Refund attempt/)).toBeInTheDocument();
    });
  });

  it('renders Terrarium branding in export area', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Terrarium')).toBeInTheDocument();
    });
  });
});
