// ---------------------------------------------------------------------------
// Run comparison utilities
// ---------------------------------------------------------------------------

/**
 * Find the run ID with the best metric value from a record of run_id -> value.
 *
 * @param values - Map of run_id to numeric metric value
 * @param higherIsBetter - If true, highest value wins; if false, lowest wins (default true)
 * @returns The run_id of the best performer, or null if the map is empty
 */
export function findBestValue(
  values: Record<string, number>,
  higherIsBetter = true,
): string | null {
  const entries = Object.entries(values);
  if (entries.length === 0) return null;

  return entries.reduce((best, current) => {
    const isBetter = higherIsBetter
      ? current[1] > best[1]
      : current[1] < best[1];
    return isBetter ? current : best;
  })[0];
}

/**
 * Compute the delta and improvement direction between a baseline and current value.
 *
 * @param baseline - The reference metric value
 * @param current - The metric value to compare
 * @returns Object with `delta` (signed difference) and `improved` (whether current is better)
 */
export function computeMetricDelta(
  baseline: number,
  current: number,
): { delta: number; improved: boolean } {
  const delta = current - baseline;
  return { delta, improved: delta > 0 };
}
