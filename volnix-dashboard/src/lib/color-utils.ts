// ---------------------------------------------------------------------------
// Color utilities for scores and charts
// ---------------------------------------------------------------------------

/** Map a 0-1 score to Tailwind bg + text color classes (dark-theme-friendly). */
export function scoreToColorClass(value: number): string {
  if (value >= 0.9) return 'bg-score-excellent/15 text-score-excellent';
  if (value >= 0.75) return 'bg-score-good/15 text-score-good';
  if (value >= 0.6) return 'bg-score-fair/15 text-score-fair';
  return 'bg-score-poor/15 text-score-poor';
}

/**
 * Interpolate a 0-1 score to a hex color string for charts.
 * Transitions: red (0) → yellow (0.5) → green (1.0).
 */
export function interpolateScoreColor(value: number): string {
  const clamped = Math.max(0, Math.min(1, value));
  // Two-segment interpolation: 0→0.5 maps red(0°)→yellow(60°), 0.5→1 maps yellow(60°)→green(142°)
  const hue = clamped <= 0.5
    ? clamped * 2 * 60
    : 60 + (clamped - 0.5) * 2 * 82;
  return hslToHex(hue, 70, 50);
}

function hslToHex(h: number, s: number, l: number): string {
  const sNorm = s / 100;
  const lNorm = l / 100;
  const a = sNorm * Math.min(lNorm, 1 - lNorm);
  const f = (n: number) => {
    const k = (n + h / 30) % 12;
    const color = lNorm - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
    return Math.max(0, Math.min(255, Math.round(255 * color))).toString(16).padStart(2, '0');
  };
  return `#${f(0)}${f(8)}${f(4)}`;
}
