import { useSearchParams } from 'react-router';
import { useCallback } from 'react';

export function useUrlState<T extends Record<string, string>>(
  defaults: T,
): [T, (updates: Partial<T>) => void] {
  const [searchParams, setSearchParams] = useSearchParams();

  const state = { ...defaults } as T;
  for (const key of Object.keys(defaults)) {
    const value = searchParams.get(key);
    if (value !== null) {
      (state as Record<string, string>)[key] = value;
    }
  }

  const setState = useCallback(
    (updates: Partial<T>) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        Object.entries(updates).forEach(([key, value]) => {
          if (value === undefined || value === '') {
            next.delete(key);
          } else {
            next.set(key, value);
          }
        });
        return next;
      });
    },
    [setSearchParams],
  );

  return [state, setState];
}
