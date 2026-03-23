import type { ReactNode } from 'react';
import { QueryProvider } from './query-provider';
import { ServicesProvider } from './services-provider';

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <QueryProvider>
      <ServicesProvider>
        {children}
      </ServicesProvider>
    </QueryProvider>
  );
}
