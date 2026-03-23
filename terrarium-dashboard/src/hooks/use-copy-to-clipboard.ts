import { useState, useCallback, useRef } from 'react';

/** Copy text to clipboard with temporary "copied" state. */
export function useCopyToClipboard(resetMs = 1500) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const copy = useCallback(async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setCopied(false), resetMs);
    } catch {
      // Clipboard API unavailable (e.g., iframe sandbox)
    }
  }, [resetMs]);

  return { copy, copied } as const;
}
