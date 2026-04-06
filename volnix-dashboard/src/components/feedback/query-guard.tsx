import type { UseQueryResult } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { PageLoading } from './page-loading';
import { ErrorDisplay } from './error-display';
import { EmptyState } from './empty-state';

interface QueryGuardProps<T> {
  query: UseQueryResult<T>;
  loadingFallback?: ReactNode;
  emptyMessage?: string;
  children: (data: T) => ReactNode;
}

export function QueryGuard<T>({
  query,
  loadingFallback,
  emptyMessage,
  children,
}: QueryGuardProps<T>) {
  if (query.isLoading) {
    return <>{loadingFallback ?? <PageLoading />}</>;
  }

  if (query.isError) {
    return <ErrorDisplay error={query.error} onRetry={() => query.refetch()} />;
  }

  if (!query.data) {
    return <EmptyState title={emptyMessage ?? 'No data'} />;
  }

  return <>{children(query.data)}</>;
}
