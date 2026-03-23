import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { UseQueryResult } from '@tanstack/react-query';
import { QueryGuard } from '@/components/feedback/query-guard';

type MockQuery = UseQueryResult<{ name: string }>;

function mockQuery(overrides: Partial<MockQuery>): MockQuery {
  return {
    isLoading: false,
    isError: false,
    data: undefined,
    error: null,
    refetch: vi.fn(),
    status: 'pending',
    fetchStatus: 'idle',
    isFetching: false,
    isSuccess: false,
    isPending: true,
    isRefetching: false,
    isLoadingError: false,
    isRefetchError: false,
    dataUpdatedAt: 0,
    errorUpdatedAt: 0,
    failureCount: 0,
    failureReason: null,
    errorUpdateCount: 0,
    isFetched: false,
    isFetchedAfterMount: false,
    isInitialLoading: false,
    isPlaceholderData: false,
    isStale: false,
    promise: Promise.resolve({ name: '' }),
    ...overrides,
  } as MockQuery;
}

describe('QueryGuard', () => {
  it('shows loading fallback when query is loading', () => {
    render(
      <QueryGuard query={mockQuery({ isLoading: true })}>
        {(data) => <span>{data.name}</span>}
      </QueryGuard>,
    );
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('shows error display when query fails', () => {
    render(
      <QueryGuard query={mockQuery({ isError: true, error: new Error('fail') })}>
        {(data) => <span>{data.name}</span>}
      </QueryGuard>,
    );
    expect(screen.getByText('fail')).toBeInTheDocument();
    expect(screen.getByText('Retry')).toBeInTheDocument();
  });

  it('shows empty state when data is null', () => {
    render(
      <QueryGuard query={mockQuery({ data: undefined })}>
        {(data) => <span>{data.name}</span>}
      </QueryGuard>,
    );
    expect(screen.getByText('No data')).toBeInTheDocument();
  });

  it('renders children with data when successful', () => {
    render(
      <QueryGuard query={mockQuery({ data: { name: 'test' } })}>
        {(data) => <span>{data.name}</span>}
      </QueryGuard>,
    );
    expect(screen.getByText('test')).toBeInTheDocument();
  });

  it('shows custom empty message when provided', () => {
    render(
      <QueryGuard query={mockQuery({ data: undefined })} emptyMessage="Nothing here">
        {(data) => <span>{data.name}</span>}
      </QueryGuard>,
    );
    expect(screen.getByText('Nothing here')).toBeInTheDocument();
  });
});
