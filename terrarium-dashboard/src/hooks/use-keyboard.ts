import { useEffect, useRef } from 'react';

type KeyHandler = (event: KeyboardEvent) => void;

const PREVENT_DEFAULT_KEYS = new Set(['ArrowUp', 'ArrowDown', 'Escape']);

export function useKeyboard(bindings: Record<string, KeyHandler>): void {
  const bindingsRef = useRef(bindings);
  bindingsRef.current = bindings;

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const fn = bindingsRef.current[event.key];
      if (fn) {
        if (PREVENT_DEFAULT_KEYS.has(event.key)) {
          event.preventDefault();
        }
        fn(event);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);
}
