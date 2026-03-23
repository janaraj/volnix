// ---------------------------------------------------------------------------
// Score computation utilities
// ---------------------------------------------------------------------------

/** Compute a letter grade and associated Tailwind color class from a numeric score. */
export function computeGrade(score: number): { label: string; colorClass: string } {
  if (score >= 0.9) return { label: 'A', colorClass: 'text-score-excellent' };
  if (score >= 0.75) return { label: 'B', colorClass: 'text-score-good' };
  if (score >= 0.6) return { label: 'C', colorClass: 'text-score-fair' };
  return { label: 'D', colorClass: 'text-score-poor' };
}

/** Clamp a value into the 0-1 range, optionally normalizing from a custom range. */
export function normalizeScore(value: number, min = 0, max = 1): number {
  if (max === min) return 0;
  return Math.max(0, Math.min(1, (value - min) / (max - min)));
}
