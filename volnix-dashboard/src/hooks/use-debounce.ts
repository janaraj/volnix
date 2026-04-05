import { useState, useEffect } from 'react';

/**
 * Debounce a value by the given delay in milliseconds.
 * Returns the debounced value that only updates after the caller
 * stops changing the input for `delay` ms.
 */
export function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}
