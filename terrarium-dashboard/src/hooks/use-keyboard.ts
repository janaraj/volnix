import { useEffect } from 'react';

type KeyHandler = (event: KeyboardEvent) => void;

export function useKeyboard(bindings: Record<string, KeyHandler>): void {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const key = event.key;
      if (bindings[key]) {
        bindings[key](event);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [bindings]);
}
