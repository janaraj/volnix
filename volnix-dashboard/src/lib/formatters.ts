// ---------------------------------------------------------------------------
// Display formatting utilities
// ---------------------------------------------------------------------------

import { formatDistanceToNowStrict, isValid, parseISO, format } from 'date-fns';
import { RELATIVE_TIME_THRESHOLD_MS } from '@/constants/defaults';

/**
 * Format an ISO date string as a human-friendly relative time (e.g. "2 minutes ago").
 * Falls back to absolute format ("Mar 1, 09:00") for dates older than the threshold.
 * Returns the raw input for invalid date strings.
 */
export function formatRelativeTime(isoDate: string): string {
  const date = parseISO(isoDate);
  if (!isValid(date)) return isoDate;
  const diffMs = Date.now() - date.getTime();
  if (diffMs > RELATIVE_TIME_THRESHOLD_MS) {
    return format(date, 'MMM d, HH:mm');
  }
  return formatDistanceToNowStrict(date, { addSuffix: true });
}

/**
 * Format a duration in milliseconds to a human-readable string.
 * Examples: 500 → "500ms", 65000 → "1m 5s", 3661000 → "1h 1m 1s"
 */
export function formatDuration(ms: number): string {
  if (ms <= 0) return '0ms';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const totalSeconds = Math.floor(ms / 1000);
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  const parts: string[] = [];
  if (h > 0) parts.push(`${h}h`);
  if (m > 0) parts.push(`${m}m`);
  if (s > 0 || parts.length === 0) parts.push(`${s}s`);
  return parts.join(' ');
}

/** Format a USD amount to a locale-aware currency string. */
const currencyFmt = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
export function formatCurrency(usd: number): string {
  return currencyFmt.format(usd);
}

/** Format a 0-1 score value as a whole-number string (e.g. 0.87 → "87"). */
export function formatScore(value: number): string {
  return Math.round(value * 100).toString();
}

/** Format a 0-1 value as a percentage string (e.g. 0.87 → "87%"). */
export function formatPercentage(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** Format a tick number with a leading hash (e.g. 234 → "#234"). */
export function formatTick(tick: number): string {
  return `#${tick}`;
}

/** Truncate a long identifier for display purposes. */
export function truncateId(id: string, len?: number): string {
  return (id ?? '').slice(0, len ?? 8);
}

/** Capitalize first letter of each word. */
export function capitalize(str: string): string {
  return str.replace(/\b\w/g, (c) => c.toUpperCase());
}
